"""Shared transcript processing pipelines for the Reflex frontend."""

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import Any

from backend.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
from backend.transcript.models import VTTChunk, VTTEntry
from backend.transcript.services.transcript_service import TranscriptService

from .runtime import run_async


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


def _serialize_transcript_dict(transcript: dict[str, Any]) -> dict[str, Any]:
    return {k: _serialize_value(v) for k, v in transcript.items()}


async def run_transcript_pipeline_async(
    content_str: str,
    on_progress: Callable[[float, str], None],
    api_key: str | None = None,
) -> dict[str, Any]:
    """Async transcript pipeline used by the Reflex app."""

    service = TranscriptService(api_key=api_key or "")
    transcript = service.process_vtt(content_str)

    def progress_sync(pct: float, msg: str) -> None:
        try:
            pct = max(0.0, min(1.0, pct))
            on_progress(pct, msg)
        except Exception:
            pass

    result = await service.clean_transcript(transcript, progress_callback=progress_sync)
    return _serialize_transcript_dict(result)


def run_transcript_pipeline(
    content_str: str, on_progress: Callable[[float, str], None], api_key: str | None = None
) -> dict[str, Any]:
    """Synchronous convenience wrapper for environments that need it."""

    return run_async(
        run_transcript_pipeline_async(content_str, on_progress, api_key=api_key)
    )


def rehydrate_vtt_chunks(raw_chunks: list[dict[str, Any]]) -> list[VTTChunk]:
    """Recreate VTTChunk dataclasses from serialized dicts."""

    chunks: list[VTTChunk] = []
    for chunk_data in raw_chunks:
        entries = [
            VTTEntry(
                cue_id=e.get("cue_id", ""),
                start_time=e.get("start_time", 0.0),
                end_time=e.get("end_time", 0.0),
                speaker=e.get("speaker", ""),
                text=e.get("text", ""),
            )
            for e in chunk_data.get("entries", [])
        ]
        chunks.append(
            VTTChunk(
                chunk_id=chunk_data.get("chunk_id", 0),
                entries=entries,
                token_count=chunk_data.get("token_count", 0),
            )
        )
    return chunks


async def run_intelligence_pipeline_async(
    chunks_raw_or_dataclass: list[Any],
    on_progress: Callable[[float, str], None],
) -> dict[str, Any]:
    """Async intelligence extraction pipeline."""

    if not chunks_raw_or_dataclass:
        raise ValueError("No chunks provided for intelligence extraction")

    orchestrator = IntelligenceOrchestrator()

    # Rehydrate serialized chunks if needed
    if not isinstance(chunks_raw_or_dataclass[0], VTTChunk):
        vtt_chunks = rehydrate_vtt_chunks(chunks_raw_or_dataclass)  # type: ignore[arg-type]
    else:
        vtt_chunks = chunks_raw_or_dataclass  # type: ignore[assignment]

    # Filter out empty chunks (chunks with no entries or empty text)
    # After rehydration, all chunks should be VTTChunk objects
    filtered_chunks = []
    for chunk in vtt_chunks:
        if isinstance(chunk, VTTChunk):
            # Check if chunk has entries with non-empty text
            if chunk.entries and any(entry.text.strip() for entry in chunk.entries):
                filtered_chunks.append(chunk)

    if not filtered_chunks:
        raise ValueError(
            "No valid chunks found for intelligence extraction. All chunks are empty or contain no text."
        )

    vtt_chunks = filtered_chunks

    def progress_sync(pct: float, msg: str) -> None:
        try:
            pct = max(0.0, min(1.0, pct))
            on_progress(pct, msg)
        except Exception:
            pass

    result = await orchestrator.process_meeting(vtt_chunks, progress_callback=progress_sync)
    return result.model_dump()


def run_intelligence_pipeline(
    chunks_raw_or_dataclass: list[Any],
    on_progress: Callable[[float, str], None],
) -> dict[str, Any]:
    """Synchronous wrapper for legacy callers."""

    return run_async(
        run_intelligence_pipeline_async(chunks_raw_or_dataclass, on_progress)
    )


