"""Business logic for transcript cleaning - uses pure Pydantic AI agents."""

import time
import structlog

from agents.transcript.cleaner import cleaning_agent, get_model_settings
from models.agents import CleaningResult
from models.transcript import VTTChunk

logger = structlog.get_logger(__name__)


class TranscriptCleaningService:
    """Orchestrates transcript cleaning using pure Pydantic AI agents."""
    
    def __init__(self, model: str = "o3-mini"):
        """Initialize service with model configuration.
        
        Args:
            model: Model name to use (e.g., 'o3-mini', 'gpt-4')
        """
        self.model = model
        logger.info(
            "TranscriptCleaningService initialized",
            model=model,
            supports_temperature=not model.startswith("o3"),
            supports_max_tokens=not model.startswith("o3"),
        )

    async def clean_chunk(self, chunk: VTTChunk, prev_text: str = "") -> CleaningResult:
        """Clean a transcript chunk using the pure cleaning agent.
        
        Args:
            chunk: VTT chunk to clean
            prev_text: Previous context for flow preservation
            
        Returns:
            CleaningResult with cleaned text, confidence, and changes
        """
        start_time = time.time()
        context = prev_text[-200:] if prev_text else ""

        # Log detailed context for monitoring
        chunk_speakers = list({entry.speaker for entry in chunk.entries})
        chunk_text = chunk.to_transcript_text()

        logger.info(
            "Starting chunk cleaning",
            chunk_id=chunk.chunk_id,
            token_count=chunk.token_count,
            entries_count=len(chunk.entries),
            unique_speakers=len(chunk_speakers),
            speakers=chunk_speakers,
            text_length=len(chunk_text),
            context_length=len(context),
            model=self.model,
            text_preview=chunk_text[:100].replace("\n", " ") + "..."
            if len(chunk_text) > 100
            else chunk_text,
        )

        # Prepare user prompt with context
        user_prompt = f"""Previous context for flow: ...{context}

Current chunk to clean:
{chunk.to_transcript_text()}

Return JSON with cleaned_text, confidence, and changes_made."""

        try:
            logger.debug(
                "Starting chunk cleaning",
                chunk_id=chunk.chunk_id,
                token_count=chunk.token_count,
                model=self.model,
            )

            # Get appropriate model settings
            settings = get_model_settings(self.model)

            api_call_start = time.time()
            logger.debug(
                "Sending request to OpenAI API",
                chunk_id=chunk.chunk_id,
                model=self.model,
            )

            # Use the pure global agent with runtime model override if needed
            if self.model != "o3-mini":
                # Override model using Pydantic AI's override method
                with cleaning_agent.override(model=f"openai:{self.model}") as overridden_agent:
                    result = await overridden_agent.run(
                        user_prompt, 
                        model_settings=settings
                    )
            else:
                # Use default model
                result = await cleaning_agent.run(user_prompt, model_settings=settings)

            api_call_time = time.time() - api_call_start
            processing_time = time.time() - start_time

            # Enhanced success logging with quality metrics
            original_length = len(chunk_text)
            cleaned_length = len(result.output.cleaned_text)
            length_change_pct = (
                ((cleaned_length - original_length) / original_length * 100)
                if original_length > 0
                else 0
            )

            logger.info(
                "Chunk cleaning completed successfully",
                chunk_id=chunk.chunk_id,
                processing_time_ms=int(processing_time * 1000),
                api_call_time_ms=int(api_call_time * 1000),
                confidence=result.output.confidence,
                changes_count=len(result.output.changes_made),
                changes_made=result.output.changes_made[
                    :3
                ],  # First 3 changes for monitoring
                text_metrics={
                    "original_length": original_length,
                    "cleaned_length": cleaned_length,
                    "length_change_pct": round(length_change_pct, 1),
                    "compression_ratio": round(cleaned_length / original_length, 3)
                    if original_length > 0
                    else 1.0,
                },
                model=self.model,
            )

            return result.output

        except Exception as e:
            logger.error(
                "Chunk cleaning failed",
                chunk_id=chunk.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model,
            )
            raise