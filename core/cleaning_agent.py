"""
Cleaning Agent implementation for the dual-agent transcript cleaning system.

This agent performs the first stage of cleaning with high accuracy and provides
confidence scoring for progressive review categorization.
"""

import time

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.settings import ModelSettings
import structlog

from config import get_agents_config, get_openai_config
from models.schemas import CleaningResult, DocumentSegment
from prompts.cleaning import get_cleaning_prompt
from utils.config_manager import get_merged_agent_config

load_dotenv()


logger = structlog.get_logger(__name__)


class CleaningAgent:
    """First-stage cleaning agent for transcript processing."""

    def __init__(self) -> None:
        """Initialize the cleaning agent with configuration."""
        # Use merged config that includes session overrides
        try:
            agents_config = get_merged_agent_config()
        except Exception:
            # Fallback to base config if overrides fail
            agents_config = get_agents_config()

        openai_config = get_openai_config()

        self.model_name = agents_config.cleaning_model
        self.temperature = agents_config.cleaning_temperature
        self.max_tokens = openai_config.max_tokens
        self.max_retries = openai_config.max_retries

        from pydantic_ai.providers.openai import OpenAIProvider
        provider = OpenAIProvider(api_key=openai_config.api_key)
        self.model = OpenAIModel(self.model_name, provider=provider)

        model_settings = ModelSettings(
            temperature=self.temperature,
        )

        self.agent: Agent[None, CleaningResult] = Agent(
            model=self.model,
            output_type=CleaningResult,
            system_prompt="""
            You are a Meeting Transcript Cleaning Agent, the first stage in a dual-agent system achieving 97-98% accuracy. Your role is to clean transcripts while preserving all original meaning, speaker voice, and content completeness.

            Core responsibilities:
            • Clean grammar, spelling, punctuation without altering meaning
            • Remove filler words (um, uh) unless contextually meaningful
            • Fix incomplete sentences while preserving speaker tone
            • Standardize formatting and speaker attributions
            • Document all changes transparently

            Critical constraints:
            • NEVER summarize, condense, or paraphrase - preserve everything
            • NEVER alter core meaning or speaker intent
            • NEVER add information not in original
            • NEVER remove important context or details
            • NEVER generalize technical specifics

            Output JSON with: segment_id, cleaned_text, changes_made
            """,
            model_settings=model_settings,
            retries=self.max_retries,
        )

        logger.info(
            "Cleaning agent initialized",
            # Key identifier (flat)
            agent_type="cleaning",
            # Configuration (grouped)
            ai_config={
                "model": self.model_name,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )

    async def clean_segment(
        self, segment: DocumentSegment, context: dict[str, str] | None = None
    ) -> CleaningResult:
        """
        Clean a single transcript segment.

        Args:
            segment: The document segment to clean
            context: Optional context information with 'previous' and 'following' keys

        Returns:
            CleaningResult with cleaned text and metadata

        Raises:
            Exception: If cleaning fails after all retries
        """
        start_time = time.time()

        # Prepare context
        previous_context = context.get("previous", "") if context else ""
        following_context = context.get("following", "") if context else ""

        # Generate the cleaning prompt
        prompt = get_cleaning_prompt(
            text_content=segment.content,
            segment_number=segment.sequence_number,
            total_segments=1,  # Will be updated by caller if needed
            token_count=segment.token_count,
            segment_id=segment.id,
            previous_context=previous_context,
            following_context=following_context,
        )

        logger.debug(
            "Cleaning segment",
            segment_id=segment.id,
            token_count=segment.token_count,
            phase="cleaning",
        )

        # Attempt cleaning with retries
        for attempt in range(self.max_retries + 1):
            try:
                # Call the PydanticAI agent with correct token parameter for o3 models
                run_settings = ModelSettings()
                run_settings["max_tokens"] = self.max_tokens

                agent_result = await self.agent.run(prompt, model_settings=run_settings)

                # Get the structured output
                result = agent_result.output

                # Add metadata that might not be included in the output
                processing_time = (time.time() - start_time) * 1000

                # Create a new result with updated metadata if needed
                result_data = result.model_dump()
                if not result_data.get("segment_id"):
                    result_data["segment_id"] = segment.id
                if result_data.get("processing_time_ms") is None:
                    result_data["processing_time_ms"] = processing_time
                if not result_data.get("model_used"):
                    result_data["model_used"] = self.model_name

                # Create updated result
                result = CleaningResult(**result_data)

                # Validate the result
                self._validate_cleaning_result(segment, result)

                logger.info(
                    "Segment cleaned successfully",
                    segment_id=segment.id,
                    changes_count=len(result.changes_made),
                    processing_time_ms=processing_time,
                    phase="cleaning",
                )

                return result

            except Exception as e:
                logger.error(
                    "Unexpected error cleaning segment",
                    segment_id=segment.id,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1,
                    error=str(e),
                    phase="cleaning",
                )
                if attempt == self.max_retries:
                    raise Exception(
                        f"Cleaning failed after {self.max_retries + 1} attempts: {e}"
                    ) from e

                await self._wait_with_backoff(attempt)

        # This should never be reached due to the exception handling above
        # But add a fallback just in case
        raise Exception(f"Unable to clean segment {segment.id} after all attempts")

    def _validate_cleaning_result(
        self, original_segment: DocumentSegment, result: CleaningResult
    ) -> None:
        """
        Validate that the cleaning result is reasonable.

        Args:
            original_segment: Original segment that was cleaned
            result: Cleaning result to validate

        Raises:
            ValueError: If the result fails validation
        """
        # Check that cleaned text exists and isn't empty
        if not result.cleaned_text or not result.cleaned_text.strip():
            raise ValueError("Cleaned text is empty")

        # Validate that changes_made is populated if there are significant changes
        if (
            len(result.cleaned_text.strip()) != len(original_segment.content.strip())
            and not result.changes_made
        ):
            logger.warning(
                "Significant text changes without documented changes",
                segment_id=original_segment.id,
                phase="validation",
                warning_type="undocumented_changes",
            )

        # Check that cleaned text isn't dramatically different in length
        original_len = len(original_segment.content)
        cleaned_len = len(result.cleaned_text)

        # Allow up to 50% change in length
        length_ratio = cleaned_len / original_len if original_len > 0 else 0
        if length_ratio < 0.5 or length_ratio > 2.0:
            logger.warning(
                "Significant length change detected",
                segment_id=original_segment.id,
                original_length=original_len,
                cleaned_length=cleaned_len,
                length_ratio=length_ratio,
                phase="validation",
                warning_type="length_change",
            )

        # Check segment ID matches
        if result.segment_id != original_segment.id:
            raise ValueError(
                f"Segment ID mismatch: {result.segment_id} vs {original_segment.id}"
            )

    async def _wait_with_backoff(self, attempt: int) -> None:
        """
        Wait with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)
        """
        import asyncio

        wait_time = min(2**attempt, 30)  # Cap at 30 seconds
        logger.info("Waiting before retry", wait_time_seconds=wait_time, phase="retry")
        await asyncio.sleep(wait_time)
