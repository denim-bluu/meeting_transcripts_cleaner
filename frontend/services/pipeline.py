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


def run_transcript_pipeline(
    content_str: str, on_progress: Callable[[float, str], None]
) -> dict[str, Any]:
    """End-to-end transcript processing for Streamlit UI.

    Steps: parse VTT -> create chunks -> async clean+review with progress.
    Returns a JSON-serializable dict suitable for the existing UI components.
    """
    service = TranscriptService(api_key="")  # settings provide actual key

    # Parse/chunk synchronously
    transcript = service.process_vtt(content_str)

    # Progress passthrough
    def progress_sync(pct: float, msg: str) -> None:
        try:
            # Clamp for safety
            pct = max(0.0, min(1.0, pct))
            on_progress(pct, msg)
        except Exception:
            pass

    # Run cleaning/review (async)
    result = run_async(
        service.clean_transcript(transcript, progress_callback=progress_sync)
    )

    # Convert dataclasses and pydantic models for Streamlit/front-end
    return _serialize_transcript_dict(result)


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


def run_intelligence_pipeline(
    chunks_raw_or_dataclass: list[Any], on_progress: Callable[[float, str], None]
) -> dict[str, Any]:
    """Run intelligence extraction on cleaned transcript chunks.

    Accepts either serialized chunk dicts (from session state) or dataclass chunks.
    Returns a plain dict (model_dump) for UI consumption.
    """
    orchestrator = IntelligenceOrchestrator()

    # Accept both dataclasses and dicts
    if chunks_raw_or_dataclass and not isinstance(chunks_raw_or_dataclass[0], VTTChunk):
        vtt_chunks = rehydrate_vtt_chunks(chunks_raw_or_dataclass)  # type: ignore[arg-type]
    else:
        vtt_chunks = chunks_raw_or_dataclass  # type: ignore[assignment]

    def progress_sync(pct: float, msg: str) -> None:
        try:
            pct = max(0.0, min(1.0, pct))
            on_progress(pct, msg)
        except Exception:
            pass

    result = run_async(
        orchestrator.process_meeting(vtt_chunks, progress_callback=progress_sync)
    )
    return result.model_dump()
