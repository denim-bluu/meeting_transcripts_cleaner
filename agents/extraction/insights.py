"""Pure chunk extraction agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from models.intelligence import ChunkInsights

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants
UNIVERSAL_EXTRACTION_INSTRUCTIONS = """
Extract comprehensive insights from this conversation segment.

Your goal: Capture EVERYTHING important - names, numbers, decisions, technical details,
context, and relationships. This could be any type of meeting - technical, business,
creative, or casual.

Extract:
1. INSIGHTS: 8-15 important statements that preserve:
   - WHO said it (speaker attribution)
   - WHAT exactly (specific details, numbers, technical terms)
   - WHY it matters (context and implications)
   - Examples:
     * "John proposed increasing the budget by 15% for Q3"
     * "Sarah explained the API returns 70% accuracy when threshold > 2%"
     * "Team agreed to use PostgreSQL over MongoDB for scaling reasons"

2. IMPORTANCE: Rate 1-10 based on decisions, commitments, or strategic value

3. THEMES: 1-3 broad themes (e.g., "Budget Planning", "Technical Architecture")

4. ACTIONS: Any commitments or next steps with owner if mentioned
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

    # Adjust based on chunk position in meeting
    position = context.get("position", "middle")
    if position == "start":
        instructions.append(
            "This is from the beginning of the meeting. Pay special attention to "
            "meeting objectives, agenda items, and introductory statements."
        )
    elif position == "end":
        instructions.append(
            "This is from the end of the meeting. Focus on final decisions, "
            "action items, next steps, and meeting conclusions."
        )

    # Adjust based on meeting type
    meeting_type = context.get("meeting_type")
    if meeting_type == "technical":
        instructions.append(
            "This is a technical meeting. Pay special attention to architecture "
            "decisions, technical specifications, system requirements, and implementation details."
        )
    elif meeting_type == "executive":
        instructions.append(
            "This is an executive meeting. Focus on strategic decisions, budget discussions, "
            "high-level planning, and business outcomes."
        )
    elif meeting_type == "standup":
        instructions.append(
            "This is a standup meeting. Focus on progress updates, blockers, "
            "and immediate next steps for team members."
        )

    # Adjust based on content characteristics
    if context.get("action_heavy"):
        instructions.append(
            "This segment is action-heavy. Be extra thorough in identifying "
            "commitments, assignments, and deliverables with owners and timelines."
        )

    return "\n\n".join(instructions) if instructions else ""
