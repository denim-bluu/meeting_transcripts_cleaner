"""Business logic for transcript review - uses pure Pydantic AI agents."""

import time

import structlog

from backend.config import settings
from backend.transcript.agents.reviewer import review_agent
from backend.transcript.models import ReviewResult, VTTChunk

logger = structlog.get_logger(__name__)


class TranscriptReviewService:
    """Orchestrates transcript review using pure Pydantic AI agents."""

    def __init__(self):
        """Initialize service using agent's internal configuration."""
        logger.info(
            "TranscriptReviewService initialized",
            review_model=settings.review_model,
        )

    async def review_chunk(self, original: VTTChunk, cleaned: str) -> ReviewResult:
        """Review a cleaned transcript chunk using the pure review agent.

        Args:
            original: Original VTT chunk
            cleaned: Cleaned transcript text

        Returns:
            ReviewResult with quality assessment and acceptance decision
        """
        start_time = time.time()

        # Prepare user prompt
        user_prompt = f"""Original transcript:
{original.to_transcript_text()}

Cleaned version:
{cleaned}

Evaluate the cleaning quality and return JSON with quality_score, issues, and accept."""

        try:
            logger.debug(
                "Starting chunk review",
                chunk_id=original.chunk_id,
                original_length=len(original.to_transcript_text()),
                cleaned_length=len(cleaned),
                review_model=settings.review_model,
            )

            # Run review agent using its internal configuration
            result = await review_agent.run(user_prompt)

            processing_time = time.time() - start_time

            logger.info(
                "Chunk review completed",
                chunk_id=original.chunk_id,
                processing_time_ms=int(processing_time * 1000),
                review_model=settings.review_model,
                quality_score=result.output.quality_score,
                issues_count=len(result.output.issues),
                accepted=result.output.accept,
            )

            return result.output

        except Exception as e:
            logger.error(
                "Chunk review failed",
                chunk_id=original.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
            )
            raise
