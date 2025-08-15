"""Production-grade intelligence synthesis using industry-standard hierarchical map-reduce."""

import asyncio

from pydantic_ai import Agent
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from models.intelligence import ChunkInsights, MeetingIntelligence

logger = structlog.get_logger(__name__)

# Microsoft Teams Premium-style synthesis prompt
PRODUCTION_SYNTHESIS_PROMPT = """
Create a comprehensive meeting summary and extract structured action items.

IMPORTANT: You must return BOTH a summary field and an action_items field.

For the summary field, create markdown content with this structure:

# Executive Summary
2-3 sentences capturing the meeting's purpose and main outcomes.

# Key Decisions
- Decision with brief rationale
- Include who made it and context

# Discussion by Topic
## [Auto-detected Topic 1]
### Main Points
- Point with context and speaker attribution when relevant
- Supporting details as sub-bullets
  - Data, numbers, or evidence mentioned
  - Technical details preserved

## [Auto-detected Topic 2]
[Same structure - let content naturally organize into topics]

# Important Quotes
Include 2-3 impactful direct quotes only if they add significant value.

For the action_items field, extract ALL actionable items as a list of structured objects.
Each action item should have:
- description: What needs to be done (minimum 10 characters)
- owner: Person responsible (null if not mentioned)
- due_date: When it's due (null if not mentioned)

Guidelines:
- Organize summary content by naturally emerging topics
- Preserve specific details: names, numbers, technical terms, decisions
- Include speaker attribution for key statements
- Use professional but accessible tone
- Extract ALL actionable items from the raw actions and insights
- DO NOT include action items in the summary markdown - they go in the separate action_items field

Meeting insights:
{insights}

Raw action items found:
{actions}
"""

# Hierarchical segment synthesis prompt
SEGMENT_SYNTHESIS_PROMPT = """
Summarize this 30-minute meeting segment focusing on key decisions and outcomes.

Format as:
## Segment Summary ({start_time} - {end_time})
### Key Decisions
- Decision with context

### Main Discussion Points
- Important point with speaker if relevant
- Technical details or data

### Actions Identified
- Action (Owner: Name, Due: Date if mentioned)

Keep this concise but comprehensive. Focus on decisions, commitments, and important technical details.

Segment insights:
{insights}
"""

# Final hierarchical synthesis prompt
FINAL_HIERARCHICAL_PROMPT = """
Create a comprehensive meeting summary from these temporal segment summaries and extract structured action items.

IMPORTANT: You must return BOTH a summary field and an action_items field.

For the summary field, create markdown content with this structure:
# Executive Summary
# Key Decisions
# Discussion by Topic
# Important Quotes (if valuable)

For the action_items field, extract ALL actionable items as a list of structured objects.
Each action item should have:
- description: What needs to be done (minimum 10 characters)
- owner: Person responsible (null if not mentioned)
- due_date: When it's due (null if not mentioned)

Synthesize across all segments to create a cohesive narrative. Look for patterns,
recurring themes, and overall meeting arc. Extract ALL action items mentioned across segments.

Segment summaries:
{segments}
"""


class IntelligenceSynthesizer:
    """Production-grade meeting intelligence synthesis using hierarchical map-reduce."""

    def __init__(self, model: str = "o3-mini"):
        self.agent = Agent(
            f"openai:{model}",
            output_type=MeetingIntelligence,
            retries=2,  # Built-in validation retries
        )
        # For hierarchical synthesis, we need a text agent for segments
        self.text_agent = Agent(f"openai:{model}", retries=1)
        logger.info("IntelligenceSynthesizer initialized", model=model)

    @retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def synthesize_intelligence_direct(
        self, insights_list: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """
        Direct synthesis for most meetings (95% of cases).

        Single API call with all important insights.
        """
        logger.info(
            "Starting direct synthesis",
            insights_count=len(insights_list),
        )

        # Collect all raw actions (lowered threshold)
        raw_actions = []
        for insights in insights_list:
            if insights.importance >= 4:  # Include more actions
                raw_actions.extend(insights.actions)

        # Format insights for synthesis
        formatted_insights = self._format_insights_for_synthesis(insights_list)

        # Create synthesis prompt
        prompt = PRODUCTION_SYNTHESIS_PROMPT.format(
            insights=formatted_insights,
            actions=chr(10).join(f"- {action}" for action in raw_actions),
        )

        logger.info(
            "Formatted content for direct synthesis",
            total_insights=sum(len(i.insights) for i in insights_list),
            raw_actions=len(raw_actions),
        )

        result = await self.agent.run(prompt)
        intelligence = result.output

        logger.info(
            "Direct synthesis completed",
            summary_length=len(intelligence.summary),
            action_items_count=len(intelligence.action_items),
            summary_sections=intelligence.summary.count("#"),
        )

        return intelligence

    @retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def synthesize_intelligence_hierarchical(
        self, insights_list: list[ChunkInsights], segment_minutes: int = 30
    ) -> MeetingIntelligence:
        """
        Hierarchical synthesis for long meetings (5% of cases).

        Multiple API calls: N segments + 1 final synthesis.
        """
        logger.info(
            "Starting hierarchical synthesis",
            insights_count=len(insights_list),
            segment_minutes=segment_minutes,
        )

        # Step 1: Create temporal segments
        segments = self._create_temporal_segments(insights_list, segment_minutes)

        logger.info(
            "Created temporal segments",
            segment_count=len(segments),
            avg_insights_per_segment=sum(len(s) for s in segments) / len(segments)
            if segments
            else 0,
        )

        # Step 2: Synthesize each segment in parallel
        segment_tasks = [
            self._synthesize_segment(segment, i, segment_minutes)
            for i, segment in enumerate(segments)
        ]

        segment_summaries = await asyncio.gather(*segment_tasks)

        # Step 3: Final synthesis of all segments
        segments_text = "\n\n".join(segment_summaries)
        final_prompt = FINAL_HIERARCHICAL_PROMPT.format(segments=segments_text)

        result = await self.agent.run(final_prompt)
        intelligence = result.output

        logger.info(
            "Hierarchical synthesis completed",
            segments_processed=len(segments),
            summary_length=len(intelligence.summary),
            action_items_count=len(intelligence.action_items),
        )

        return intelligence

    async def _synthesize_segment(
        self, segment: list[ChunkInsights], segment_index: int, segment_minutes: int
    ) -> str:
        """Synthesize a single temporal segment."""
        start_time = f"{segment_index * segment_minutes}min"
        end_time = f"{(segment_index + 1) * segment_minutes}min"

        # Format insights for this segment
        formatted_insights = self._format_insights_for_synthesis(segment)

        prompt = SEGMENT_SYNTHESIS_PROMPT.format(
            start_time=start_time,
            end_time=end_time,
            insights=formatted_insights,
        )

        result = await self.text_agent.run(prompt)
        return result.output

    def _create_temporal_segments(
        self, insights_list: list[ChunkInsights], segment_minutes: int
    ) -> list[list[ChunkInsights]]:
        """
        Create temporal segments for hierarchical processing.

        Groups insights by estimated time progression.
        """
        if not insights_list:
            return []

        # Simple segmentation by chunk order (assumes chronological processing)
        segment_size = max(1, len(insights_list) // max(1, len(insights_list) // 10))

        segments = []
        for i in range(0, len(insights_list), segment_size):
            segment = insights_list[i : i + segment_size]
            if segment:  # Only add non-empty segments
                segments.append(segment)

        return segments

    def _format_insights_for_synthesis(self, insights_list: list[ChunkInsights]) -> str:
        """Format insights in a clean, structured way for synthesis."""
        formatted = []

        for i, insights in enumerate(insights_list):
            formatted.append(
                f"\n--- Chunk {i+1} (Importance: {insights.importance}) ---"
            )

            # Add insights
            for insight in insights.insights:
                formatted.append(f"• {insight}")

            # Add themes context
            if insights.themes:
                formatted.append(f"Themes: {', '.join(insights.themes)}")

            # Add actions
            if insights.actions:
                formatted.append("Actions mentioned:")
                for action in insights.actions:
                    formatted.append(f"  - {action}")

        return "\n".join(formatted)
