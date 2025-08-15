"""Simple topic clustering using structured output."""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class ThemeClusters(BaseModel):
    """Simple model for theme clustering - avoid complexity to prevent timeouts."""

    themes: list[str] = Field(
        ..., min_length=3, max_length=8, description="List of themes"
    )


class TopicClusterer:
    """Simplified topic clustering using structured output."""

    def __init__(self, model: str = "o3-mini"):
        self.agent = Agent(
            f"openai:{model}",
            output_type=ThemeClusters,
            retries=1,  # Built-in validation retry
        )
        logger.info("TopicClusterer initialized", model=model)

    @retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def cluster_themes(self, all_themes: list[str]) -> list[str]:
        """Cluster themes into 3-8 major categories."""
        # If we already have few themes, return as-is
        if len(all_themes) <= 8:
            unique_themes = list(set(all_themes))
            logger.info("Using original themes", count=len(unique_themes))
            return unique_themes

        logger.info("Clustering themes", original_count=len(all_themes))

        prompt = f"""
        Group these {len(all_themes)} meeting themes into 3-8 major categories.

        Original themes:
        {chr(10).join(f"- {t}" for t in set(all_themes))}

        Create broader categories that represent the main discussion areas.
        Focus on:
        - Grouping related concepts together
        - Creating 3-8 broad themes (not more than 8)
        - Using clear, descriptive names
        - Covering all important themes
        """

        result = await self.agent.run(prompt)
        clusters = result.output

        logger.info(
            "Themes clustered successfully",
            original_count=len(all_themes),
            clustered_count=len(clusters.themes),
        )

        return clusters.themes

    def extract_all_themes(self, insights_list: list) -> list[str]:
        """Extract all themes from insights list."""
        all_themes = []
        for insights in insights_list:
            if hasattr(insights, "themes"):
                all_themes.extend(insights.themes)
            else:
                # Fallback for dict format
                all_themes.extend(insights.get("themes", []))

        unique_themes = list(set(all_themes))
        logger.info("Raw themes extracted", count=len(unique_themes))
        return unique_themes
