"""Application state management for Dash frontend.

This module provides state management using Dash's dcc.Store components
and callback-based state updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from dotenv import load_dotenv

from app.utils.state_transformers import (
    format_speakers_display,
    format_validation_issue,
    transform_action_item_cards,
    transform_chunk_pairs,
    transform_key_area_cards,
)
from backend.config import configure_structlog
from shared.config import ERROR_MESSAGES
from shared.services.pipeline import (
    rehydrate_vtt_chunks,
    run_intelligence_pipeline_async,
    run_transcript_pipeline_async,
)
from shared.utils.files import (
    format_file_size,
    generate_download_filename,
    validate_file_metadata,
)

load_dotenv()

try:  # pragma: no cover - defensive logging configuration
    configure_structlog()
except Exception:  # pragma: no cover - logging setup failure should not break UI
    logging.getLogger(__name__).warning("Failed to configure logging for Dash app.")


class ChunkReviewDisplay(dict):
    """Display-ready chunk review data."""

    pass


class KeyAreaDisplay(dict):
    """Display-ready key area data."""

    pass


class ActionItemDisplay(dict):
    """Display-ready action item data."""

    pass


class ValidationDisplay(dict):
    """Display-ready validation data."""

    pass


# Global state storage (in production, consider using Redis or similar)
_app_state: dict[str, Any] = {
    "uploaded_file_name": "",
    "uploaded_file_size": 0,
    "upload_preview": "",
    "upload_preview_truncated": False,
    "upload_error": "",
    "vtt_content": "",
    "is_processing": False,
    "processing_status": "",
    "processing_progress": 0.0,
    "processing_complete": False,
    "transcript_error": "",
    "transcript_data": {},
    "intelligence_running": False,
    "intelligence_status": "",
    "intelligence_progress": 0.0,
    "intelligence_error": "",
    "intelligence_data": {},
    "last_download_error": "",
    "current_page": "/",
}


def get_state() -> dict[str, Any]:
    """Get current application state."""
    return _app_state.copy()


def update_state(**kwargs: Any) -> None:
    """Update application state."""
    _app_state.update(kwargs)


def get_state_value(key: str, default: Any = None) -> Any:
    """Get a specific state value."""
    return _app_state.get(key, default)


def _create_normalized_progress_callback(
    progress_key: str,
    status_key: str,
) -> Callable[[float, str], None] | Callable[[float, str], Awaitable[None]]:
    """Create a normalized progress callback that updates state.

    Args:
        progress_key: Key in state dict for progress (float)
        status_key: Key in state dict for status message (str)

    Returns:
        Async callback function that can be passed to backend services
    """

    async def on_progress(pct: float, msg: str) -> None:
        try:
            # Normalize progress to valid range
            pct = max(0.0, min(1.0, pct))
            # Update state
            update_state(**{progress_key: pct, status_key: msg})
        except Exception:
            # Silently ignore errors in progress callbacks
            pass

    return on_progress


async def handle_upload(content: str, filename: str) -> dict[str, Any]:
    """Handle uploaded VTT file and store metadata for processing.

    Args:
        content: File content as string
        filename: Original filename

    Returns:
        Dict with upload status and any error messages
    """
    update_state(
        upload_error="",
        transcript_error="",
        processing_complete=False,
        processing_status="",
        processing_progress=0.0,
        transcript_data={},
        intelligence_data={},
    )

    size_bytes = len(content.encode("utf-8"))
    is_valid, message = validate_file_metadata(filename, size_bytes)
    if not is_valid:
        update_state(upload_error=message)
        return {"success": False, "error": message}

    preview_length = min(len(content), 2000)

    update_state(
        uploaded_file_name=filename,
        uploaded_file_size=size_bytes,
        vtt_content=content,
        upload_preview=content[:preview_length],
        upload_preview_truncated=len(content) > preview_length,
        processing_status="Ready to process",
    )

    return {"success": True}


def clear_upload() -> None:
    """Reset upload-related state."""
    update_state(
        uploaded_file_name="",
        uploaded_file_size=0,
        upload_preview="",
        upload_preview_truncated=False,
        upload_error="",
        vtt_content="",
        processing_status="",
        processing_progress=0.0,
        processing_complete=False,
        transcript_data={},
        transcript_error="",
        intelligence_data={},
        intelligence_status="",
        intelligence_error="",
    )


async def start_processing() -> dict[str, Any]:
    """Execute the transcript processing pipeline.

    Returns:
        Dict with processing status
    """
    state = get_state()
    vtt_content = state.get("vtt_content", "")

    if not vtt_content:
        update_state(upload_error="Upload a VTT file before processing.")
        return {"success": False, "error": "No file uploaded"}

    if state.get("is_processing", False):
        return {"success": False, "error": "Already processing"}

    update_state(
        is_processing=True,
        processing_status="Processing transcript...",
        processing_progress=0.05,
        transcript_error="",
    )

    on_progress = _create_normalized_progress_callback(
        "processing_progress",
        "processing_status",
    )

    try:
        result = await run_transcript_pipeline_async(vtt_content, on_progress)
        update_state(
            transcript_data=result.model_dump(),
            processing_complete=True,
            is_processing=False,
            processing_progress=1.0,
        )
        return {"success": True, "data": result.model_dump()}
    except Exception as exc:  # pragma: no cover - backend guard
        logging.exception("Transcript processing failed: %s", exc)
        error_msg = f"{ERROR_MESSAGES['processing_failed']} ({type(exc).__name__}: {exc})"
        update_state(
            transcript_error=error_msg,
            is_processing=False,
            processing_status="",
            processing_progress=0.0,
        )
        return {"success": False, "error": error_msg}


async def extract_intelligence() -> dict[str, Any]:
    """Run the intelligence pipeline on cleaned transcript chunks.

    Returns:
        Dict with intelligence extraction status
    """
    state = get_state()
    transcript_data = state.get("transcript_data", {})

    if not transcript_data:
        error_msg = ERROR_MESSAGES["missing_transcript"]
        update_state(intelligence_error=error_msg)
        return {"success": False, "error": error_msg}

    if state.get("intelligence_running", False):
        return {"success": False, "error": "Already running"}

    update_state(
        intelligence_running=True,
        intelligence_status="Extracting insights...",
        intelligence_progress=0.0,
        intelligence_error="",
    )

    # Extract chunks from nested transcript structure
    transcript_info = transcript_data.get("transcript", {})
    chunks = rehydrate_vtt_chunks(transcript_info.get("chunks", []))
    if not chunks:
        error_msg = "No chunks available for intelligence extraction. Please process a transcript first."
        update_state(
            intelligence_error=error_msg,
            intelligence_running=False,
            intelligence_status="",
            intelligence_progress=0.0,
        )
        return {"success": False, "error": error_msg}

    on_progress = _create_normalized_progress_callback(
        "intelligence_progress",
        "intelligence_status",
    )

    try:
        result = await run_intelligence_pipeline_async(chunks, on_progress)
        update_state(
            intelligence_data=result,
            intelligence_running=False,
            intelligence_status="Intelligence ready",
            intelligence_progress=1.0,
        )
        return {"success": True, "data": result}
    except Exception as exc:  # pragma: no cover - backend guard
        logging.exception("Intelligence extraction failed: %s", exc)
        error_msg = f"{ERROR_MESSAGES['intelligence_failed']} ({type(exc).__name__}: {exc})"
        update_state(
            intelligence_error=error_msg,
            intelligence_running=False,
            intelligence_status="",
            intelligence_progress=0.0,
        )
        return {"success": False, "error": error_msg}


# Computed properties (used in callbacks)
def get_has_uploaded_file() -> bool:
    """Check if a file has been uploaded."""
    return bool(get_state_value("vtt_content"))


def get_processing_disabled() -> bool:
    """Check if processing should be disabled."""
    state = get_state()
    return (not bool(state.get("vtt_content"))) or state.get("is_processing", False)


def get_upload_size_display() -> str:
    """Get formatted file size."""
    size = get_state_value("uploaded_file_size", 0)
    if not size:
        return ""
    return format_file_size(size)


def get_has_transcript() -> bool:
    """Check if transcript data exists."""
    return bool(get_state_value("transcript_data"))


def get_transcript_chunks() -> list[dict[str, Any]]:
    """Get transcript chunks."""
    transcript_data = get_state_value("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    return list(transcript_info.get("chunks", []))


def get_transcript_cleaned_chunks() -> list[dict[str, Any]]:
    """Get cleaned chunks."""
    transcript_data = get_state_value("transcript_data", {})
    return list(transcript_data.get("cleaned_chunks", []))


def get_transcript_review_results() -> list[dict[str, Any]]:
    """Get review results."""
    transcript_data = get_state_value("transcript_data", {})
    return list(transcript_data.get("review_results", []))


def get_transcript_chunk_count() -> int:
    """Get chunk count."""
    return len(get_transcript_chunks())


def get_transcript_has_chunks() -> bool:
    """Check if chunks exist."""
    return len(get_transcript_chunks()) > 0


def get_transcript_total_entries() -> int:
    """Get total entry count."""
    chunks = get_transcript_chunks()
    return sum(len(chunk.get("entries", [])) for chunk in chunks)


def get_transcript_speakers() -> list[str]:
    """Get speakers list."""
    transcript_data = get_state_value("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    speakers = transcript_info.get("speakers", [])
    return list(speakers)


def get_transcript_speakers_display() -> str:
    """Get formatted speakers display."""
    return format_speakers_display(get_transcript_speakers())


def get_transcript_has_speakers() -> bool:
    """Check if speakers exist."""
    transcript_data = get_state_value("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    speakers = transcript_info.get("speakers", [])
    return len(speakers) > 0


def get_transcript_duration_display() -> str:
    """Get formatted duration."""
    transcript_data = get_state_value("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    duration = float(transcript_info.get("duration", 0.0))
    if duration <= 0:
        return "0s"
    if duration < 60:
        return f"{duration:.1f}s"
    minutes = int(duration // 60)
    seconds = duration % 60
    return f"{minutes}m {seconds:.0f}s"


def get_transcript_acceptance_count() -> int:
    """Get acceptance count."""
    reviews = get_transcript_review_results()
    return sum(1 for review in reviews if review and review.get("accept"))


def get_transcript_average_quality() -> float:
    """Get average quality score."""
    reviews = get_transcript_review_results()
    scores = [review.get("quality_score", 0.0) for review in reviews if review]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def get_transcript_acceptance_rate() -> float:
    """Get acceptance rate."""
    total = len(get_transcript_review_results())
    if total == 0:
        return 0.0
    accepted = get_transcript_acceptance_count()
    return accepted / total


def get_transcript_acceptance_rate_display() -> str:
    """Get formatted acceptance rate."""
    rate = get_transcript_acceptance_rate()
    if rate == 0:
        return "—"
    return f"{rate * 100:.0f}%"


def get_transcript_acceptance_helper() -> str:
    """Get acceptance helper text."""
    display = get_transcript_acceptance_rate_display()
    if display == "—":
        return "—"
    return f"{display} acceptance"


def get_transcript_average_quality_display() -> str:
    """Get formatted average quality."""
    avg = get_transcript_average_quality()
    if avg == 0:
        return "—"
    return f"{avg * 100:.0f}%"


def get_transcript_quality_high() -> int:
    """Get high quality count."""
    reviews = get_transcript_review_results()
    return sum(
        1
        for review in reviews
        if review and review.get("quality_score", 0.0) >= 0.8
    )


def get_transcript_quality_medium() -> int:
    """Get medium quality count."""
    reviews = get_transcript_review_results()
    return sum(
        1
        for review in reviews
        if review and 0.6 <= review.get("quality_score", 0.0) < 0.8
    )


def get_transcript_quality_low() -> int:
    """Get low quality count."""
    reviews = get_transcript_review_results()
    return sum(
        1
        for review in reviews
        if review and review.get("quality_score", 0.0) < 0.6
    )


def get_transcript_chunk_pairs() -> list[ChunkReviewDisplay]:
    """Transform chunks into display-ready pairs."""
    return transform_chunk_pairs(
        get_transcript_chunks(),
        get_transcript_cleaned_chunks(),
        get_transcript_review_results(),
    )


def get_has_intelligence() -> bool:
    """Check if intelligence data exists."""
    return bool(get_state_value("intelligence_data"))


def get_intelligence_action_items() -> list[dict[str, Any]]:
    """Get action items."""
    intelligence_data = get_state_value("intelligence_data", {})
    return list(intelligence_data.get("action_items", []))


def get_intelligence_key_areas() -> list[dict[str, Any]]:
    """Get key areas."""
    intelligence_data = get_state_value("intelligence_data", {})
    return list(intelligence_data.get("key_areas", []))


def get_intelligence_confidence() -> float:
    """Get confidence score."""
    intelligence_data = get_state_value("intelligence_data", {})
    return float(intelligence_data.get("confidence") or 0.0)


def get_intelligence_confidence_display() -> str:
    """Get formatted confidence."""
    confidence = get_intelligence_confidence()
    if confidence <= 0:
        return "—"
    return f"{confidence * 100:.0f}%"


def get_intelligence_has_action_items() -> bool:
    """Check if action items exist."""
    return len(get_intelligence_action_items()) > 0


def get_intelligence_has_key_areas() -> bool:
    """Check if key areas exist."""
    return len(get_intelligence_key_areas()) > 0


def get_intelligence_action_item_count() -> int:
    """Get action item count."""
    return len(get_intelligence_action_items())


def get_intelligence_key_area_count() -> int:
    """Get key area count."""
    return len(get_intelligence_key_areas())


def get_processing_progress_percent() -> str:
    """Get formatted progress percentage."""
    progress = get_state_value("processing_progress", 0.0)
    pct = max(0.0, min(1.0, progress))
    return f"{pct * 100:.0f}%"


def get_intelligence_progress_percent() -> str:
    """Get formatted intelligence progress."""
    progress = get_state_value("intelligence_progress", 0.0)
    pct = max(0.0, min(1.0, progress))
    return f"{pct * 100:.0f}%"


def get_intelligence_running() -> bool:
    """Check if intelligence extraction is running."""
    return bool(get_state_value("intelligence_running", False))


def get_intelligence_status() -> str:
    """Get intelligence extraction status."""
    return str(get_state_value("intelligence_status", ""))


def get_intelligence_error() -> str:
    """Get intelligence extraction error."""
    return str(get_state_value("intelligence_error", ""))


def get_last_download_error() -> str:
    """Get last download error."""
    return str(get_state_value("last_download_error", ""))


def get_intelligence_summary_text() -> str:
    """Get summary text."""
    intelligence_data = get_state_value("intelligence_data", {})
    summary = intelligence_data.get("summary") if intelligence_data else ""
    if isinstance(summary, str) and summary.strip():
        return summary
    return "Summary not available."


def get_cleansed_transcript_text() -> str:
    """Get the final cleansed transcript text."""
    transcript_data = get_state_value("transcript_data", {})
    if not transcript_data:
        return ""

    # Try final_transcript first
    final_transcript = transcript_data.get("final_transcript") or ""
    if isinstance(final_transcript, str) and final_transcript.strip():
        return final_transcript

    # Fallback: construct from cleaned_chunks
    cleaned_chunks = transcript_data.get("cleaned_chunks") or []
    if cleaned_chunks:
        texts = []
        for chunk in cleaned_chunks:
            if isinstance(chunk, dict):
                cleaned_text = chunk.get("cleaned_text") or ""
                if cleaned_text:
                    texts.append(cleaned_text)
            elif hasattr(chunk, "cleaned_text"):
                texts.append(chunk.cleaned_text)

        if texts:
            return "\n\n".join(texts)

    return ""


def get_intelligence_key_area_cards() -> list[KeyAreaDisplay]:
    """Transform intelligence key areas into display-ready cards."""
    return transform_key_area_cards(get_intelligence_key_areas())


def get_intelligence_action_item_cards() -> list[ActionItemDisplay]:
    """Transform intelligence action items into display-ready cards."""
    return transform_action_item_cards(get_intelligence_action_items())


def get_intelligence_validation_display() -> ValidationDisplay:
    """Get validation display data."""
    intelligence_data = get_state_value("intelligence_data", {})
    stats = intelligence_data.get("processing_stats") if intelligence_data else {}
    stats = stats if isinstance(stats, dict) else {}
    validation = stats.get("validation") if isinstance(stats, dict) else {}
    validation = validation if isinstance(validation, dict) else {}

    passed = bool(validation.get("passed", True))
    status_label = "Validation passed" if passed else "Validation reported issues"
    status_class = (
        "text-sm font-bold px-3 py-1 border-4 border-black bg-cyan-300 text-black"
        if passed
        else "text-sm font-bold px-3 py-1 border-4 border-black bg-yellow-200 text-black"
    )

    issues_raw = validation.get("issues") or []
    issue_lines = [
        format_validation_issue(issue) for issue in issues_raw if issue
    ]
    issues_text = "\n".join(line for line in issue_lines if line)

    artifacts = (
        intelligence_data.get("aggregation_artifacts")
        if intelligence_data
        else {}
    )
    artifacts = artifacts if isinstance(artifacts, dict) else {}

    unresolved = artifacts.get("unresolved_topics") or []
    unresolved_text = "\n".join(str(topic) for topic in unresolved if topic)

    notes = artifacts.get("validation_notes") or []
    notes_text = "\n".join(str(note) for note in notes if note)

    return {
        "status_label": status_label,
        "status_class": status_class,
        "has_issues": bool(issues_text),
        "issues_text": issues_text,
        "has_unresolved": bool(unresolved_text),
        "unresolved_text": unresolved_text,
        "has_notes": bool(notes_text),
        "notes_text": notes_text,
    }
