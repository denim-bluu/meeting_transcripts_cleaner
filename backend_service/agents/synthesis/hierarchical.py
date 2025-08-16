"""Pure hierarchical synthesis agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

from backend_service.models.intelligence import MeetingIntelligence

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants
FINAL_HIERARCHICAL_INSTRUCTIONS = """
Create a PRECISE technical meeting summary from temporal segment summaries that preserves exact technical details and natural discussion flow.

ABSOLUTE FACTUAL ACCURACY:
- NEVER infer, assume, or fabricate participant names, roles, or details not in segments
- ONLY synthesize information explicitly present across segment summaries
- If participant information is incomplete, do NOT complete it - use only confirmed names
- When details are unclear across segments, OMIT rather than guess

TECHNICAL PRESERVATION ACROSS SEGMENTS:
- Preserve ALL technical specifications, numbers, percentages, and exact terminology from all segments
- Maintain natural chronological flow of how technical topics were actually presented
- Include specific speaker attributions only when clearly identified across segments
- Capture how technical concepts were introduced and explained throughout the meeting
- Preserve exact technical quotes and specifications verbatim

NATURAL SYNTHESIS REQUIREMENTS:
- Follow the meeting's natural progression as it evolved across time segments
- Show how technical discussions built upon each other chronologically
- Preserve the actual flow of technical presentations and Q&A sessions
- Include supporting evidence and examples as they were actually cited
- Maintain factual accuracy while synthesizing across temporal boundaries

IMPORTANT: You must return BOTH a summary field and an action_items field.

For the summary field, create clean markdown following this EXACT structure (match stakeholder preference):

### **[Topic Name Based on Natural Meeting Flow Across Segments]**

- **[Speaker Name]** [action verb] by [specific technical details with exact numbers]
- [Key technical points with precise specifications and terminology]
- [Technical mechanisms, formulas, or implementation details mentioned across segments]
- [Important technical insights or methodology explanations that evolved over time]

---

### **[Next Topic Following Meeting Progression Across Time]**

- [Continue with natural flow of technical presentation as it developed]
- [Preserve exact technical details, percentages, and specifications from all segments]
- [Include specific examples and use cases mentioned throughout the meeting]
- [Show how technical understanding evolved across meeting timeline]

---

[Continue for all major technical topics discussed in their natural chronological order]

For the action_items field, extract ALL actionable items from across all meeting segments as structured objects:
- description: What needs to be done with clear context (minimum 15 characters)
- owner: Person responsible (use exact names mentioned across segments, null if unclear)
- due_date: When it's due (preserve exact timeframes, null if not mentioned)

PRECISION-FIRST HIERARCHICAL VALIDATION:
- Summary MUST use clean ### **Topic** structure following natural meeting progression across segments
- Summary MUST preserve ALL technical specifications, numbers, dates verbatim from all segments
- Summary MUST contain ONLY factually verified information synthesized from segments
- Summary MUST use simple bullet points, no complex nested formatting
- Summary MUST include speaker attribution only when clearly identified across segments
- NEVER fabricate, infer, or complete participant lists or details not present in segments
- Focus on technical accuracy and natural chronological discussion progression
- Preserve exact technical terminology, system names, version numbers from all segments
- Use clean, readable structure matching stakeholder preference
- DO NOT include action items in summary markdown - use separate action_items field

HIERARCHICAL SYNTHESIS GUIDELINES:
- Synthesize chronologically across temporal segments maintaining natural flow
- Identify patterns and technical themes as they actually emerged over time
- Preserve ALL specific technical details: numbers, specifications, exact quotes
- Show how technical concepts evolved through actual meeting progression
- Include speaker attribution only when factually verified across segments
- Extract ALL action items mentioned throughout meeting with accurate context
- Create factually accurate technical narrative without inference or elaboration
- Ensure precision and accuracy over comprehensiveness
"""

# Pure agent definition - stateless and global
# Using OpenAIResponsesModel for o3 models to enable thinking
hierarchical_synthesis_agent = Agent(
    OpenAIResponsesModel("o3"),
    output_type=MeetingIntelligence,
    instructions=FINAL_HIERARCHICAL_INSTRUCTIONS,
    retries=3,  # Built-in validation retries (increased for complex synthesis)
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="high",  # Enable thinking for complex reasoning
        openai_reasoning_summary="detailed",  # Include detailed reasoning summaries
    ),
)
