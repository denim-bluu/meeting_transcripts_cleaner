"""Intelligence domain protocols - defines interfaces for intelligence processing."""

from typing import Protocol, runtime_checkable

from transcript.models import VTTChunk

from .models import ChunkInsights, MeetingIntelligence


@runtime_checkable
class ChunkingStrategy(Protocol):
    """Protocol for creating semantic chunks from VTT chunks."""

    def create_chunks(self, vtt_chunks: list[VTTChunk]) -> list[str]:
        """Create semantic chunks from VTT chunks.

        Args:
            vtt_chunks: List of VTT chunks from transcript processing

        Returns:
            List of semantic chunk texts ready for extraction
        """
        ...


@runtime_checkable
class ExtractionStrategy(Protocol):
    """Protocol for extracting insights from semantic chunks."""

    async def extract_insights(
        self, chunks: list[str], detail_level: str = "comprehensive"
    ) -> list[ChunkInsights]:
        """Extract insights from semantic chunks.

        Args:
            chunks: List of semantic chunk texts
            detail_level: Level of detail for extraction

        Returns:
            List of extracted insights per chunk
        """
        ...


@runtime_checkable
class SynthesisStrategy(Protocol):
    """Protocol for synthesizing meeting intelligence from insights."""

    async def synthesize_intelligence(
        self, insights: list[ChunkInsights], strategy: str = "direct"
    ) -> MeetingIntelligence:
        """Synthesize meeting intelligence from extracted insights.

        Args:
            insights: List of chunk insights
            strategy: Synthesis strategy ("direct" or "hierarchical")

        Returns:
            Final meeting intelligence
        """
        ...
