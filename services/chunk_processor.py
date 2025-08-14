import asyncio
import time

from pydantic_ai import Agent
import structlog

logger = structlog.get_logger(__name__)

PROMPT = """
Extract detailed information from this meeting transcript segment. Preserve specific details, names, numbers, and technical terms.

1. DETAILED POINTS: Extract 8-12 detailed bullet points that preserve:
   - Speaker names (e.g., "Nathaniel Meixler explained that...")
   - Specific numbers, percentages, metrics (e.g., "70% accuracy", "2% threshold")
   - Technical terms and company names (e.g., "13F filings", "ARM model", "Starmine")
   - Specific examples and use cases
   - Do NOT summarize - extract verbatim important statements

2. IMPORTANCE SCORE (1-10 based on decisions made, action items, strategic discussions)

3. MAIN TOPICS (2-4 broader themes discussed, not micro-topics)

4. ACTION ITEMS (if any, with owner/deadline if mentioned)

Format your response exactly as:
DETAILED POINTS:
- Point 1 with speaker name and specific details
- Point 2 with numbers/percentages preserved
- Point 3 with technical terms intact

IMPORTANCE: 7

MAIN TOPICS:
- Broader Topic 1
- Broader Topic 2

ACTION ITEMS:
- Action 1 (Owner: John, Due: Friday)

Transcript:
{chunk_text}
"""


class ChunkProcessor:
    """
    Process individual chunks to extract key information.

    Responsibilities:
    - Extract 3-5 key points per chunk
    - Score importance (1-10) based on decisions/actions
    - Identify main topics discussed
    - Extract action items if present

    Expected behavior:
    - Single LLM call per chunk
    - Returns structured dict for synthesis
    - Automatically filters low-importance content
    """

    def __init__(self, api_key: str, model: str = "o3-mini"):
        self.agent = Agent(f"openai:{model}")
        logger.info("ChunkProcessor initialized", model=model)

    async def process_chunk(
        self, chunk_text: str, chunk_index: int, total_chunks: int
    ) -> dict:
        """Process single chunk and extract information with progress logging."""

        start_time = time.time()

        # Log chunk start with progress indicator
        logger.info(
            "Processing chunk",
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            progress=f"{chunk_index}/{total_chunks}",
            chunk_size_chars=len(chunk_text),
        )

        # Retry logic for API calls
        max_retries = 3
        retry_delay = 1.0  # seconds

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(
                        "Retrying chunk processing",
                        chunk_index=chunk_index,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    await asyncio.sleep(retry_delay * attempt)  # Exponential backoff

                result = await self.agent.run(PROMPT.format(chunk_text=chunk_text))
                parsed_result = self._parse_result(result.output, chunk_text)

                processing_time = time.time() - start_time
                logger.info(
                    "Chunk processed successfully",
                    chunk_index=chunk_index,
                    processing_time_ms=int(processing_time * 1000),
                    importance_score=parsed_result["importance_score"],
                    key_points_count=len(parsed_result["key_points"]),
                    topics_count=len(parsed_result["topics"]),
                    attempts=attempt + 1,
                )

                return parsed_result

            except Exception as e:
                processing_time = time.time() - start_time
                error_msg = str(e)

                if attempt < max_retries - 1:
                    logger.warning(
                        "Chunk processing failed, will retry",
                        chunk_index=chunk_index,
                        attempt=attempt + 1,
                        error=error_msg,
                        processing_time_ms=int(processing_time * 1000),
                        next_retry_delay=retry_delay * (attempt + 1),
                    )
                    continue  # Try again
                else:
                    logger.error(
                        "Chunk processing failed after all retries",
                        chunk_index=chunk_index,
                        error=error_msg,
                        total_attempts=max_retries,
                        processing_time_ms=int(processing_time * 1000),
                    )
                    raise

    def _parse_result(self, llm_output: str, original_text: str) -> dict:
        """Parse LLM response into structured dict with enhanced detail extraction."""
        lines = llm_output.strip().split("\n")
        result = {
            "key_points": [],  # Now contains detailed points with speaker attribution
            "importance_score": 5,
            "topics": [],
            "action_items": [],
            "chunk_text": original_text,
        }

        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("DETAILED POINTS:"):
                current_section = "key_points"
            elif line.startswith("KEY POINTS:"):  # Fallback for old format
                current_section = "key_points"
            elif line.startswith("IMPORTANCE:"):
                try:
                    result["importance_score"] = int(line.split(":")[1].strip())
                except:
                    result["importance_score"] = 5
            elif line.startswith("MAIN TOPICS:"):
                current_section = "topics"
            elif line.startswith("TOPICS:"):  # Fallback for old format
                current_section = "topics"
            elif line.startswith("ACTION ITEMS:"):
                current_section = "action_items"
            elif line.startswith("- ") and current_section:
                point = line[2:].strip()
                # Only add non-empty points
                if point:
                    result[current_section].append(point)

        # Log parsing results for debugging
        logger.debug(
            "Parsed chunk result",
            key_points_extracted=len(result["key_points"]),
            topics_extracted=len(result["topics"]),
            action_items_extracted=len(result["action_items"]),
            importance_score=result["importance_score"],
        )

        return result

    async def process_chunks_parallel(
        self,
        chunks: list[str],
        max_concurrent: int = 3,  # Reduced from 5 to 3 for stability
    ) -> list[dict]:
        """Process multiple chunks in parallel with rate limiting and progress tracking."""
        import time

        start_time = time.time()
        semaphore = asyncio.Semaphore(max_concurrent)
        total_chunks = len(chunks)

        logger.info(
            "Starting parallel chunk processing",
            total_chunks=total_chunks,
            max_concurrent=max_concurrent,
        )

        async def process_one(chunk: str, index: int):
            async with semaphore:
                return await self.process_chunk(
                    chunk, chunk_index=index + 1, total_chunks=total_chunks
                )

        # Create tasks with chunk indices for progress tracking
        tasks = [process_one(chunk, i) for i, chunk in enumerate(chunks)]

        # Use gather with return_exceptions=True to handle failures gracefully
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        processed_results = []
        successful_chunks = 0
        failed_chunks = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_chunks += 1
                logger.error(
                    "Chunk processing failed",
                    chunk_index=i + 1,
                    error=str(result),
                    error_type=type(result).__name__,
                )
                # Create a fallback result to maintain structure
                fallback_result = {
                    "key_points": [f"Processing failed: {str(result)}"],
                    "importance_score": 3,  # Low importance for failed chunks
                    "topics": ["Processing Error"],
                    "action_items": [],
                    "chunk_text": chunks[i][:200] + "..."
                    if len(chunks[i]) > 200
                    else chunks[i],
                }
                processed_results.append(fallback_result)
            else:
                successful_chunks += 1
                processed_results.append(result)

        processing_time = time.time() - start_time

        # Calculate average importance only from successful chunks
        successful_results = [r for r in processed_results if r["importance_score"] > 3]
        avg_importance = (
            sum(r["importance_score"] for r in successful_results)
            / len(successful_results)
            if successful_results
            else 5.0
        )

        logger.info(
            "Parallel chunk processing completed",
            total_chunks=total_chunks,
            successful_chunks=successful_chunks,
            failed_chunks=failed_chunks,
            success_rate=f"{successful_chunks/total_chunks*100:.1f}%",
            avg_importance=round(avg_importance, 2),
            total_processing_time_ms=int(processing_time * 1000),
            avg_time_per_chunk_ms=int((processing_time / total_chunks) * 1000),
        )

        if successful_chunks == 0:
            logger.error("All chunks failed to process")
            raise Exception(f"All {total_chunks} chunks failed to process")

        if failed_chunks > 0:
            logger.warning(
                f"Partial processing completed: {failed_chunks}/{total_chunks} chunks failed"
            )

        return processed_results
