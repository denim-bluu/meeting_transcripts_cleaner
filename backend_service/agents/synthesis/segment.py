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
Summarize this meeting segment with precise factual accuracy, preserving exact technical details.

PRECISION REQUIREMENTS:
- ONLY include information explicitly stated in the segment insights
- NEVER infer, assume, or fabricate participant names or details
- Preserve ALL technical specifications, numbers, percentages exactly
- Include speaker attribution only when clearly identified

Format as:
## Segment Summary
### Key Decisions
- Decision with exact technical context and specifications

### Main Discussion Points
- Important technical points with precise numbers and details
- Speaker attribution only when explicitly identified
- Exact quotes and technical specifications preserved

### Actions Identified
- Action with clear context (Owner: Name if clearly stated, Due: Date if mentioned)

Focus on factual accuracy, exact technical details, and natural discussion flow from this segment.
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
