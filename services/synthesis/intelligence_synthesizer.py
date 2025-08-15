"""Intelligence synthesis using universal prompts and structured output."""

from pydantic_ai import Agent
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from models.intelligence import ChunkInsights, MeetingIntelligence

logger = structlog.get_logger(__name__)

# Universal synthesis prompt that works for any meeting type
UNIVERSAL_SYNTHESIS_PROMPT = """
Create a comprehensive meeting summary from these insights.

This could be any type of meeting - technical, business, creative, or casual.
Preserve ALL important details and context.

Requirements:
- Organize by major themes
- Preserve specific details (names, numbers, technical terms, decisions)
- Include speaker attribution for key statements
- Extract action items with owners and deadlines
- Use professional but accessible tone

Insights organized by theme:
{insights_by_theme}

Raw action items found:
{raw_actions}

Generate:
1. A detailed markdown summary with clear theme headers (# Theme)
2. Comprehensive bullet points that preserve context and specifics
3. A consolidated list of actionable items with owners/deadlines
"""


class IntelligenceSynthesizer:
    """Universal meeting intelligence synthesis."""

    def __init__(self, model: str = "o3-mini"):
        self.agent = Agent(
            f"openai:{model}",
            output_type=MeetingIntelligence,
            retries=2,  # Built-in validation retries
        )
        logger.info("IntelligenceSynthesizer initialized", model=model)

    @retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def synthesize_intelligence(
        self, insights_list: list[ChunkInsights], major_themes: list[str]
    ) -> MeetingIntelligence:
        """Synthesize all insights into final intelligence."""
        logger.info(
            "Starting intelligence synthesis",
            insights_count=len(insights_list),
            themes_count=len(major_themes),
        )

        # Organize insights by theme
        insights_by_theme = self._organize_insights_by_theme(
            insights_list, major_themes
        )

        # Collect all raw actions
        raw_actions = []
        for insights in insights_list:
            if insights.importance >= 6:  # Include medium-high importance actions
                raw_actions.extend(insights.actions)

        # Create synthesis prompt
        prompt = UNIVERSAL_SYNTHESIS_PROMPT.format(
            insights_by_theme=self._format_insights_by_theme(insights_by_theme),
            raw_actions=chr(10).join(f"- {action}" for action in raw_actions),
        )

        logger.info(
            "Organized content for synthesis",
            themes_with_content=len(
                [t for t, insights in insights_by_theme.items() if insights]
            ),
            total_insights=sum(
                len(insights) for insights in insights_by_theme.values()
            ),
            raw_actions=len(raw_actions),
        )

        result = await self.agent.run(prompt)
        intelligence = result.output

        logger.info(
            "Intelligence synthesis completed",
            summary_length=len(intelligence.summary),
            action_items_count=len(intelligence.action_items),
            summary_sections=intelligence.summary.count("#"),
        )

        return intelligence

    def _organize_insights_by_theme(
        self, insights_list: list[ChunkInsights], major_themes: list[str]
    ) -> dict[str, list[str]]:
        """Organize insights by major themes."""
        theme_insights = {theme: [] for theme in major_themes}

        for insights in insights_list:
            # Include medium to high importance insights (5+)
            if insights.importance >= 5:
                # Try to match insights to themes
                matched = False
                for theme in major_themes:
                    # Check if any of the chunk's themes match this major theme
                    if any(
                        theme.lower() in chunk_theme.lower()
                        or chunk_theme.lower() in theme.lower()
                        for chunk_theme in insights.themes
                    ):
                        theme_insights[theme].extend(insights.insights)
                        matched = True
                        break

                # If no theme match but high importance, add to first theme
                if not matched and insights.importance >= 8:
                    if major_themes:
                        theme_insights[major_themes[0]].extend(insights.insights)

        # Remove empty themes
        return {
            theme: insights for theme, insights in theme_insights.items() if insights
        }

    def _format_insights_by_theme(self, insights_by_theme: dict[str, list[str]]) -> str:
        """Format insights organized by theme for the prompt."""
        formatted = []

        for theme, insights in insights_by_theme.items():
            if insights:
                formatted.append(f"\n{theme}:")
                for insight in insights:
                    formatted.append(f"  - {insight}")

        if not formatted:
            return "No insights available"

        return "\n".join(formatted)
