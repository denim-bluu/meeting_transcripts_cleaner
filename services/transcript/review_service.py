"""Business logic for transcript review - uses pure Pydantic AI agents."""

import time
import structlog

from agents.transcript.reviewer import review_agent, get_model_settings
from models.agents import ReviewResult
from models.transcript import VTTChunk

logger = structlog.get_logger(__name__)


class TranscriptReviewService:
    """Orchestrates transcript review using pure Pydantic AI agents."""
    
    def __init__(self, model: str = "o3-mini"):
        """Initialize service with model configuration.
        
        Args:
            model: Model name to use (e.g., 'o3-mini', 'gpt-4')
        """
        self.model = model
        logger.info("TranscriptReviewService initialized", model=model)

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
                model=self.model,
            )

            # Get appropriate model settings
            settings = get_model_settings(self.model)

            # Use the pure global agent with runtime model override if needed
            if self.model != "o3-mini":
                # Override model using Pydantic AI's override method
                with review_agent.override(model=f"openai:{self.model}") as overridden_agent:
                    result = await overridden_agent.run(
                        user_prompt, 
                        model_settings=settings
                    )
            else:
                # Use default model
                result = await review_agent.run(user_prompt, model_settings=settings)

            processing_time = time.time() - start_time

            logger.info(
                "Chunk review completed",
                chunk_id=original.chunk_id,
                processing_time_ms=int(processing_time * 1000),
                quality_score=result.output.quality_score,
                issues_count=len(result.output.issues),
                accepted=result.output.accept,
                model=self.model,
            )

            return result.output

        except Exception as e:
            logger.error(
                "Chunk review failed",
                chunk_id=original.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model,
            )
            raise