"""Factory functions for service assembly with dependency injection."""

from intelligence.chunker import SemanticChunker
from intelligence.protocols import (
    ChunkingStrategy,
    ExtractionStrategy,
    SynthesisStrategy,
)
from intelligence.strategies.extraction import InsightExtractionStrategy
from intelligence.strategies.synthesis import IntelligenceSynthesisStrategy
from tasks.protocols import TaskRepository
from tasks.repository import InMemoryTaskRepository
from transcript.parser import VTTProcessor
from transcript.protocols import (
    TranscriptCleaner,
    TranscriptParser,
    TranscriptReviewer,
)
from transcript.services.cleaner import TranscriptCleaningService
from transcript.services.reviewer import TranscriptReviewService


class SemanticChunkingStrategy:
    """Wrapper to match protocol interface."""

    def __init__(self):
        self.chunker = SemanticChunker()

    def create_chunks(self, vtt_chunks):
        return self.chunker.create_chunks(vtt_chunks)


def create_transcript_processor(
    api_key: str,
    parser: TranscriptParser | None = None,
    cleaner: TranscriptCleaner | None = None,
    reviewer: TranscriptReviewer | None = None,
    task_repo: TaskRepository | None = None,
):
    """Factory with optional dependency overrides for testing."""
    from transcript.processor import TranscriptProcessor

    return TranscriptProcessor(
        parser=parser or VTTProcessor(),
        cleaner=cleaner or TranscriptCleaningService(),
        reviewer=reviewer or TranscriptReviewService(),
        task_repo=task_repo or InMemoryTaskRepository(),
    )


def create_intelligence_processor(
    api_key: str,
    chunking_strategy: ChunkingStrategy | None = None,
    extraction_strategy: ExtractionStrategy | None = None,
    synthesis_strategy: SynthesisStrategy | None = None,
    task_repo: TaskRepository | None = None,
):
    """Factory for intelligence processing with strategy injection."""
    from intelligence.processor import IntelligenceProcessor

    return IntelligenceProcessor(
        chunking_strategy=chunking_strategy or SemanticChunkingStrategy(),
        extraction_strategy=extraction_strategy or InsightExtractionStrategy(),
        synthesis_strategy=synthesis_strategy or IntelligenceSynthesisStrategy(),
        task_repo=task_repo or InMemoryTaskRepository(),
    )


def create_application_services(api_key: str):
    """Create all application services with shared dependencies."""
    shared_task_repo = InMemoryTaskRepository()

    transcript_processor = create_transcript_processor(
        api_key, task_repo=shared_task_repo
    )
    intelligence_processor = create_intelligence_processor(
        api_key, task_repo=shared_task_repo
    )

    return transcript_processor, intelligence_processor
