"""Universal chunk extraction using structured output and tenacity retry."""

import asyncio

from pydantic_ai import Agent, RunContext
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models.intelligence import ChunkInsights

logger = structlog.get_logger(__name__)

# Universal extraction instructions that work for ANY meeting type
UNIVERSAL_EXTRACTION_INSTRUCTIONS = """
Extract comprehensive insights from this conversation segment.

Your goal: Capture EVERYTHING important - names, numbers, decisions, technical details,
context, and relationships. This could be any type of meeting - technical, business,
creative, or casual.

Extract:
1. INSIGHTS: 8-15 important statements that preserve:
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
"""


class ChunkExtractor:
    """Universal chunk extraction with structured output and retry logic."""

    def __init__(self, model: str = "o3-mini"):
        self.agent = Agent(
            f"openai:{model}",
            output_type=ChunkInsights,
            instructions=UNIVERSAL_EXTRACTION_INSTRUCTIONS,
            deps_type=dict,  # Accept context dictionary as dependency
            retries=2,
        )

        # Add dynamic instructions based on meeting context
        @self.agent.instructions
        def add_context_instructions(ctx: RunContext[dict]) -> str:
            """Add context-specific extraction instructions."""
            context = ctx.deps or {}

            instructions = []

            # Adjust based on chunk position in meeting
            position = context.get("position", "middle")
            if position == "start":
                instructions.append(
                    "This is from the beginning of the meeting. Pay special attention to "
                    "meeting objectives, agenda items, and introductory statements."
                )
            elif position == "end":
                instructions.append(
                    "This is from the end of the meeting. Focus on final decisions, "
                    "action items, next steps, and meeting conclusions."
                )

            # Adjust based on meeting type
            meeting_type = context.get("meeting_type")
            if meeting_type == "technical":
                instructions.append(
                    "This is a technical meeting. Pay special attention to architecture "
                    "decisions, technical specifications, system requirements, and implementation details."
                )
            elif meeting_type == "executive":
                instructions.append(
                    "This is an executive meeting. Focus on strategic decisions, budget discussions, "
                    "high-level planning, and business outcomes."
                )
            elif meeting_type == "standup":
                instructions.append(
                    "This is a standup meeting. Focus on progress updates, blockers, "
                    "and immediate next steps for team members."
                )

            # Adjust based on content characteristics
            if context.get("action_heavy"):
                instructions.append(
                    "This segment is action-heavy. Be extra thorough in identifying "
                    "commitments, assignments, and deliverables with owners and timelines."
                )

            return "\n\n".join(instructions) if instructions else ""

        logger.info(
            "ChunkExtractor initialized",
            model=model,
            supports_dynamic_instructions=True,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    async def extract_insights(
        self,
        text: str,
        chunk_index: int,
        total_chunks: int,
        context: dict | None = None,
    ) -> ChunkInsights:
        """
        Extract insights from a single chunk with automatic retry.

        Args:
            text: The conversation text to extract insights from
            chunk_index: Current chunk number (1-based)
            total_chunks: Total number of chunks being processed
            context: Optional context for dynamic instructions:
                - position: 'start', 'middle', 'end'
                - meeting_type: 'technical', 'executive', 'standup'
                - action_heavy: bool for action-focused content

        Network errors (connection, timeout) are retried via tenacity.
        Validation errors (ModelRetry) are handled by Pydantic AI's built-in retry.
        """
        logger.info(
            "Extracting insights",
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            progress=f"{chunk_index}/{total_chunks}",
            chunk_size_chars=len(text),
        )

        try:
            # Prepare context with chunk position information
            runtime_context = context or {}

            # Auto-detect position if not provided
            if "position" not in runtime_context:
                if chunk_index <= 2:
                    runtime_context["position"] = "start"
                elif chunk_index >= total_chunks - 1:
                    runtime_context["position"] = "end"
                else:
                    runtime_context["position"] = "middle"

            # Pass context as dependencies to enable dynamic instructions
            result = await self.agent.run(text, deps=runtime_context)
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
        self,
        semantic_chunks: list[str],
        max_concurrent: int = 3,
        context: dict | None = None,
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
                return await self.extract_insights(
                    chunk, index + 1, total_chunks, context
                )

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
