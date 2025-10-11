"""Main intelligence orchestration - direct synthesis only."""

import asyncio
import time

import structlog

from backend.config import settings
from backend.intelligence.agents.direct import direct_synthesis_agent
from backend.intelligence.models import MeetingIntelligence
from backend.transcript.models import VTTChunk

logger = structlog.get_logger(__name__)


class IntelligenceOrchestrator:
    """Direct synthesis orchestration from transcript text.

    Responsibilities:
    - Semantic chunking → Direct Synthesis (no intermediate extraction)
    - Track processing stats and performance
    """

    def __init__(self):
        logger.info(
            "IntelligenceOrchestrator initialized (direct synthesis only)",
            synthesis_model=settings.synthesis_model,
        )

    async def process_meeting(
        self,
        cleaned_chunks: list[VTTChunk],
        progress_callback=None,
    ) -> MeetingIntelligence:
        """Prepare transcript text and run direct synthesis.

        Returns MeetingIntelligence with structured output.
        """
        start_time = time.time()
        logger.info(
            "Starting intelligence processing",
            vtt_chunks=len(cleaned_chunks),
            synthesis_model=settings.synthesis_model,
        )

        # Phase 1: Build full transcript text from VTT chunks
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(0.1, "Phase 1: Preparing transcript text...")
            else:
                progress_callback(0.1, "Phase 1: Preparing transcript text...")
        logger.info("Phase 1: Building transcript text from chunks")
        phase1_start = time.time()
        transcript_text = await asyncio.to_thread(self._build_transcript_text, cleaned_chunks)
        phase1_time = int((time.time() - phase1_start) * 1000)
        logger.info(
            "Phase 1 completed",
            text_length_chars=len(transcript_text),
            time_ms=phase1_time,
        )

        # Phase 2: Direct synthesis from transcript segments
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(0.6, "Phase 2: Direct synthesis from transcript...")
            else:
                progress_callback(0.6, "Phase 2: Direct synthesis from transcript...")
        logger.info("Phase 2: Starting direct synthesis")
        phase2_start = time.time()
        intelligence = await self._synthesize_from_transcript_text(transcript_text)
        phase2_time = int((time.time() - phase2_start) * 1000)
        logger.info(
            "Phase 2 completed",
            summary_length=len(intelligence.summary),
            action_items=len(intelligence.action_items),
            time_ms=phase2_time,
        )

        # Calculate final stats
        total_time = int((time.time() - start_time) * 1000)
        api_calls = 1  # single direct synthesis call

        # Add processing stats
        intelligence.processing_stats = {
            "vtt_chunks": len(cleaned_chunks),
            "api_calls": api_calls,
            "time_ms": total_time,
            "phase_times": {
                "transcript_prep_ms": phase1_time,
                "synthesis_ms": phase2_time,
            },
        }

        logger.info(
            "Intelligence processing completed successfully",
            api_calls=api_calls,
            total_time_ms=total_time,
        )

        return intelligence
    def _build_transcript_text(self, chunks: list[VTTChunk]) -> str:
        """Concatenate VTT chunks into a single transcript string."""
        if not chunks:
            return ""
        parts: list[str] = []
        for ch in chunks:
            parts.append(ch.to_transcript_text())
        return "\n\n".join(parts)

    async def _synthesize_from_transcript_text(self, transcript_text: str) -> MeetingIntelligence:
        """Run the direct synthesis agent on the full transcript text."""
        logger.info(
            "Prepared transcript for synthesis",
            formatted_size_chars=len(transcript_text),
            estimated_tokens=len(transcript_text) // 4,
        )

        user_prompt = (
            "Create comprehensive meeting intelligence from the following transcript.\n\n"
            + transcript_text
            + "\n\nReturn both summary (detailed markdown) and action_items (structured list)."
        )

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
