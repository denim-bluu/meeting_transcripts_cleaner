"""Intelligence synthesis strategy wrapper."""

from ..agents.hierarchical import hierarchical_synthesis_agent
from ..agents.segment import segment_synthesis_agent
from ..agents.synthesizer import direct_synthesis_agent
from ..models import ChunkInsights, MeetingIntelligence


class IntelligenceSynthesisStrategy:
    """Wrapper for synthesis agents implementing SynthesisStrategy protocol."""

    async def synthesize_intelligence(
        self, insights: list[ChunkInsights], strategy: str = "direct"
    ) -> MeetingIntelligence:
        """Synthesize meeting intelligence from extracted insights."""
        if strategy == "hierarchical":
            return await self._synthesize_hierarchical(insights)
        else:
            return await self._synthesize_direct(insights)

    async def _synthesize_direct(
        self, insights: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """Direct synthesis using single agent."""
        formatted_insights = self._format_insights_for_synthesis(insights)
        result = await direct_synthesis_agent.run(formatted_insights)
        return result.output

    async def _synthesize_hierarchical(
        self, insights: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """Hierarchical synthesis using segment then final agents."""
        # Group insights into segments (simple time-based grouping)
        segments = self._group_insights_into_segments(insights)

        # Create segment summaries
        segment_summaries = []
        for segment in segments:
            formatted_segment = self._format_insights_for_synthesis(segment)
            segment_result = await segment_synthesis_agent.run(formatted_segment)
            segment_summaries.append(segment_result.output)

        # Combine segments into final summary
        combined_segments = "\n\n".join(segment_summaries)
        final_result = await hierarchical_synthesis_agent.run(combined_segments)
        return final_result.output

    def _format_insights_for_synthesis(self, insights: list[ChunkInsights]) -> str:
        """Format insights into a structured prompt for synthesis agent."""
        formatted_sections = []

        for i, chunk_insights in enumerate(insights):
            section_header = (
                f"## Chunk {i + 1} (Importance: {chunk_insights.importance})"
            )
            formatted_sections.append(section_header)

            # Add insights
            insights_text = "\n".join(
                f"- {insight}" for insight in chunk_insights.insights
            )
            formatted_sections.append("**Key Insights:**")
            formatted_sections.append(insights_text)

            # Add themes if present
            if chunk_insights.themes:
                themes_text = ", ".join(chunk_insights.themes)
                formatted_sections.append(f"**Themes:** {themes_text}")

            # Add actions if present
            if chunk_insights.actions:
                actions_text = "\n".join(
                    f"- {action}" for action in chunk_insights.actions
                )
                formatted_sections.append("**Actions:**")
                formatted_sections.append(actions_text)

            formatted_sections.append("")  # Add blank line between chunks

        return "\n".join(formatted_sections)

    def _group_insights_into_segments(
        self, insights: list[ChunkInsights], segments: int = 3
    ) -> list[list[ChunkInsights]]:
        """Group insights into time-based segments for hierarchical synthesis."""
        if not insights:
            return []

        segment_size = max(1, len(insights) // segments)
        grouped_segments = []

        for i in range(0, len(insights), segment_size):
            segment = insights[i : i + segment_size]
            grouped_segments.append(segment)

        return grouped_segments
