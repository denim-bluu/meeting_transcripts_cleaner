"""
Review Agent implementation for the dual-agent transcript cleaning system.

This agent performs quality assurance as the second stage, validating cleaning
results and making final approval decisions.
"""

import time

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.settings import ModelSettings
import structlog

from config import get_agents_config, get_openai_config
from models.schemas import CleaningResult, DocumentSegment, ReviewDecision
from prompts.review import get_review_prompt
from utils.config_manager import get_merged_agent_config

logger = structlog.get_logger(__name__)


class ReviewAgent:
    """Second-stage review agent for quality assurance."""

    def __init__(self) -> None:
        """Initialize the review agent with configuration."""
        # Use merged config that includes session overrides
        try:
            agents_config = get_merged_agent_config()
        except Exception:
            # Fallback to base config if overrides fail
            agents_config = get_agents_config()

        openai_config = get_openai_config()

        self.model_name = agents_config.review_model
        self.temperature = agents_config.review_temperature
        self.max_tokens = openai_config.max_tokens
        self.max_retries = openai_config.max_retries

        # Create OpenAI model instance with proper provider
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=openai_config.api_key)
        self.model = OpenAIModel(self.model_name, provider=provider)
        # Initialize Pydantic AI agent with proper configuration
        model_settings = ModelSettings(
            temperature=self.temperature,
        )

        self.agent: Agent[None, ReviewDecision] = Agent(
            model=self.model,
            output_type=ReviewDecision,
            system_prompt="""You are a Review Agent providing quality assurance for transcript cleaning. Your role is to validate the Cleaning Agent's work, ensuring 97-98% system accuracy through rigorous review.

Core responsibilities:
• Validate meaning and context preservation
• Assess quality and appropriateness of changes
• Score confidence (0.0-1.0) and preservation (0.0-1.0)
• Decide: accept, reject, or modify with reasoning
• Ensure no summarization or content loss occurred

Review criteria:
• Meaning preservation is absolute priority
• Speaker voice and dialogue integrity maintained
• Changes are necessary and beneficial
• No new interpretations introduced
• Technical accuracy preserved

Output JSON with: segment_id, decision, confidence, preservation_score, issues_found, suggested_corrections, reasoning""",
            model_settings=model_settings,
            retries=self.max_retries,
        )

        logger.info(
            "Review agent initialized",
            # Key identifier (flat)
            agent_type="review",
            # Configuration (grouped)
            ai_config={
                "model": self.model_name,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )

    async def review_cleaning(
        self,
        original_segment: DocumentSegment,
        cleaning_result: CleaningResult,
        context: dict[str, str] | None = None,
    ) -> ReviewDecision:
        """
        Review a cleaning result and make an approval decision.

        Args:
            original_segment: The original document segment
            cleaning_result: The cleaning result to review
            context: Optional context information

        Returns:
            ReviewDecision with approval/rejection and reasoning

        Raises:
            Exception: If review fails after all retries
        """
        start_time = time.time()

        # Prepare context
        previous_context = context.get("previous", "") if context else ""
        following_context = context.get("following", "") if context else ""

        # Generate the review prompt
        prompt = get_review_prompt(
            original_text=original_segment.content,
            cleaned_text=cleaning_result.cleaned_text,
            changes_made=cleaning_result.changes_made,
            segment_number=original_segment.sequence_number,
            total_segments=1,  # Will be updated by caller if needed
            token_count=original_segment.token_count,
            segment_id=original_segment.id,
            previous_context=previous_context,
            following_context=following_context,
        )

        logger.debug(
            "Reviewing segment", segment_id=original_segment.id, phase="review"
        )

        # Attempt review with retries
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
                if not result.segment_id:
                    result.segment_id = original_segment.id
                if result.processing_time_ms is None:
                    result.processing_time_ms = processing_time
                if not result.model_used:
                    result.model_used = self.model_name

                # Validate the result
                self._validate_review_decision(
                    original_segment, cleaning_result, result
                )

                logger.info(
                    "Review completed for segment",
                    segment_id=original_segment.id,
                    decision=result.decision,
                    confidence=result.confidence,
                    preservation_score=result.preservation_score,
                    processing_time_ms=processing_time,
                    phase="review",
                )

                return result

            except Exception as e:
                logger.error(
                    "Unexpected error reviewing segment",
                    segment_id=original_segment.id,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1,
                    error=str(e),
                    phase="review",
                )
                if attempt == self.max_retries:
                    raise Exception(
                        f"Review failed after {self.max_retries + 1} attempts: {e}"
                    ) from e

                await self._wait_with_backoff(attempt)

        # This should never be reached due to exception handling above, but provide fallback
        raise Exception(
            f"Unable to review segment {original_segment.id} after all attempts"
        )

    def _validate_review_decision(
        self,
        original_segment: DocumentSegment,
        cleaning_result: CleaningResult,
        decision: ReviewDecision,
    ) -> None:
        """
        Validate that the review decision is reasonable.

        Args:
            original_segment: Original segment
            cleaning_result: Cleaning result that was reviewed
            decision: Review decision to validate

        Raises:
            ValueError: If the decision fails validation
        """
        # Check confidence score is in valid range
        if not (0.0 <= decision.confidence <= 1.0):
            raise ValueError(f"Invalid confidence score: {decision.confidence}")

        # Check preservation score is in valid range
        if not (0.0 <= decision.preservation_score <= 1.0):
            raise ValueError(
                f"Invalid preservation score: {decision.preservation_score}"
            )

        # Ensure segment ID matches (fix if AI returned wrong ID)
        if decision.segment_id != original_segment.id:
            logger.warning(
                "AI returned wrong segment_id, correcting",
                ai_returned_id=decision.segment_id,
                correct_id=original_segment.id,
                phase="validation",
                warning_type="incorrect_segment_id",
            )
            decision.segment_id = original_segment.id

        # Check that reasoning exists
        if not decision.reasoning or not decision.reasoning.strip():
            raise ValueError("Review decision must include reasoning")

        # Check that modify decisions include suggested corrections
        if decision.decision == "modify" and not decision.suggested_corrections:
            raise ValueError("Modify decisions must include suggested_corrections")

        # Validate suggested corrections are different from original
        if (
            decision.decision == "modify"
            and decision.suggested_corrections
            and decision.suggested_corrections.strip()
            == cleaning_result.cleaned_text.strip()
        ):
            logger.warning(
                "Modify decision has identical corrections to cleaned text",
                segment_id=original_segment.id,
                phase="validation",
                warning_type="redundant_corrections",
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
