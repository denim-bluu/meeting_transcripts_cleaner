"""Shared transcript processing pipelines."""

from dataclasses import asdict, is_dataclass
from typing import Any

from backend.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
from backend.transcript.models import TranscriptProcessingResult, VTTChunk
from backend.transcript.services.transcript_service import TranscriptService
from shared.types import ProgressCallback


def _serialize_value(value: Any) -> Any:
    """Convert dataclasses and Pydantic models to plain python structures."""

    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()  # type: ignore[no-any-return]
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


async def run_transcript_pipeline_async(
    content_str: str,
    api_key: str | None = None,
) -> TranscriptProcessingResult:
    """Async transcript pipeline.

    Processes VTT content through parsing, cleaning, and review stages.
    Returns serialized transcript data suitable for frontend consumption.
    """
    service = TranscriptService(api_key=api_key or "")
    processing_result = service.process_vtt(content_str)

    result = await service.clean_transcript(
        processing_result
    )
    return result


def rehydrate_vtt_chunks(raw_chunks: list[dict[str, Any]]) -> list[VTTChunk]:
    """Recreate VTTChunk objects from serialized dicts."""
    return [VTTChunk.model_validate(chunk_data) for chunk_data in raw_chunks]


async def run_intelligence_pipeline_async(
    chunks: list[VTTChunk] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Async intelligence extraction pipeline.

    Processes transcript chunks to extract meeting intelligence including
    summaries, key areas, action items, and validation results.
    """

    if not chunks:
        raise ValueError("No chunks provided for intelligence extraction")

    orchestrator = IntelligenceOrchestrator()

    # Rehydrate serialized chunks if needed
    if chunks and not isinstance(chunks[0], VTTChunk):
        chunks = rehydrate_vtt_chunks(chunks)

    result = await orchestrator.process_meeting(chunks)  # type: ignore[arg-type]
    return _serialize_value(result)
