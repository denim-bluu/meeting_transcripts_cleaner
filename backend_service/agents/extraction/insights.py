"""Pure chunk extraction agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from backend_service.models.intelligence import ChunkInsights

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants - concise accuracy-first approach
UNIVERSAL_EXTRACTION_INSTRUCTIONS = """
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

# Pure agent definition - stateless and global
chunk_extraction_agent = Agent(
    "openai:o3-mini",
    output_type=ChunkInsights,
    instructions=UNIVERSAL_EXTRACTION_INSTRUCTIONS,
    deps_type=dict,  # Accept context dictionary as dependency
    retries=2,  # Built-in retry on validation failure
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
        instructions.append("Extract 15-20 insights with maximum accuracy. Include all technical details mentioned.")
    elif detail_level == "technical_focus":
        instructions.append("Extract 12-18 insights focusing on technical content and methodologies.")
    elif detail_level == "standard":
        instructions.append("Extract 10-15 key insights focusing on decisions and outcomes.")
    # Comprehensive uses base instructions (10-20 insights)

    # Simple position adjustments
    position = context.get("position", "middle")
    if position == "start":
        instructions.append("Focus on objectives and introductory statements.")
    elif position == "end":
        instructions.append("Focus on decisions, action items, and conclusions.")

    return "\n\n".join(instructions) if instructions else ""
