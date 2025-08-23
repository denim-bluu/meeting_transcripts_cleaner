"""Intelligence synthesis strategy wrapper."""

from agents.synthesis.direct import direct_synthesis_agent
from models.intelligence import ChunkInsights, MeetingIntelligence


class IntelligenceSynthesisStrategy:
    """Wrapper for synthesis agents implementing SynthesisStrategy protocol."""

    async def synthesize(self, insights: list[ChunkInsights]) -> MeetingIntelligence:
        # Format insights into string prompt for the agent
        formatted_insights = self._format_insights_for_synthesis(insights)
        
        # Use direct synthesis for now - add hierarchical logic later
        result = await direct_synthesis_agent.run(formatted_insights)
        return result.output
    
    def _format_insights_for_synthesis(self, insights: list[ChunkInsights]) -> str:
        """Format insights into a structured prompt for synthesis agent."""
        formatted_sections = []
        
        for i, chunk_insights in enumerate(insights):
            section_header = f"## Chunk {i + 1} (Importance: {chunk_insights.importance})"
            formatted_sections.append(section_header)
            
            # Add insights
            insights_text = "\n".join(f"- {insight}" for insight in chunk_insights.insights)
            formatted_sections.append("**Key Insights:**")
            formatted_sections.append(insights_text)
            
            # Add themes if present
            if chunk_insights.themes:
                themes_text = ", ".join(chunk_insights.themes)
                formatted_sections.append(f"**Themes:** {themes_text}")
            
            # Add actions if present
            if chunk_insights.actions:
                actions_text = "\n".join(f"- {action}" for action in chunk_insights.actions)
                formatted_sections.append("**Actions:**")
                formatted_sections.append(actions_text)
            
            formatted_sections.append("")  # Add blank line between chunks
        
        return "\n".join(formatted_sections)
