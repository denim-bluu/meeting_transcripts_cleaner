"""Application state management for Dash frontend.

This module provides pure utility functions for state access and transformation.
All functions are pure (no side effects) to improve testability and enable
multi-session support.
"""

from __future__ import annotations

import asyncio
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


def get_default_state() -> dict[str, Any]:
    """Get default empty state."""
    return {
        "uploaded_file_name": "",
        "uploaded_file_size": 0,
        "upload_preview": "",
        "upload_preview_truncated": False,
        "upload_error": "",
        "vtt_content": "",
        "is_processing": False,
        "processing_complete": False,
        "transcript_error": "",
        "transcript_data": {},
        "intelligence_running": False,
        "intelligence_error": "",
        "intelligence_data": {},
        "last_download_error": "",
        "current_page": "/",
    }


async def handle_upload(content: str, filename: str, current_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Handle uploaded VTT file and return state updates.

    Args:
        content: File content as string
        filename: Original filename
        current_state: Current state dict (optional, for resetting related fields)

    Returns:
        Dict with state updates to merge into store
    """
    state = current_state or {}

    size_bytes = len(content.encode("utf-8"))
    is_valid, message = validate_file_metadata(filename, size_bytes)
    if not is_valid:
        return {
            "upload_error": message,
            "success": False,
            "error": message,
        }

    preview_length = min(len(content), 2000)

    return {
        "uploaded_file_name": filename,
        "uploaded_file_size": size_bytes,
        "vtt_content": content,
        "upload_preview": content[:preview_length],
        "upload_preview_truncated": len(content) > preview_length,
        "upload_error": "",
        "transcript_error": "",
        "processing_complete": False,
        "transcript_data": {},
        "intelligence_data": {},
        "success": True,
    }


def clear_upload_state() -> dict[str, Any]:
    """Return state updates to clear upload-related state."""
    return {
        "uploaded_file_name": "",
        "uploaded_file_size": 0,
        "upload_preview": "",
        "upload_preview_truncated": False,
        "upload_error": "",
        "vtt_content": "",
        "processing_complete": False,
        "transcript_data": {},
        "transcript_error": "",
        "intelligence_data": {},
        "intelligence_error": "",
    }


async def start_processing(
    vtt_content: str,
    current_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the transcript processing pipeline.

    Args:
        vtt_content: VTT file content
        current_state: Current state dict

    Returns:
        Dict with processing status and state updates
    """
    if not vtt_content:
        return {
            "success": False,
            "error": "No file uploaded",
            "upload_error": "Upload a VTT file before processing.",
        }

    state = current_state or {}
    if state.get("is_processing", False):
        return {"success": False, "error": "Already processing"}

    try:
        result = await run_transcript_pipeline_async(vtt_content)
        return {
            "success": True,
            "data": result.model_dump(),
            "transcript_data": result.model_dump(),
            "processing_complete": True,
            "is_processing": False,
        }
    except Exception as exc:  # pragma: no cover - backend guard
        logging.exception("Transcript processing failed: %s", exc)
        error_msg = f"{ERROR_MESSAGES['processing_failed']} ({type(exc).__name__}: {exc})"
        return {
            "success": False,
            "error": error_msg,
            "transcript_error": error_msg,
            "is_processing": False,
        }


async def extract_intelligence(
    transcript_data: dict[str, Any],
    current_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the intelligence pipeline on cleaned transcript chunks.

    Args:
        transcript_data: Transcript data dict
        current_state: Current state dict

    Returns:
        Dict with intelligence extraction status and state updates
    """
    if not transcript_data:
        error_msg = ERROR_MESSAGES["missing_transcript"]
        return {
            "success": False,
            "error": error_msg,
            "intelligence_error": error_msg,
        }

    state = current_state or {}
    if state.get("intelligence_running", False):
        return {"success": False, "error": "Already running"}

    # Extract chunks from nested transcript structure
    transcript_info = transcript_data.get("transcript", {})
    chunks = rehydrate_vtt_chunks(transcript_info.get("chunks", []))
    if not chunks:
        error_msg = "No chunks available for intelligence extraction. Please process a transcript first."
        return {
            "success": False,
            "error": error_msg,
            "intelligence_error": error_msg,
            "intelligence_running": False,
        }

    try:
        result = await run_intelligence_pipeline_async(chunks)
        return {
            "success": True,
            "data": result,
            "intelligence_data": result,
            "intelligence_running": False,
        }
    except Exception as exc:  # pragma: no cover - backend guard
        logging.exception("Intelligence extraction failed: %s", exc)
        error_msg = f"{ERROR_MESSAGES['intelligence_failed']} ({type(exc).__name__}: {exc})"
        return {
            "success": False,
            "error": error_msg,
            "intelligence_error": error_msg,
            "intelligence_running": False,
        }


# Pure state accessor functions (accept data dict as argument)
def has_uploaded_file(data: dict[str, Any]) -> bool:
    """Check if a file has been uploaded."""
    return bool(data.get("vtt_content"))


def get_processing_disabled(data: dict[str, Any]) -> bool:
    """Check if processing should be disabled."""
    return (not bool(data.get("vtt_content"))) or data.get("is_processing", False)


def get_upload_size_display(data: dict[str, Any]) -> str:
    """Get formatted file size."""
    size = data.get("uploaded_file_size", 0)
    if not size:
        return ""
    return format_file_size(size)


def has_transcript(data: dict[str, Any]) -> bool:
    """Check if transcript data exists."""
    return bool(data.get("transcript_data"))


def get_transcript_chunks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get transcript chunks."""
    transcript_data = data.get("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    return list(transcript_info.get("chunks", []))


def get_transcript_cleaned_chunks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get cleaned chunks."""
    transcript_data = data.get("transcript_data", {})
    return list(transcript_data.get("cleaned_chunks", []))


def get_transcript_review_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get review results."""
    transcript_data = data.get("transcript_data", {})
    return list(transcript_data.get("review_results", []))


def get_transcript_chunk_count(data: dict[str, Any]) -> int:
    """Get chunk count."""
    return len(get_transcript_chunks(data))


def get_transcript_has_chunks(data: dict[str, Any]) -> bool:
    """Check if chunks exist."""
    return len(get_transcript_chunks(data)) > 0


def get_transcript_total_entries(data: dict[str, Any]) -> int:
    """Get total entry count."""
    chunks = get_transcript_chunks(data)
    return sum(len(chunk.get("entries", [])) for chunk in chunks)


def get_transcript_speakers(data: dict[str, Any]) -> list[str]:
    """Get speakers list."""
    transcript_data = data.get("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    speakers = transcript_info.get("speakers", [])
    return list(speakers)


def get_transcript_speakers_display(data: dict[str, Any]) -> str:
    """Get formatted speakers display."""
    return format_speakers_display(get_transcript_speakers(data))


def get_transcript_has_speakers(data: dict[str, Any]) -> bool:
    """Check if speakers exist."""
    transcript_data = data.get("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    speakers = transcript_info.get("speakers", [])
    return len(speakers) > 0


def get_transcript_duration_display(data: dict[str, Any]) -> str:
    """Get formatted duration."""
    transcript_data = data.get("transcript_data", {})
    transcript_info = transcript_data.get("transcript", {})
    duration = float(transcript_info.get("duration", 0.0))
    if duration <= 0:
        return "0s"
    if duration < 60:
        return f"{duration:.1f}s"
    minutes = int(duration // 60)
    seconds = duration % 60
    return f"{minutes}m {seconds:.0f}s"


def get_transcript_acceptance_count(data: dict[str, Any]) -> int:
    """Get acceptance count."""
    reviews = get_transcript_review_results(data)
    return sum(1 for review in reviews if review and review.get("accept"))


def get_transcript_average_quality(data: dict[str, Any]) -> float:
    """Get average quality score."""
    reviews = get_transcript_review_results(data)
    scores = [review.get("quality_score", 0.0) for review in reviews if review]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def get_transcript_acceptance_rate(data: dict[str, Any]) -> float:
    """Get acceptance rate."""
    total = len(get_transcript_review_results(data))
    if total == 0:
        return 0.0
    accepted = get_transcript_acceptance_count(data)
    return accepted / total


def get_transcript_acceptance_rate_display(data: dict[str, Any]) -> str:
    """Get formatted acceptance rate."""
    rate = get_transcript_acceptance_rate(data)
    if rate == 0:
        return "—"
    return f"{rate * 100:.0f}%"


def get_transcript_acceptance_helper(data: dict[str, Any]) -> str:
    """Get acceptance helper text."""
    display = get_transcript_acceptance_rate_display(data)
    if display == "—":
        return "—"
    return f"{display} acceptance"


def get_transcript_average_quality_display(data: dict[str, Any]) -> str:
    """Get formatted average quality."""
    avg = get_transcript_average_quality(data)
    if avg == 0:
        return "—"
    return f"{avg * 100:.0f}%"


def get_transcript_quality_high(data: dict[str, Any]) -> int:
    """Get high quality count."""
    reviews = get_transcript_review_results(data)
    return sum(
        1
        for review in reviews
        if review and review.get("quality_score", 0.0) >= 0.8
    )


def get_transcript_quality_medium(data: dict[str, Any]) -> int:
    """Get medium quality count."""
    reviews = get_transcript_review_results(data)
    return sum(
        1
        for review in reviews
        if review and 0.6 <= review.get("quality_score", 0.0) < 0.8
    )


def get_transcript_quality_low(data: dict[str, Any]) -> int:
    """Get low quality count."""
    reviews = get_transcript_review_results(data)
    return sum(
        1
        for review in reviews
        if review and review.get("quality_score", 0.0) < 0.6
    )


def get_transcript_chunk_pairs(data: dict[str, Any]) -> list[ChunkReviewDisplay]:
    """Transform chunks into display-ready pairs."""
    return transform_chunk_pairs(
        get_transcript_chunks(data),
        get_transcript_cleaned_chunks(data),
        get_transcript_review_results(data),
    )


def has_intelligence(data: dict[str, Any]) -> bool:
    """Check if intelligence data exists."""
    return bool(data.get("intelligence_data"))


def get_intelligence_action_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get action items."""
    intelligence_data = data.get("intelligence_data", {})
    return list(intelligence_data.get("action_items", []))


def get_intelligence_key_areas(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get key areas."""
    intelligence_data = data.get("intelligence_data", {})
    return list(intelligence_data.get("key_areas", []))


def get_intelligence_confidence(data: dict[str, Any]) -> float:
    """Get confidence score."""
    intelligence_data = data.get("intelligence_data", {})
    return float(intelligence_data.get("confidence") or 0.0)


def get_intelligence_confidence_display(data: dict[str, Any]) -> str:
    """Get formatted confidence."""
    confidence = get_intelligence_confidence(data)
    if confidence <= 0:
        return "—"
    return f"{confidence * 100:.0f}%"


def get_intelligence_has_action_items(data: dict[str, Any]) -> bool:
    """Check if action items exist."""
    return len(get_intelligence_action_items(data)) > 0


def get_intelligence_has_key_areas(data: dict[str, Any]) -> bool:
    """Check if key areas exist."""
    return len(get_intelligence_key_areas(data)) > 0


def get_intelligence_action_item_count(data: dict[str, Any]) -> int:
    """Get action item count."""
    return len(get_intelligence_action_items(data))


def get_intelligence_key_area_count(data: dict[str, Any]) -> int:
    """Get key area count."""
    return len(get_intelligence_key_areas(data))


def get_processing_progress_percent(data: dict[str, Any]) -> str:
    """Get formatted progress percentage."""
    return "0%"


def get_intelligence_progress_percent(data: dict[str, Any]) -> str:
    """Get formatted intelligence progress."""
    return "0%"


def get_intelligence_running(data: dict[str, Any]) -> bool:
    """Check if intelligence extraction is running."""
    return bool(data.get("intelligence_running", False))


def get_intelligence_status(data: dict[str, Any]) -> str:
    """Get intelligence extraction status."""
    return ""


def get_intelligence_error(data: dict[str, Any]) -> str:
    """Get intelligence extraction error."""
    return str(data.get("intelligence_error", ""))


def get_last_download_error(data: dict[str, Any]) -> str:
    """Get last download error."""
    return str(data.get("last_download_error", ""))


def get_intelligence_summary_text(data: dict[str, Any]) -> str:
    """Get summary text."""
    intelligence_data = data.get("intelligence_data", {})
    summary = intelligence_data.get("summary") if intelligence_data else ""
    if isinstance(summary, str) and summary.strip():
        return summary
    return "Summary not available."


def get_cleansed_transcript_text(data: dict[str, Any]) -> str:
    """Get the final cleansed transcript text."""
    transcript_data = data.get("transcript_data", {})
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


def get_intelligence_key_area_cards(data: dict[str, Any]) -> list[KeyAreaDisplay]:
    """Transform intelligence key areas into display-ready cards."""
    return transform_key_area_cards(get_intelligence_key_areas(data))


def get_intelligence_action_item_cards(data: dict[str, Any]) -> list[ActionItemDisplay]:
    """Transform intelligence action items into display-ready cards."""
    return transform_action_item_cards(get_intelligence_action_items(data))


def get_intelligence_validation_display(data: dict[str, Any]) -> ValidationDisplay:
    """Get validation display data."""
    intelligence_data = data.get("intelligence_data", {})
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
