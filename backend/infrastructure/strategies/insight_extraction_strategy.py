"""Insight extraction strategy wrapper."""

from agents.extraction.insights import chunk_extraction_agent
from models.intelligence import ChunkInsights
from pydantic_ai import RunContext


class InsightExtractionStrategy:
    """Wrapper for extraction agents implementing ExtractionStrategy protocol."""

    async def extract_insights(self, chunk_text: str, context: dict) -> ChunkInsights:
        result = await chunk_extraction_agent.run(chunk_text, deps=context)
        return result.output
