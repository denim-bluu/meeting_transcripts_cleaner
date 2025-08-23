"""Factory functions for service assembly with dependency injection."""

from application.ports.protocols import (
    ChunkingStrategy,
    ExtractionStrategy,
    SynthesisStrategy,
    TaskRepository,
    TranscriptCleaner,
    TranscriptParser,
    TranscriptReviewer,
)
from infrastructure.repositories.task_repository import InMemoryTaskRepository
from infrastructure.strategies.insight_extraction_strategy import (
    InsightExtractionStrategy,
)
from infrastructure.strategies.intelligence_synthesis_strategy import (
    IntelligenceSynthesisStrategy,
)
from infrastructure.strategies.semantic_chunking_strategy import (
    SemanticChunkingStrategy,
)
from services.transcript.cleaning_service import TranscriptCleaningService
from services.transcript.review_service import TranscriptReviewService
from services.transcript.vtt_processor import VTTProcessor


def create_transcript_processor(
    api_key: str,
    parser: TranscriptParser | None = None,
    cleaner: TranscriptCleaner | None = None,
    reviewer: TranscriptReviewer | None = None,
    task_repo: TaskRepository | None = None,
):
    """Factory with optional dependency overrides for testing."""
    from application.services.transcript_processor import TranscriptProcessor

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
    from application.services.intelligence_processor import (
        IntelligenceProcessor,
    )

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
