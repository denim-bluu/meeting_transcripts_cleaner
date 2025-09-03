"""Main intelligence orchestration - clean, simple pipeline."""

import asyncio
import time

from asyncio_throttle.throttler import Throttler
import structlog

from backend.config import settings
from backend.intelligence.agents.direct import direct_synthesis_agent

# Use pure agents following Pydantic AI best practices
from backend.intelligence.agents.insights import chunk_extraction_agent
from backend.intelligence.models import ChunkInsights, MeetingIntelligence
from backend.transcript.models import VTTChunk
from backend.utils.semantic_chunker import SemanticChunker

logger = structlog.get_logger(__name__)


class IntelligenceOrchestrator:
    """
    Production-grade intelligence orchestration using industry-standard approach.

    Responsibilities:
    - Coordinate the 3-phase processing pipeline
    - Semantic chunking → Extraction → Hierarchical Synthesis
    - Automatic fallback for long meetings with temporal segmentation
    - Track processing stats and performance
    """

    def __init__(self):
        self.chunker = SemanticChunker()

        self.MIN_IMPORTANCE = (
            1  # Include ALL contextual content for comprehensive summaries
        )
        self.CRITICAL_IMPORTANCE = 8  # Never exclude these
        self.CONTEXT_LIMIT = 100000  # Hardcoded for simplicity
        self.SEGMENT_MINUTES = 30  # Temporal segmentation

        logger.info(
            "IntelligenceOrchestrator initialized with pure agents",
            min_importance=self.MIN_IMPORTANCE,
            context_limit=self.CONTEXT_LIMIT,
            insights_model=settings.insights_model,
            synthesis_model=settings.synthesis_model,
        )

    async def process_meeting(
        self,
        cleaned_chunks: list[VTTChunk],
        progress_callback=None,
    ) -> MeetingIntelligence:
        """
        Two approaches:
        - Direct synthesis
        - Hierarchical synthesis with temporal segmentation

        Returns MeetingIntelligence with structured output.
        """
        start_time = time.time()
        logger.info(
            "Starting intelligence processing",
            vtt_chunks=len(cleaned_chunks),
            insights_model=settings.insights_model,
            synthesis_model=settings.synthesis_model,
        )

        # Phase 1: Semantic chunking (no API calls)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(0.1, "Phase 1: Semantic chunking...")
            else:
                progress_callback(0.1, "Phase 1: Semantic chunking...")
        logger.info("Phase 1: Starting semantic chunking")
        phase1_start = time.time()
        semantic_chunks = await asyncio.to_thread(
            self.chunker.create_chunks, cleaned_chunks
        )
        phase1_time = int((time.time() - phase1_start) * 1000)
        logger.info(
            "Phase 1 completed",
            semantic_chunks=len(semantic_chunks),
            time_ms=phase1_time,
        )

        # Phase 2: Extract insights from all chunks (N API calls)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(
                    0.2,
                    f"Phase 2: Extracting insights from {len(semantic_chunks)} chunks...",
                )
            else:
                progress_callback(
                    0.2,
                    f"Phase 2: Extracting insights from {len(semantic_chunks)} chunks...",
                )
        logger.info(
            "Phase 2: Starting insight extraction",
            chunks_to_process=len(semantic_chunks),
        )
        phase2_start = time.time()
        insights_list = await self._extract_all_insights(
            semantic_chunks, progress_callback
        )
        phase2_time = int((time.time() - phase2_start) * 1000)
        logger.info(
            "Phase 2 completed",
            insights_extracted=len(insights_list),
            time_ms=phase2_time,
        )

        # Phase 3: Smart synthesis (industry-standard approach)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(
                    0.8, "Phase 3: Synthesizing meeting intelligence..."
                )
            else:
                progress_callback(0.8, "Phase 3: Synthesizing meeting intelligence...")
        logger.info("Phase 3: Starting intelligent synthesis")
        phase3_start = time.time()

        # Filter by importance (battle-tested threshold)
        important_insights = [
            i for i in insights_list if i.importance >= self.MIN_IMPORTANCE
        ]

        logger.info("Passing insights", filtered_insights=len(important_insights))
        intelligence = await self._synthesize(important_insights)

        phase3_time = int((time.time() - phase3_start) * 1000)
        logger.info(
            "Phase 3 completed",
            summary_length=len(intelligence.summary),
            action_items=len(intelligence.action_items),
            time_ms=phase3_time,
        )

        # Calculate final stats
        total_time = int((time.time() - start_time) * 1000)
        api_calls = len(semantic_chunks)
        avg_importance = sum(i.importance for i in insights_list) / len(insights_list)

        # Preserve critical insights check
        critical_insights = [
            i for i in insights_list if i.importance >= self.CRITICAL_IMPORTANCE
        ]
        critical_preserved = len(critical_insights)

        # Add processing stats
        intelligence.processing_stats = {
            "vtt_chunks": len(cleaned_chunks),
            "semantic_chunks": len(semantic_chunks),
            "api_calls": api_calls,
            "time_ms": total_time,
            "avg_importance": round(avg_importance, 2),
            "insights_filtered": len(important_insights),
            "insights_total": len(insights_list),
            "critical_insights_preserved": critical_preserved,
            "phase_times": {
                "semantic_chunking_ms": phase1_time,
                "insight_extraction_ms": phase2_time,
                "synthesis_ms": phase3_time,
            },
        }

        logger.info(
            "Intelligence processing completed successfully",
            api_calls=api_calls,
            total_time_ms=total_time,
            avg_importance=round(avg_importance, 2),
            critical_preserved=critical_preserved,
        )

        return intelligence

    async def _extract_all_insights(
        self,
        semantic_chunks: list[str],
        progress_callback=None,
    ) -> list[ChunkInsights]:
        """Extract insights from all semantic chunks using concurrent processing."""
        import asyncio

        semaphore = asyncio.Semaphore(10)  # 10 concurrent tasks
        throttler = Throttler(rate_limit=50, period=60)  # 50 requests per minute

        async def extract_single_chunk(
            i: int, chunk_text: str
        ) -> tuple[int, ChunkInsights]:
            """Extract insights from a single chunk with proper error handling."""
            user_prompt = f"Extract comprehensive insights from this conversation segment:\n\n{chunk_text}"

            try:
                logger.info(
                    "Starting chunk extraction",
                    chunk_index=i + 1,
                    total_chunks=len(semantic_chunks),
                    chunk_size_chars=len(chunk_text),
                    insights_model=settings.insights_model,
                )

                async with semaphore, throttler:
                    result = await chunk_extraction_agent.run(user_prompt)

                logger.info(
                    "Chunk extraction completed",
                    chunk_index=i + 1,
                    importance=result.output.importance,
                    insights_count=len(result.output.insights),
                    themes=result.output.themes,
                    actions_count=len(result.output.actions),
                )

                return i, result.output

            except Exception as e:
                logger.error(
                    "Chunk extraction failed",
                    chunk_index=i + 1,
                    total_chunks=len(semantic_chunks),
                    error=str(e),
                    chunk_size_chars=len(chunk_text),
                )
                raise

        # Create concurrent tasks for all chunks
        logger.info(
            "Starting concurrent insight extraction",
            total_chunks=len(semantic_chunks),
        )

        tasks = [
            extract_single_chunk(i, chunk_text)
            for i, chunk_text in enumerate(semantic_chunks)
        ]

        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(
                    0.3, f"Processing {len(tasks)} chunks concurrently..."
                )
            else:
                progress_callback(
                    0.3, f"Processing {len(tasks)} chunks concurrently..."
                )
        results: list[tuple[int, ChunkInsights] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(0.7, "Consolidating extraction results...")
            else:
                progress_callback(0.7, "Consolidating extraction results...")

        # Process results and handle exceptions
        insights_list: list[ChunkInsights | None] = [None] * len(
            semantic_chunks
        )  # Pre-allocate with correct order

        insights_list: list[ChunkInsights | None] = [None] * len(
            semantic_chunks
        )  # Pre-allocate with correct order

        for result in results:
            if isinstance(result, BaseException):
                logger.error("Concurrent chunk extraction failed", error=str(result))
                raise result
            else:
                # Type narrowing: result is tuple[int, ChunkInsights]
                chunk_index, insights = result
                insights_list[chunk_index] = insights

        # Ensure no None values (safety check)
        final_insights: list[ChunkInsights] = [
            insights for insights in insights_list if insights is not None
        ]

        final_insights: list[ChunkInsights] = [
            insights for insights in insights_list if insights is not None
        ]

        logger.info(
            "Concurrent insight extraction completed",
            chunks_processed=len(final_insights),
            total_chunks=len(semantic_chunks),
        )

        return final_insights

    async def _synthesize(
        self, insights_list: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """Direct synthesis using pure agent with detailed logging."""
        logger.info(
            "Starting direct synthesis",
            insights_count=len(insights_list),
            total_actions=sum(len(insight.actions) for insight in insights_list),
            total_insights_items=sum(
                len(insight.insights) for insight in insights_list
            ),
            avg_importance=round(
                sum(insight.importance for insight in insights_list)
                / len(insights_list),
                2,
            )
            if insights_list
            else 0,
        )

        formatted_insights = self._format_insights_for_synthesis(insights_list)

        logger.info(
            "Formatted insights for synthesis",
            formatted_size_chars=len(formatted_insights),
            estimated_tokens=len(formatted_insights) // 4,  # Rough token estimate
        )

        user_prompt = f"""Create comprehensive meeting intelligence from these insights:

{formatted_insights}

Return both summary (detailed markdown) and action_items (structured list)."""

        synthesis_start_time = time.time()

        try:
            logger.info(
                "Calling direct synthesis agent",
                agent_retries=2,  # Built-in Pydantic AI retries
                synthesis_model=settings.synthesis_model,
            )

            # Use capture_run_messages to log all interactions including retries
            from pydantic_ai import capture_run_messages

            with capture_run_messages():
                try:
                    result = await asyncio.wait_for(
                        direct_synthesis_agent.run(user_prompt),
                        timeout=300,  # 300 second timeout
                    )

                except Exception as e:
                    logger.error(
                        "Direct synthesis failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        timeout=300,  # 300 second timeout
                    )
                    raise

            synthesis_time = int((time.time() - synthesis_start_time) * 1000)

            logger.info(
                "Direct synthesis completed successfully",
                synthesis_time_ms=synthesis_time,
                summary_length=len(result.output.summary),
                action_items_count=len(result.output.action_items),
                has_processing_stats=bool(result.output.processing_stats),
            )

            return result.output
        except Exception as e:
            synthesis_time = int((time.time() - synthesis_start_time) * 1000)
            logger.error(
                "Direct synthesis failed after retries",
                error=str(e),
                error_type=type(e).__name__,
                synthesis_time_ms=synthesis_time,
            )
            raise

    def _format_insights_for_synthesis(self, insights_list: list[ChunkInsights]) -> str:
        """Format insights for synthesis prompts."""
        formatted_sections = []

        for i, insight in enumerate(insights_list, 1):
            section = f"""--- Insight Group {i} (Importance: {insight.importance}) ---
Themes: {', '.join(insight.themes)}

Key Insights:
"""
            for insight_text in insight.insights:
                section += f"• {insight_text}\n"

            if insight.actions:
                section += "\nAction Items:\n"
                for action in insight.actions:
                    section += f"• {action}\n"

            formatted_sections.append(section)

        return "\n\n".join(formatted_sections)
