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
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_agents_config, get_openai_config
from models.schemas import CleaningResult, DocumentSegment, ReviewDecision
from prompts.review import get_review_prompt
from utils.config_manager import get_merged_agent_config
from utils.validators import validate_review_decision

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

        # Call the AI review method with automatic retry
        result = await self._review_with_retry(
            prompt, original_segment, cleaning_result, start_time
        )

        logger.info(
            "Review completed for segment",
            segment_id=original_segment.id,
            decision=result.decision,
            confidence=result.confidence,
            preservation_score=result.preservation_score,
            processing_time_ms=result.processing_time_ms,
            phase="review",
        )

        return result

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=30))
    async def _review_with_retry(
        self,
        prompt: str,
        original_segment: DocumentSegment,
        cleaning_result: CleaningResult,
        start_time: float,
    ) -> ReviewDecision:
        """
        Review a cleaning result with automatic exponential backoff retry.

        Args:
            prompt: The review prompt to use
            original_segment: The original document segment
            cleaning_result: The cleaning result to review
            start_time: Start time for processing time calculation

        Returns:
            ReviewDecision with approval/rejection and reasoning

        Raises:
            Exception: If review fails after all retries
        """
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

            # Validate the result using shared validator
            validate_review_decision(original_segment, cleaning_result, result)

            return result

        except Exception as e:
            logger.error(
                "Error reviewing segment",
                segment_id=original_segment.id,
                error=str(e),
                phase="review",
            )
            raise
