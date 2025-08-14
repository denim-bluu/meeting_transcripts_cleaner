import asyncio

from pydantic_ai import Agent
import structlog

logger = structlog.get_logger(__name__)


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

    async def process_chunk(self, chunk_text: str) -> dict:
        """Process single chunk and extract information."""
        prompt = f"""
        Analyze this meeting transcript segment and extract:

        1. KEY POINTS (max 5 bullet points of important content)
        2. IMPORTANCE SCORE (1-10 based on decisions made, action items, strategic discussions)
        3. TOPICS (main subjects discussed, max 3)
        4. ACTION ITEMS (if any, with owner/deadline if mentioned)

        Format your response exactly as:
        KEY POINTS
        - Point 1
        - Point 2

        IMPORTANCE: 7

        TOPICS:
        - Topic 1
        - Topic 2

        ACTION ITEMS:
        - Action 1 (Owner: John, Due: Friday)

        Transcript:
        {chunk_text}
        """

        result = await self.agent.run(prompt)
        return self._parse_result(result.output, chunk_text)

    def _parse_result(self, llm_output: str, original_text: str) -> dict:
        """Parse LLM response into structured dict."""
        lines = llm_output.strip().split("\n")
        result = {
            "key_points": [],
            "importance_score": 5,
            "topics": [],
            "action_items": [],
            "chunk_text": original_text,
        }

        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("KEY POINTS:"):
                current_section = "key_points"
            elif line.startswith("IMPORTANCE:"):
                try:
                    result["importance_score"] = int(line.split(":")[1].strip())
                except:
                    result["importance_score"] = 5
            elif line.startswith("TOPICS:"):
                current_section = "topics"
            elif line.startswith("ACTION ITEMS:"):
                current_section = "action_items"
            elif line.startswith("- ") and current_section:
                result[current_section].append(line[2:])

        return result

    async def process_chunks_parallel(
        self, chunks: list[str], max_concurrent: int = 5
    ) -> list[dict]:
        """Process multiple chunks in parallel with rate limiting."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_one(chunk):
            async with semaphore:
                return await self.process_chunk(chunk)

        results = await asyncio.gather(*[process_one(chunk) for chunk in chunks])

        logger.info(
            "Parallel chunk processing completed",
            total_chunks=len(chunks),
            avg_importance=sum(r["importance_score"] for r in results) / len(results),
        )

        return results
