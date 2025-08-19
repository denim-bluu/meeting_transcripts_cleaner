"""Pure segment synthesis agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

from backend.config import settings

# Import for string output type
# (segment synthesis returns plain string, not structured)

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants - concise accuracy-first approach
SEGMENT_SYNTHESIS_INSTRUCTIONS = """
Create a segment summary from the provided insights.

STRICT RULES:
1. ONLY include information from the provided insights
2. NEVER add technical details, formulas, or names not in insights
3. NO elaboration beyond what's stated
4. If details are missing, don't fill them in

EXCLUDE:
- Greetings, confirmations, logistics
- Any content marked as trivial

FORMAT:
## Segment Summary
### **[Topic from insights]**
- State what was discussed using only the information provided
- Include speaker names only if mentioned in insights
- Preserve numbers and percentages exactly as given
- Don't add context or explanation not in insights

Length: As long as needed to cover the insights, but no padding
Quality over quantity - better to be accurate than comprehensive
"""

# Pure agent definition - stateless and global
# Using OpenAIResponsesModel for o3 models to enable thinking
segment_synthesis_agent = Agent(
    OpenAIResponsesModel(settings.synthesis_model),
    instructions=SEGMENT_SYNTHESIS_INSTRUCTIONS,
    retries=2,  # Built-in validation retries (consistent with other agents)
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="high",  # Enable thinking for complex reasoning
        openai_reasoning_summary="detailed",  # Include detailed reasoning summaries
    ),
)
