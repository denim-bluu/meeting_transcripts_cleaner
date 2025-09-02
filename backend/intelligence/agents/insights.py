"""Pure chunk extraction agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel
import structlog

from backend.config import settings
from backend.intelligence.models import ChunkInsights

logger = structlog.get_logger(__name__)

load_dotenv()

INSTRUCTIONS = """
You are extracting insights from a meeting transcript segment.

STRICT RULES:
1. ONLY extract what is EXPLICITLY stated - no inference or elaboration
2. SKIP trivial content (greetings, "OK", "Yeah", meeting logistics)
3. NEVER add information not in the transcript
4. If unsure, leave it out

EXTRACT:
- Technical explanations as stated (no adding details)
- Decisions with the reasoning given
- Important Q&A exchanges
- Action items with owners if named

Quality check each insight:
- Is this exactly what was said?
- Does it add value to understanding?
- Am I adding any information not stated?

Target: 10-20 meaningful insights per chunk
"""

chunk_extraction_agent = Agent(
    OpenAIResponsesModel(settings.insights_model),
    output_type=ChunkInsights,
    instructions=INSTRUCTIONS,
    deps_type=dict,
    retries=2,
)


# Dynamic instructions based on meeting context (following Pydantic AI patterns)
@chunk_extraction_agent.instructions
def add_context_instructions(ctx: RunContext[dict]) -> str:
    """Add context-specific extraction instructions."""
    context = ctx.deps or {}

    instructions = []

    # Adjust extraction based on detail level
    detail_level = context.get("detail_level", "comprehensive")
    if detail_level == "premium":
        instructions.append(
            "Extract 15-20 insights with maximum accuracy. Include all technical details mentioned."
        )
    elif detail_level == "technical_focus":
        instructions.append(
            "Extract 12-18 insights focusing on technical content and methodologies."
        )
    elif detail_level == "standard":
        instructions.append(
            "Extract 10-15 key insights focusing on decisions and outcomes."
        )
    # Comprehensive uses base instructions (10-20 insights)

    # Simple position adjustments
    position = context.get("position", "middle")
    if position == "start":
        instructions.append("Focus on objectives and introductory statements.")
    elif position == "end":
        instructions.append("Focus on decisions, action items, and conclusions.")

    return "\n\n".join(instructions) if instructions else ""
