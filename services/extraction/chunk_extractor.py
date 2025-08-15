"""Universal chunk extraction using structured output and tenacity retry."""

import asyncio

from pydantic_ai import Agent
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models.intelligence import ChunkInsights

logger = structlog.get_logger(__name__)

# Universal extraction prompt that works for ANY meeting type
UNIVERSAL_EXTRACTION_PROMPT = """
Extract comprehensive insights from this conversation segment.

Your goal: Capture EVERYTHING important - names, numbers, decisions, technical details,
context, and relationships. This could be any type of meeting - technical, business,
creative, or casual.

Extract:
1. INSIGHTS: 5-12 important statements that preserve:
   - WHO said it (speaker attribution)
   - WHAT exactly (specific details, numbers, technical terms)
   - WHY it matters (context and implications)
   - Examples:
     * "John proposed increasing the budget by 15% for Q3"
     * "Sarah explained the API returns 70% accuracy when threshold > 2%"
     * "Team agreed to use PostgreSQL over MongoDB for scaling reasons"

2. IMPORTANCE: Rate 1-10 based on decisions, commitments, or strategic value

3. THEMES: 1-3 broad themes (e.g., "Budget Planning", "Technical Architecture")

4. ACTIONS: Any commitments or next steps with owner if mentioned

Conversation:
{text}
"""


class ChunkExtractor:
    """Universal chunk extraction with structured output and retry logic."""

    def __init__(self, model: str = "o3-mini"):
        # Use Pydantic AI structured output with built-in validation retries
        self.agent = Agent(
            f"openai:{model}",
            output_type=ChunkInsights,
            retries=2,  # Automatic retry on validation failure
        )
        logger.info("ChunkExtractor initialized", model=model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
    )
    async def extract_insights(
        self, text: str, chunk_index: int, total_chunks: int
    ) -> ChunkInsights:
        """Extract insights from a single chunk with automatic retry."""
        logger.info(
            "Extracting insights",
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            progress=f"{chunk_index}/{total_chunks}",
            chunk_size_chars=len(text),
        )

        try:
            result = await self.agent.run(UNIVERSAL_EXTRACTION_PROMPT.format(text=text))
            insights = result.output

            logger.info(
                "Insights extracted successfully",
                chunk_index=chunk_index,
                importance=insights.importance,
                insights_count=len(insights.insights),
                themes_count=len(insights.themes),
                actions_count=len(insights.actions),
            )

            return insights

        except Exception as e:
            logger.error(
                "Insight extraction failed",
                chunk_index=chunk_index,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def extract_all_insights(
        self, semantic_chunks: list[str], max_concurrent: int = 3
    ) -> list[ChunkInsights]:
        """Extract insights from all chunks in parallel with rate limiting."""
        semaphore = asyncio.Semaphore(max_concurrent)
        total_chunks = len(semantic_chunks)

        logger.info(
            "Starting parallel insight extraction",
            total_chunks=total_chunks,
            max_concurrent=max_concurrent,
        )

        async def extract_one(chunk: str, index: int):
            async with semaphore:
                return await self.extract_insights(chunk, index + 1, total_chunks)

        # Process all chunks with error handling
        tasks = [extract_one(chunk, i) for i, chunk in enumerate(semantic_chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Separate successful results from exceptions
        successful_insights = []
        failed_count = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(
                    "Chunk extraction failed",
                    chunk_index=i + 1,
                    error=str(result),
                    error_type=type(result).__name__,
                )
                # Create fallback insights for failed chunks
                fallback = ChunkInsights(
                    insights=[f"Processing failed: {str(result)}"],
                    importance=3,  # Low importance for failed chunks
                    themes=["Processing Error"],
                    actions=[],
                )
                successful_insights.append(fallback)
            else:
                successful_insights.append(result)

        logger.info(
            "Parallel insight extraction completed",
            total_chunks=total_chunks,
            successful_chunks=total_chunks - failed_count,
            failed_chunks=failed_count,
            success_rate=f"{((total_chunks - failed_count) / total_chunks) * 100:.1f}%",
        )

        return successful_insights
