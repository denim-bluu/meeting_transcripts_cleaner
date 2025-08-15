"""Pure segment synthesis agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

# Import for string output type
# (segment synthesis returns plain string, not structured)

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants
SEGMENT_SYNTHESIS_INSTRUCTIONS = """
Summarize this meeting segment focusing on key decisions and outcomes.

Format as:
## Segment Summary
### Key Decisions
- Decision with context

### Main Discussion Points
- Important point with speaker if relevant
- Technical details or data

### Actions Identified
- Action (Owner: Name, Due: Date if mentioned)

Keep this concise but comprehensive. Focus on decisions, commitments, and important technical details.
"""

# Pure agent definition - stateless and global
# Using OpenAIResponsesModel for o3 models to enable thinking
segment_synthesis_agent = Agent(
    OpenAIResponsesModel("o3-mini"),
    instructions=SEGMENT_SYNTHESIS_INSTRUCTIONS,
    retries=1,  # Built-in validation retries
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="high",  # Enable thinking for complex reasoning
        openai_reasoning_summary="detailed",  # Include detailed reasoning summaries
    ),
)
