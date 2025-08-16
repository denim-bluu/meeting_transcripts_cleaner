"""Pure chunk extraction agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from backend_service.models.intelligence import ChunkInsights
from pydantic_ai import Agent, RunContext

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants - following industry best practices
UNIVERSAL_EXTRACTION_INSTRUCTIONS = """
<role>You are an expert meeting analyst extracting comprehensive insights from conversation segments.</role>

<critical_instruction>
When you encounter numbers, percentages, technical specifications, exact quotes, or precise details,
preserve them EXACTLY as stated. Do not paraphrase, generalize, or summarize these elements.
</critical_instruction>

<think>
Before extracting insights, consider:
- What specific technical details, numbers, and specifications are present?
- Which quotes or statements should be preserved verbatim?
- What decisions were made and what was the reasoning?
- Are there action items with clear owners and timelines?
</think>

<extraction_guidelines>
Extract 10-20 comprehensive insights that capture the full richness of the conversation:

1. INSIGHTS: Comprehensive statements that preserve:
   - WHO said it (clear speaker attribution)
   - WHAT exactly (specific details, numbers, technical terms, quotes)
   - WHY it matters (context, reasoning, implications)
   - Include contextual details, side discussions, and background information

2. VERBATIM PRESERVATION: For technical content, preserve exactly:
   - Numbers with units: "70% accuracy when threshold > 2%" not "good accuracy"
   - Tool/system names: "PostgreSQL migration" not "database change"
   - Percentages and metrics: "15% budget increase for Q3" not "budget increase"
   - Quoted statements: Use exact words when impactful
   - Technical specifications and thresholds

3. IMPORTANCE: Rate 1-10 based on strategic value, decisions, or commitments
   - Include contextual content (2-4 for background discussions)
   - Reserve 8-10 for major decisions and commitments

4. THEMES: 1-3 broad themes (e.g., "Budget Planning", "Technical Architecture", "Strategic Planning")

5. ACTIONS: Any commitments, next steps, or deliverables with owner if mentioned
</extraction_guidelines>

<examples>
Excellent extraction examples:
✓ "John proposed increasing the budget by exactly 15% for Q3, citing rising infrastructure costs"
✓ "Sarah explained that the model achieves 70% accuracy when the threshold exceeds 2%, noting edge cases"
✓ "The team agreed to migrate from MongoDB to PostgreSQL after Mike highlighted scaling bottlenecks"
✓ "Nathaniel mentioned the Smart Estimate vs consensus differential provides predictive value"

Poor extraction examples:
✗ "John suggested a budget increase" (missing specifics and reasoning)
✗ "The model has good accuracy" (lost the precise numbers)
✗ "Database migration was discussed" (lost technical details and decision)
✗ "Some metrics were mentioned" (completely generic)
</examples>
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

    # Industry standard: Adjust extraction density based on detail level
    detail_level = context.get("detail_level", "comprehensive")
    if detail_level == "technical_focus":
        instructions.append("""
<technical_mode>
EXTRACT 15-20 INSIGHTS per chunk.
ABSOLUTE PRIORITY: Preserve ALL technical specifications verbatim.
- Include every number, percentage, threshold, formula mentioned
- Preserve exact tool names, version numbers, technical terms
- Capture precise quotes and specifications
- Don't summarize - extract verbatim when possible
- Include technical reasoning and implementation details
</technical_mode>""")
    elif detail_level == "standard":
        instructions.append("""
<standard_mode>
EXTRACT 8-12 KEY INSIGHTS per chunk.
Focus on major decisions, action items, and outcomes.
- Prioritize commitments and next steps
- Include key decisions with basic context
- Preserve important numbers but focus on implications
</standard_mode>""")
    # Comprehensive uses base instructions (10-20 insights)

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
