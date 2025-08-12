"""AI agents for transcript cleaning and review using Pydantic AI."""

import os
import time

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModelSettings
import structlog

from models.agents import CleaningResult, ReviewResult
from models.vtt import VTTChunk

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

# Instructions (preserved from original system prompts)
CLEANER_INSTRUCTIONS = """You are an expert transcript editor specializing in meeting transcripts.

Your task: Clean speech-to-text errors while preserving speaker attribution and conversational flow.

Rules:
1. NEVER change speaker names or labels
2. Fix grammar, spelling, and punctuation
3. Remove filler words (um, uh, like, you know)
4. Maintain conversational tone and meaning
5. Preserve technical terms and proper nouns
6. Keep the same general length and structure

Output format: JSON with exactly these fields:
- "cleaned_text": The improved transcript text
- "confidence": Float 0.0-1.0 indicating your confidence in the improvements
- "changes_made": Array of strings describing what was changed"""

REVIEWER_INSTRUCTIONS = """You are an expert transcript quality reviewer with deep expertise in meeting transcription standards.

Your task: Evaluate the quality of transcript cleaning with rigorous standards.

Evaluation Criteria:
1. Speaker Attribution (25%): Names preserved exactly, no confusion
2. Meaning Preservation (30%): Original intent and content maintained
3. Grammar & Clarity (25%): Proper grammar, clear sentence structure
4. Flow & Naturalness (20%): Conversational tone, natural transitions

Quality Scoring:
- 0.9-1.0: Excellent - Ready for publication
- 0.8-0.89: Good - Minor issues, acceptable
- 0.7-0.79: Fair - Some issues, needs review
- 0.6-0.69: Poor - Significant problems
- Below 0.6: Unacceptable - Major errors

Output format: JSON with exactly these fields:
- "quality_score": Float 0.0-1.0 overall quality assessment
- "issues": Array of specific problems found (empty if none)
- "accept": Boolean whether cleaning meets quality standards (score >= 0.7)"""


class TranscriptCleaner:
    """Manages Pydantic AI agent for cleaning VTT chunks with automatic retry on validation failure."""

    def __init__(self, api_key: str | None = None, model: str = "o3-mini"):
        """Creates agent using environment OPENAI_API_KEY or provided key, configures with CleaningResult output."""
        # Use environment variable if no key provided (Pydantic AI best practice)
        if api_key:  # Only override if explicitly provided
            os.environ["OPENAI_API_KEY"] = api_key

        self.model_name = model
        self.agent = Agent(
            f"openai:{model}",  # Shorthand format recommended by docs
            output_type=CleaningResult,
            system_prompt=CLEANER_INSTRUCTIONS,
            retries=3,  # Built-in retry on validation failure
        )

        logger.info(
            "TranscriptCleaner initialized",
            model=model,
            supports_temperature=not model.startswith("o3"),
            supports_max_tokens=not model.startswith("o3"),
        )

    async def clean_chunk(self, chunk: VTTChunk, prev_text: str = "") -> CleaningResult:
        """Runs agent with chunk context, returns validated CleaningResult, logs metrics."""
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
            model=self.model_name,
            text_preview=chunk_text[:100].replace("\n", " ") + "..."
            if len(chunk_text) > 100
            else chunk_text,
        )

        user_prompt = f"""Previous context for flow: ...{context}

Current chunk to clean:
{chunk.to_transcript_text()}

Return JSON with cleaned_text, confidence, and changes_made."""

        try:
            logger.debug(
                "Starting chunk cleaning",
                chunk_id=chunk.chunk_id,
                token_count=chunk.token_count,
                model=self.model_name,
            )

            # Use model settings for non-o3 models (temperature not supported in o3)
            settings = (
                None
                if self.model_name.startswith("o3")
                else OpenAIModelSettings(temperature=0.3, max_tokens=1000)
            )

            api_call_start = time.time()
            logger.debug(
                "Sending request to OpenAI API",
                chunk_id=chunk.chunk_id,
                model=self.model_name,
            )

            result = await self.agent.run(user_prompt, model_settings=settings)

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
                model=self.model_name,
            )

            return result.output

        except Exception as e:
            logger.error(
                "Chunk cleaning failed",
                chunk_id=chunk.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model_name,
            )
            raise


class TranscriptReviewer:
    """Manages Pydantic AI agent for reviewing cleaned transcripts with quality assessment."""

    def __init__(self, api_key: str | None = None, model: str = "o3-mini"):
        """Creates agent using environment OPENAI_API_KEY or provided key, configures with ReviewResult output."""
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        self.model_name = model
        self.agent = Agent(
            f"openai:{model}",
            output_type=ReviewResult,
            system_prompt=REVIEWER_INSTRUCTIONS,
            retries=3,
        )

    async def review_chunk(self, original: VTTChunk, cleaned: str) -> ReviewResult:
        """Runs agent comparing original vs cleaned, returns validated ReviewResult with accept decision."""
        start_time = time.time()

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
                model=self.model_name,
            )

            # Use model settings for non-o3 models (temperature not supported in o3)
            settings = (
                None
                if self.model_name.startswith("o3")
                else OpenAIModelSettings(temperature=0.2, max_tokens=500)
            )

            result = await self.agent.run(user_prompt, model_settings=settings)
            processing_time = time.time() - start_time

            logger.info(
                "Chunk review completed",
                chunk_id=original.chunk_id,
                processing_time_ms=int(processing_time * 1000),
                quality_score=result.output.quality_score,
                issues_count=len(result.output.issues),
                accepted=result.output.accept,
                model=self.model_name,
            )

            return result.output

        except Exception as e:
            logger.error(
                "Chunk review failed",
                chunk_id=original.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model_name,
            )
            raise
