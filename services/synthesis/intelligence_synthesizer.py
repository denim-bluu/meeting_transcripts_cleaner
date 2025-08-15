"""Production-grade intelligence synthesis using industry-standard hierarchical map-reduce."""

import asyncio

from pydantic_ai import Agent
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models.intelligence import ChunkInsights, MeetingIntelligence

logger = structlog.get_logger(__name__)

# Adaptive Detail Control - Context Preservation Synthesis Instructions
PRODUCTION_SYNTHESIS_INSTRUCTIONS = """
Create a COMPREHENSIVE meeting intelligence that preserves important context and details.

CRITICAL: Include sufficient detail for someone who wasn't in the meeting to understand:
- Not just WHAT was decided, but WHY
- Not just WHO said something, but their REASONING
- Not just OUTCOMES, but the DISCUSSION that led there

IMPORTANT: You must return BOTH a summary field and an action_items field.

For the summary field, create detailed markdown with:

# Executive Summary
3-4 sentences providing complete context of the meeting's purpose, key participants, main topics discussed, and primary outcomes.

# Key Decisions
For each decision include:
- The decision made with full context
- The rationale and trade-offs discussed
- Who made it and who was consulted or provided input
- Any concerns, alternatives, or dissenting views considered
- Impact or implications mentioned

# Discussion by Topic
## [Topic Name]
### Context
Brief background on why this topic was discussed and its importance

### Main Discussion Points
- Detailed point with full context and speaker attribution
- Include specific numbers, dates, technical details, and reasoning mentioned
- Preserve important quotes or specific phrasing when impactful
- Capture the flow of discussion and different perspectives
  - Supporting evidence, data, or examples cited
  - Counterarguments, concerns, or challenges raised
  - Technical details or specifications discussed
  - Timeline considerations or dependencies mentioned

### Outcomes
What was concluded, decided, or left open for this topic, including next steps

[Continue for all major topics discussed...]

# Important Quotes
Include 3-4 impactful direct quotes that provide valuable context or capture key insights.

For the action_items field, extract ALL actionable items as a list of structured objects.
Each action item should have:
- description: What needs to be done with sufficient context (minimum 10 characters)
- owner: Person responsible (null if not mentioned)
- due_date: When it's due (null if not mentioned)

Guidelines:
- Prioritize comprehensiveness while maintaining clear organization
- Preserve specific details: names, numbers, technical terms, decisions, reasoning
- Include speaker attribution for key statements and reasoning
- Capture the "why" behind decisions and discussions
- Use professional but accessible tone with rich context
- Extract ALL actionable items from the raw actions and insights
- DO NOT include action items in the summary markdown - they go in the separate action_items field
- Focus on making the summary self-contained and informative for non-attendees
"""

# Hierarchical segment synthesis instructions
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

# Final hierarchical synthesis instructions
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

Guidelines:
- Synthesize across all segments to create a cohesive, comprehensive narrative
- Look for patterns, recurring themes, and overall meeting arc
- Prioritize comprehensiveness while maintaining clear organization
- Preserve specific details: names, numbers, technical terms, decisions, reasoning
- Include speaker attribution for key statements and reasoning
- Capture the "why" behind decisions and discussions
- Extract ALL action items mentioned across segments
- Focus on making the summary self-contained and informative for non-attendees
"""


class IntelligenceSynthesizer:
    """Production-grade meeting intelligence synthesis using hierarchical map-reduce."""

    def __init__(self, model: str = "o3-mini"):
        self.model_name = model

        # Configure thinking for complex synthesis using proper OpenAIResponsesModel
        if model.startswith("o3"):
            # For o3 models, use OpenAIResponsesModel with thinking
            model_instance = OpenAIResponsesModel(model)
            model_settings = OpenAIResponsesModelSettings(
                openai_reasoning_effort="high",  # Enable thinking for complex reasoning
                openai_reasoning_summary="detailed",  # Include detailed reasoning summaries
            )
            thinking_enabled = True
        else:
            # For other models, use standard approach
            model_instance = f"openai:{model}"
            model_settings = None
            thinking_enabled = False

        self.agent = Agent(
            model_instance,
            output_type=MeetingIntelligence,
            instructions=PRODUCTION_SYNTHESIS_INSTRUCTIONS,
            retries=2,  # Built-in validation retries
            model_settings=model_settings,
        )

        # For hierarchical synthesis, we need a text agent for segments
        # Also enable thinking for segment synthesis
        self.text_agent = Agent(
            model_instance,
            instructions=SEGMENT_SYNTHESIS_INSTRUCTIONS,
            retries=1,
            model_settings=model_settings,
        )

        # For final hierarchical synthesis, we need another agent with different instructions
        self.hierarchical_agent = Agent(
            model_instance,
            output_type=MeetingIntelligence,
            instructions=FINAL_HIERARCHICAL_INSTRUCTIONS,
            retries=2,
            model_settings=model_settings,
        )

        logger.info(
            "IntelligenceSynthesizer initialized",
            model=model,
            thinking_enabled=thinking_enabled,
            uses_responses_model=model.startswith("o3"),
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    async def synthesize_intelligence_direct(
        self, insights_list: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """
        Direct synthesis for most meetings (95% of cases).

        Single API call with all important insights.
        Network errors retried via tenacity, validation errors handled by Pydantic AI.
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

        # Create user message with meeting data
        user_message = f"""Meeting insights:
{formatted_insights}

Raw action items found:
{chr(10).join(f"- {action}" for action in raw_actions)}"""

        logger.info(
            "Formatted content for direct synthesis",
            total_insights=sum(len(i.insights) for i in insights_list),
            raw_actions=len(raw_actions),
        )

        result = await self.agent.run(user_message)
        intelligence = result.output

        logger.info(
            "Direct synthesis completed",
            summary_length=len(intelligence.summary),
            action_items_count=len(intelligence.action_items),
            summary_sections=intelligence.summary.count("#"),
        )

        return intelligence

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    async def synthesize_intelligence_hierarchical(
        self, insights_list: list[ChunkInsights], segment_minutes: int = 30
    ) -> MeetingIntelligence:
        """
                Hierarchical synthesis for long meetings (5% of cases).

                Multiple API calls: N segments + 1 final synthesis.
        <<<<<<< Updated upstream
        =======
                Network errors retried via tenacity, validation errors handled by Pydantic AI.
        >>>>>>> Stashed changes
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

        # Use dedicated hierarchical agent with appropriate instructions
        result = await self.hierarchical_agent.run(
            f"Segment summaries:\n\n{segments_text}"
        )
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

        # Create user message with segment data
        user_message = f"""Time range: {start_time} - {end_time}

Segment insights:
{formatted_insights}"""

        result = await self.text_agent.run(user_message)
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
