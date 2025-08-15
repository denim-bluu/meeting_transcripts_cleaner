"""Pure hierarchical synthesis agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

from models.intelligence import MeetingIntelligence

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants
FINAL_HIERARCHICAL_INSTRUCTIONS = """
Create a COMPREHENSIVE meeting summary from temporal segment summaries that preserves important context and details.

CRITICAL: Include sufficient detail for someone who wasn't in the meeting to understand:
- Not just WHAT was decided, but WHY
- Not just WHO said something, but their REASONING
- Not just OUTCOMES, but the DISCUSSION that led there

IMPORTANT: You must return BOTH a summary field and an action_items field.

For the summary field, create detailed markdown with this structure:

# Executive Summary
3-4 sentences providing complete context of the meeting's purpose, key participants, main topics discussed, and primary outcomes across all segments.

# Key Decisions
For each decision include:
- The decision made with full context from across segments
- The rationale and trade-offs discussed over time
- Who made it and who was consulted throughout the meeting
- Any concerns, alternatives, or evolving perspectives
- Impact or implications mentioned

# Discussion by Topic
## [Topic Name]
### Context
Background on why this topic was important and how it evolved during the meeting

### Discussion Flow
- Detailed progression of the discussion with speaker attribution
- Include specific numbers, dates, technical details, and reasoning mentioned
- Capture how perspectives evolved or changed during the meeting
- Preserve important quotes or specific phrasing when impactful
  - Supporting evidence, data, or examples cited across segments
  - Counterarguments, concerns, or challenges that emerged
  - Technical details or specifications discussed
  - Timeline considerations or dependencies mentioned

### Outcomes
What was concluded, decided, or left open for this topic, including next steps

[Continue for all major topics discussed...]

# Important Quotes
Include 3-4 impactful direct quotes that provide valuable context or capture key insights from across the meeting.

For the action_items field, extract ALL actionable items as a list of structured objects.
Each action item should have:
- description: What needs to be done with sufficient context (minimum 10 characters)
- owner: Person responsible (null if not mentioned)
- due_date: When it's due (null if not mentioned)

CRITICAL VALIDATION REQUIREMENTS:
- Summary MUST be at least 100 characters long with rich, detailed content
- Summary MUST include proper markdown headers (# Executive Summary, # Key Decisions, # Discussion by Topic, # Important Quotes)
- Summary MUST contain speaker attribution words like: 'said', 'mentioned', 'explained', 'proposed', 'suggested', 'agreed', 'noted'
- Action items (if any) should have varied descriptions and include owners when mentioned
- Use comprehensive, detailed language - avoid brief or superficial summaries

Guidelines:
- Synthesize across all segments to create a cohesive, comprehensive narrative
- Look for patterns, recurring themes, and overall meeting arc
- Prioritize comprehensiveness while maintaining clear organization
- Preserve specific details: names, numbers, technical terms, decisions, reasoning
- Include speaker attribution for key statements and reasoning using specific attribution verbs
- Capture the "why" behind decisions and discussions
- Extract ALL action items mentioned across segments
- Focus on making the summary self-contained and informative for non-attendees
- Ensure summary contains at least 100 characters of meaningful content
"""

# Pure agent definition - stateless and global
# Using OpenAIResponsesModel for o3 models to enable thinking
hierarchical_synthesis_agent = Agent(
    OpenAIResponsesModel("o3-mini"),
    output_type=MeetingIntelligence,
    instructions=FINAL_HIERARCHICAL_INSTRUCTIONS,
    retries=3,  # Built-in validation retries (increased for complex synthesis)
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="high",  # Enable thinking for complex reasoning
        openai_reasoning_summary="detailed",  # Include detailed reasoning summaries
    ),
)
