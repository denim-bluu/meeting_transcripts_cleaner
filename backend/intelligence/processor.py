"""Intelligence processing orchestration using configurable strategies."""

from collections.abc import Callable

import structlog
from tasks.protocols import TaskRepository
from transcript.models import VTTChunk

from .models import MeetingIntelligence
from .protocols import (
    ChunkingStrategy,
    ExtractionStrategy,
    SynthesisStrategy,
)

logger = structlog.get_logger(__name__)


class IntelligenceProcessor:
    """Orchestrates intelligence extraction using configurable strategies."""

    def __init__(
        self,
        chunking_strategy: ChunkingStrategy,
        extraction_strategy: ExtractionStrategy,
        synthesis_strategy: SynthesisStrategy,
        task_repo: TaskRepository,
    ):
        self._chunking = chunking_strategy
        self._extraction = extraction_strategy
        self._synthesis = synthesis_strategy
        self._task_repo = task_repo

    async def process_meeting(
        self,
        cleaned_chunks: list[VTTChunk],
        detail_level: str = "comprehensive",
        progress_callback: Callable | None = None,
    ) -> MeetingIntelligence:
        """Extract meeting intelligence - same interface as IntelligenceOrchestrator.process_meeting()"""

        # Phase 1: Semantic chunking
        if progress_callback:
            progress_callback(0.1, "Creating semantic chunks...")
        semantic_chunks = self._chunking.create_chunks(cleaned_chunks)

        # Phase 2: Extract insights
        if progress_callback:
            progress_callback(0.3, "Extracting insights...")
        insights = await self._extraction.extract_insights(
            semantic_chunks, detail_level
        )

        if progress_callback:
            progress_callback(
                0.8, f"Extracted insights from {len(semantic_chunks)} chunks"
            )

        # Phase 3: Synthesize intelligence
        if progress_callback:
            progress_callback(0.9, "Synthesizing meeting intelligence...")
        intelligence = await self._synthesis.synthesize_intelligence(insights, "direct")

        if progress_callback:
            progress_callback(1.0, "Intelligence extraction complete")

        return intelligence
