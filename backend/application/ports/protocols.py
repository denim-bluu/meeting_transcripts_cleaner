"""Protocol interfaces for dependency injection and SOLID compliance."""

from typing import Protocol, runtime_checkable

from core.task_cache import TaskEntry
from models.intelligence import ChunkInsights, MeetingIntelligence
from models.transcript import CleaningResult, ReviewResult, VTTChunk, VTTEntry


@runtime_checkable
class TranscriptParser(Protocol):
    """Parses VTT files into structured entries and chunks for AI processing.

    Responsibilities:
    - Parse WebVTT format strictly following spec
    - Extract timestamps, speakers, text from <v> tags
    - Create processing chunks with ~3000 token limits
    - Handle malformed VTT gracefully (skip bad entries, log issues)

    Behaviors:
    - parse_vtt() returns ALL valid entries, skips malformed ones
    - create_chunks() groups entries by speaker continuity + token limits
    - MUST preserve exact speaker names from VTT
    - MUST maintain chronological order
    """

    def parse_vtt(self, content: str) -> list[VTTEntry]: ...
    def create_chunks(self, entries: list[VTTEntry]) -> list[VTTChunk]: ...


@runtime_checkable
class TranscriptCleaner(Protocol):
    """Cleans transcript text using AI while preserving speaker attribution."""

    async def clean_chunk(
        self, chunk: VTTChunk, prev_text: str = ""
    ) -> CleaningResult: ...


@runtime_checkable
class TranscriptReviewer(Protocol):
    """Reviews cleaned text quality and determines acceptance."""

    async def review_chunk(
        self, original: VTTChunk, cleaned: str
    ) -> ReviewResult: ...


@runtime_checkable
class ChunkingStrategy(Protocol):
    """Breaks transcript into semantic chunks optimized for LLM processing."""

    def create_chunks(self, vtt_chunks: list[VTTChunk]) -> list[str]: ...


@runtime_checkable
class ExtractionStrategy(Protocol):
    """Extracts structured insights from transcript chunks using AI."""

    async def extract_insights(
        self, chunk_text: str, context: dict
    ) -> ChunkInsights: ...


@runtime_checkable
class SynthesisStrategy(Protocol):
    """Synthesizes insights into comprehensive meeting intelligence."""

    async def synthesize(
        self, insights: list[ChunkInsights]
    ) -> MeetingIntelligence: ...


@runtime_checkable
class TaskRepository(Protocol):
    """Abstracts task storage for async processing status tracking."""

    async def store_task(self, task: TaskEntry) -> None: ...
    async def get_task(self, task_id: str) -> TaskEntry | None: ...
    async def update_task(self, task_id: str, **updates) -> None: ...
