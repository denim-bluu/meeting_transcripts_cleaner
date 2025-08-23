"""Insight extraction strategy wrapper."""

from ..agents.extractor import chunk_extraction_agent
from ..models import ChunkInsights


class InsightExtractionStrategy:
    """Wrapper for extraction agents implementing ExtractionStrategy protocol."""

    async def extract_insights(
        self, chunks: list[str], detail_level: str = "comprehensive"
    ) -> list[ChunkInsights]:
        """Extract insights from semantic chunks."""
        results = []

        for i, chunk_text in enumerate(chunks):
            context = {
                "detail_level": detail_level,
                "position": "start"
                if i == 0
                else "end"
                if i == len(chunks) - 1
                else "middle",
                "chunk_index": i,
                "total_chunks": len(chunks),
            }

            result = await chunk_extraction_agent.run(chunk_text, deps=context)
            results.append(result.output)

        return results
