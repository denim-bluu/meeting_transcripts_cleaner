"""Pure direct synthesis agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
import structlog

from backend.config import settings
from backend.models.intelligence import MeetingIntelligence

# Ensure environment is loaded for API key
load_dotenv()
logger = structlog.get_logger(__name__)

# Agent configuration as module constants - following industry best practices
PRODUCTION_SYNTHESIS_INSTRUCTIONS = """
Create a meeting summary from the extracted insights.

CRITICAL RULES:
1. ONLY include information from the provided insights
2. NEVER add technical details, formulas, or names not in insights
3. NO elaboration beyond what's stated
4. If details are missing, don't fill them in

EXCLUDE:
- Greetings, confirmations, logistics
- Any content marked as trivial

STRUCTURE:
### **[Topic from insights]**
- State what was discussed using only the information provided
- Include speaker names only if mentioned in insights
- Preserve numbers and percentages exactly as given
- Don't add context or explanation not in insights

Length: As long as needed to cover the insights, but no padding
Quality over quantity - better to be accurate than comprehensive

You must return BOTH a summary field and an action_items field.
Extract action items mentioned in insights with exact context given.
"""

# Pure agent definition - stateless and global
# Using OpenAIResponsesModel for o3 models to enable thinking
direct_synthesis_agent = Agent(
    OpenAIResponsesModel(settings.synthesis_model),
    output_type=MeetingIntelligence,
    instructions=PRODUCTION_SYNTHESIS_INSTRUCTIONS,
    retries=2,  # Built-in validation retries (balanced for reliability)
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort=(
            settings.synthesis_reasoning_effort
            if settings.synthesis_reasoning_effort in ("low", "medium", "high")
            else "high"
        ),
        openai_reasoning_summary=(
            "detailed"
            if settings.synthesis_reasoning_summary == "detailed"
            else "concise"
            if settings.synthesis_reasoning_summary == "concise"
            else "detailed"
        ),
    ),
)
logger.info(
    "Direct synthesis agent configured",
    synthesis_model=settings.synthesis_model,
    synthesis_reasoning_effort=settings.synthesis_reasoning_effort,
    synthesis_reasoning_summary=settings.synthesis_reasoning_summary,
)
