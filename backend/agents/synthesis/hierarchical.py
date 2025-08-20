"""Pure hierarchical synthesis agent - stateless and global following Pydantic AI best practices."""

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

# Agent configuration as module constants - concise accuracy-first approach
FINAL_HIERARCHICAL_INSTRUCTIONS = """
Create a meeting summary by combining segment summaries.

CRITICAL RULES:
1. ONLY include information from the provided segment summaries
2. NEVER add technical details, formulas, or names not in segment summaries
3. NO elaboration beyond what's stated in segments
4. If details are missing, don't fill them in

EXCLUDE:
- Greetings, confirmations, logistics from any segment
- Any content marked as trivial in segments

COMBINE SEGMENTS:
### **[Topic from segments]**
- State what was discussed using only information from segment summaries
- Include speaker names only if mentioned in segments
- Preserve numbers and percentages exactly as given in segments
- Don't add context or explanation not in segments

Length: As long as needed to cover the segment content, but no padding
Quality over quantity - better to be accurate than comprehensive

You must return BOTH a summary field and an action_items field.
Extract action items mentioned across all segments with exact context given.
"""

# Pure agent definition - stateless and global
# Using OpenAIResponsesModel for o3 models to enable thinking
hierarchical_synthesis_agent = Agent(
    OpenAIResponsesModel(settings.synthesis_model),
    output_type=MeetingIntelligence,
    instructions=FINAL_HIERARCHICAL_INSTRUCTIONS,
    retries=2,  # Built-in validation retries (reduced with simpler prompts)
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort=(
            settings.synthesis_reasoning_effort
            if settings.synthesis_reasoning_effort in ("low", "medium", "high")
            else "high"
        ),
        openai_reasoning_summary=(
            settings.synthesis_reasoning_summary
            if settings.synthesis_reasoning_summary in ("detailed", "concise")
            else "detailed"
        ),
    ),
)
logger.info(
    "Hierarchical synthesis agent configured",
    synthesis_model=settings.synthesis_model,
    synthesis_reasoning_effort=settings.synthesis_reasoning_effort,
    synthesis_reasoning_summary=settings.synthesis_reasoning_summary,
)
