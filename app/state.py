"""Application state for the Reflex frontend."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any, TypedDict

from dotenv import load_dotenv
import reflex as rx

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
from shared.utils.exports import generate_export_content
from shared.utils.files import (
    format_file_size,
    generate_download_filename,
    validate_file_metadata,
)

load_dotenv()

try:  # pragma: no cover - defensive logging configuration
    configure_structlog()
except Exception:  # pragma: no cover - logging setup failure should not break UI
    logging.getLogger(__name__).warning("Failed to configure logging for Reflex app.")


class ChunkReviewDisplay(TypedDict):
    index_label: str
    quality_score: str
    quality_label: str
    quality_badge_class: str
    status_label: str
    status_badge_class: str
    original_text: str
    cleaned_text: str
    confidence_text: str
    has_issues: bool
    issues_text: str


class KeyAreaDisplay(TypedDict):
    title: str
    meta: str
    summary: str
    highlights: list[str]
    decisions: list[str]
    actions: list[str]
    supporting_text: str
    has_highlights: bool
    has_decisions: bool
    has_actions: bool
    has_supporting: bool


class ActionItemDisplay(TypedDict):
    title: str
    owner_text: str
    due_text: str
    confidence_text: str
    has_confidence: bool


class ValidationDisplay(TypedDict):
    status_label: str
    status_class: str
    has_issues: bool
    issues_text: str
    has_unresolved: bool
    unresolved_text: str
    has_notes: bool
    notes_text: str


class State(rx.State):
    """Shared application state across Reflex pages."""

    uploaded_file_name: str = ""
    uploaded_file_size: int = 0
    upload_preview: str = ""
    upload_preview_truncated: bool = False
    upload_error: str = ""

    vtt_content: str = ""

    is_processing: bool = False
    processing_status: str = ""
    processing_progress: float = 0.0
    processing_complete: bool = False
    transcript_error: str = ""
    transcript_data: dict[str, Any] = {}

    intelligence_running: bool = False
    intelligence_status: str = ""
    intelligence_progress: float = 0.0
    intelligence_error: str = ""
    intelligence_data: dict[str, Any] = {}

    last_download_error: str = ""
    current_page: str = "/"

    @rx.event
    def set_current_page(self, page: str):
        """Update the current page for navigation highlighting."""
        self.current_page = page

    def _create_normalized_progress_callback(
        self,
        progress_attr: str,
        status_attr: str,
    ) -> Callable[[float, str], None] | Callable[[float, str], Awaitable[None]]:
        """Create a normalized progress callback that updates state attributes.

        Normalizes progress values to [0.0, 1.0] and handles errors silently.
        Returns an async callback that properly updates Reflex state.

        Args:
            progress_attr: Name of the state attribute to update with progress (float)
            status_attr: Name of the state attribute to update with status message (str)

        Returns:
            Async callback function that can be passed to backend services
        """
        async def on_progress(pct: float, msg: str) -> None:
            try:
                # Normalize progress to valid range
                pct = max(0.0, min(1.0, pct))
                # Update state attributes directly - Reflex will detect these changes
                setattr(self, progress_attr, pct)
                setattr(self, status_attr, msg)
            except Exception:
                # Silently ignore errors in progress callbacks
                # Don't let UI updates crash the backend processing
                pass

        return on_progress

    @rx.event
    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle uploaded VTT file and store metadata for processing."""

        if not files:
            return

        file = files[0]
        self.upload_error = ""
        self.transcript_error = ""
        self.processing_complete = False
        self.processing_status = ""
        self.processing_progress = 0.0
        self.transcript_data = {}
        self.intelligence_data = {}

        try:
            data = await file.read()
        except Exception as exc:  # pragma: no cover - I/O guard
            logging.exception("Failed to read uploaded file: %s", exc)
            self.upload_error = f"Failed to read file: {exc}"
            return

        size_bytes = len(data)
        is_valid, message = validate_file_metadata(file.name, size_bytes)
        if not is_valid:
            self.upload_error = message
            return

        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            self.upload_error = "Unable to decode file. Ensure the file is UTF-8 encoded."
            return

        preview_length = min(len(content), 2000)

        self.uploaded_file_name = file.name
        self.uploaded_file_size = size_bytes
        self.vtt_content = content
        self.upload_preview = content[:preview_length]
        self.upload_preview_truncated = len(content) > preview_length
        self.processing_status = "Ready to process"

    @rx.event
    def clear_upload(self):
        """Reset upload-related state."""

        self.uploaded_file_name = ""
        self.uploaded_file_size = 0
        self.upload_preview = ""
        self.upload_preview_truncated = False
        self.upload_error = ""
        self.vtt_content = ""
        self.processing_status = ""
        self.processing_progress = 0.0
        self.processing_complete = False
        self.transcript_data = {}
        self.transcript_error = ""
        self.intelligence_data = {}
        self.intelligence_status = ""
        self.intelligence_error = ""

    @rx.event
    async def start_processing(self):
        """Execute the transcript processing pipeline."""

        if not self.vtt_content:
            self.upload_error = "Upload a VTT file before processing."
            return

        if self.is_processing:
            return

        self.is_processing = True
        self.processing_status = "Processing transcript..."
        self.processing_progress = 0.05
        self.transcript_error = ""

        yield

        on_progress = self._create_normalized_progress_callback(
            "processing_progress",
            "processing_status",
        )

        # Run pipeline in background task while periodically yielding for UI updates
        async def run_pipeline():
            return await run_transcript_pipeline_async(self.vtt_content, on_progress)

        pipeline_task = asyncio.create_task(run_pipeline())

        try:
            # Periodically yield to allow Reflex to process state updates
            while not pipeline_task.done():
                await asyncio.sleep(0.1)  # Check every 100ms
                yield
            result = await pipeline_task
        except Exception as exc:  # pragma: no cover - backend guard
            logging.exception("Transcript processing failed: %s", exc)
            self.transcript_error = (
                f"{ERROR_MESSAGES['processing_failed']} ({type(exc).__name__}: {exc})"
            )
            self.is_processing = False
            self.processing_status = ""
            self.processing_progress = 0.0
            yield
            return

        # Progress already updated by callback
        self.transcript_data = result.model_dump()
        self.processing_complete = True
        self.is_processing = False
        self.processing_progress = 1.0
        self.current_page = "/review"

        yield rx.redirect("/review")

    @rx.event
    async def extract_intelligence(self):
        """Run the intelligence pipeline on cleaned transcript chunks."""

        if not self.transcript_data:
            self.intelligence_error = ERROR_MESSAGES["missing_transcript"]
            return

        if self.intelligence_running:
            return

        self.intelligence_running = True
        self.intelligence_status = "Extracting insights..."
        self.intelligence_progress = 0.0
        self.intelligence_error = ""

        yield

        # Extract chunks from nested transcript structure
        transcript_info = self.transcript_data.get("transcript", {})
        chunks = rehydrate_vtt_chunks(transcript_info.get("chunks", []))
        if not chunks:
            self.intelligence_error = "No chunks available for intelligence extraction. Please process a transcript first."
            self.intelligence_running = False
            self.intelligence_status = ""
            self.intelligence_progress = 0.0
            yield
            return

        on_progress = self._create_normalized_progress_callback(
            "intelligence_progress",
            "intelligence_status",
        )

        # Run pipeline in background task while periodically yielding for UI updates
        async def run_pipeline():
            return await run_intelligence_pipeline_async(chunks, on_progress)

        pipeline_task = asyncio.create_task(run_pipeline())

        try:
            # Periodically yield to allow Reflex to process state updates
            while not pipeline_task.done():
                await asyncio.sleep(0.1)  # Check every 100ms
                yield
            result = await pipeline_task
        except Exception as exc:  # pragma: no cover - backend guard
            logging.exception("Intelligence extraction failed: %s", exc)
            self.intelligence_error = (
                f"{ERROR_MESSAGES['intelligence_failed']} ({type(exc).__name__}: {exc})"
            )
            self.intelligence_running = False
            self.intelligence_status = ""
            self.intelligence_progress = 0.0
            yield
            return

        # Progress already updated by callback
        self.intelligence_data = result
        self.intelligence_running = False
        self.intelligence_status = "Intelligence ready"
        self.intelligence_progress = 1.0

    @rx.event
    def download_transcript(self, format_type: str):
        """Download processed transcript data in the requested format."""

        if not self.transcript_data:
            self.last_download_error = ERROR_MESSAGES["missing_transcript"]
            return

        self.last_download_error = ""
        filename_base = self.uploaded_file_name or "transcript.vtt"
        filename = generate_download_filename(filename_base, "cleaned", format_type)
        content, mime_type = generate_export_content(self.transcript_data, format_type)

        yield rx.download(data=content, filename=filename, mime_type=mime_type)

    @rx.event
    def download_intelligence(self, format_type: str):
        """Download intelligence data."""

        if not self.intelligence_data:
            self.last_download_error = ERROR_MESSAGES["missing_transcript"]
            return

        self.last_download_error = ""
        filename_base = self.uploaded_file_name or "transcript.vtt"
        filename = generate_download_filename(filename_base, "intelligence", format_type)
        content, mime_type = generate_export_content(self.intelligence_data, format_type)

        yield rx.download(data=content, filename=filename, mime_type=mime_type)

    # ------------------------------------------------------------------
    # Derived values for UI rendering
    # ------------------------------------------------------------------

    @rx.var
    def has_uploaded_file(self) -> bool:
        return bool(self.vtt_content)

    @rx.var
    def processing_disabled(self) -> bool:
        return (not bool(self.vtt_content)) or self.is_processing

    @rx.var
    def upload_size_display(self) -> str:
        if not self.uploaded_file_size:
            return ""
        return format_file_size(self.uploaded_file_size)

    @rx.var
    def has_transcript(self) -> bool:
        return bool(self.transcript_data)

    @rx.var
    def transcript_chunks(self) -> list[dict[str, Any]]:
        transcript_info = self.transcript_data.get("transcript", {})
        return list(transcript_info.get("chunks", []))

    @rx.var
    def transcript_cleaned_chunks(self) -> list[dict[str, Any]]:
        return list(self.transcript_data.get("cleaned_chunks", []))

    @rx.var
    def transcript_review_results(self) -> list[dict[str, Any]]:
        return list(self.transcript_data.get("review_results", []))

    @rx.var
    def transcript_chunk_count(self) -> int:
        return len(self.transcript_chunks)

    @rx.var
    def transcript_has_chunks(self) -> bool:
        return len(self.transcript_chunks) > 0

    @rx.var
    def transcript_total_entries(self) -> int:
        return sum(len(chunk.get("entries", [])) for chunk in self.transcript_chunks)

    @rx.var
    def transcript_speakers(self) -> list[str]:
        transcript_info = self.transcript_data.get("transcript", {})
        speakers = transcript_info.get("speakers", [])
        return list(speakers)

    @rx.var
    def transcript_speakers_display(self) -> str:
        """Display speakers as comma-separated string, with fallback."""
        return format_speakers_display(self.transcript_speakers)

    @rx.var
    def transcript_has_speakers(self) -> bool:
        transcript_info = self.transcript_data.get("transcript", {})
        speakers = transcript_info.get("speakers", [])
        return len(speakers) > 0

    @rx.var
    def transcript_duration_display(self) -> str:
        transcript_info = self.transcript_data.get("transcript", {})
        duration = float(transcript_info.get("duration", 0.0))
        if duration <= 0:
            return "0s"
        if duration < 60:
            return f"{duration:.1f}s"
        minutes = int(duration // 60)
        seconds = duration % 60
        return f"{minutes}m {seconds:.0f}s"

    @rx.var
    def transcript_acceptance_count(self) -> int:
        return sum(1 for review in self.transcript_review_results if review and review.get("accept"))

    @rx.var
    def transcript_average_quality(self) -> float:
        scores = [review.get("quality_score", 0.0) for review in self.transcript_review_results if review]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @rx.var
    def transcript_acceptance_rate(self) -> float:
        total = len(self.transcript_review_results)
        if total == 0:
            return 0.0
        accepted = self.transcript_acceptance_count
        return accepted / total

    @rx.var
    def transcript_acceptance_rate_display(self) -> str:
        rate = self.transcript_acceptance_rate
        if rate == 0:
            return "—"
        return f"{rate * 100:.0f}%"

    @rx.var
    def transcript_acceptance_helper(self) -> str:
        display = self.transcript_acceptance_rate_display
        if display == "—":
            return "—"
        return f"{display} acceptance"

    @rx.var
    def transcript_average_quality_display(self) -> str:
        avg = self.transcript_average_quality
        if avg == 0:
            return "—"
        return f"{avg * 100:.0f}%"

    @rx.var
    def transcript_quality_high(self) -> int:
        return sum(
            1
            for review in self.transcript_review_results
            if review and review.get("quality_score", 0.0) >= 0.8
        )

    @rx.var
    def transcript_quality_medium(self) -> int:
        return sum(
            1
            for review in self.transcript_review_results
            if review and 0.6 <= review.get("quality_score", 0.0) < 0.8
        )

    @rx.var
    def transcript_quality_low(self) -> int:
        return sum(
            1
            for review in self.transcript_review_results
            if review and review.get("quality_score", 0.0) < 0.6
        )

    @rx.var
    def transcript_quality_breakdown(self) -> dict[str, int]:
        breakdown = {"high": 0, "medium": 0, "low": 0}
        for review in self.transcript_review_results:
            if not review:
                continue
            score = review.get("quality_score", 0.0)
            if score >= 0.8:
                breakdown["high"] += 1
            elif score >= 0.6:
                breakdown["medium"] += 1
            else:
                breakdown["low"] += 1
        return breakdown

    @rx.var
    def transcript_chunk_pairs(self) -> list[ChunkReviewDisplay]:
        """Transform chunks into display-ready pairs using pure transformer."""
        return transform_chunk_pairs(
            self.transcript_chunks,
            self.transcript_cleaned_chunks,
            self.transcript_review_results,
        )

    @rx.var
    def has_intelligence(self) -> bool:
        return bool(self.intelligence_data)

    @rx.var
    def intelligence_action_items(self) -> list[dict[str, Any]]:
        return list(self.intelligence_data.get("action_items", []))

    @rx.var
    def intelligence_key_areas(self) -> list[dict[str, Any]]:
        return list(self.intelligence_data.get("key_areas", []))

    @rx.var
    def intelligence_confidence(self) -> float:
        return float(self.intelligence_data.get("confidence") or 0.0)

    @rx.var
    def intelligence_confidence_display(self) -> str:
        confidence = self.intelligence_confidence
        if confidence <= 0:
            return "—"
        return f"{confidence * 100:.0f}%"

    @rx.var
    def intelligence_has_action_items(self) -> bool:
        return len(self.intelligence_action_items) > 0

    @rx.var
    def intelligence_has_key_areas(self) -> bool:
        return len(self.intelligence_key_areas) > 0

    @rx.var
    def intelligence_action_item_count(self) -> int:
        return len(self.intelligence_action_items)

    @rx.var
    def intelligence_key_area_count(self) -> int:
        return len(self.intelligence_key_areas)

    @rx.var
    def processing_progress_percent(self) -> str:
        pct = max(0.0, min(1.0, self.processing_progress))
        return f"{pct * 100:.0f}%"

    @rx.var
    def intelligence_progress_percent(self) -> str:
        pct = max(0.0, min(1.0, self.intelligence_progress))
        return f"{pct * 100:.0f}%"

    @rx.var
    def intelligence_summary_text(self) -> str:
        summary = self.intelligence_data.get("summary") if self.intelligence_data else ""
        if isinstance(summary, str) and summary.strip():
            return summary
        return "Summary not available."

    @rx.var
    def cleansed_transcript_text(self) -> str:
        """Get the final cleansed transcript text."""
        if not self.transcript_data:
            return ""

        # Try final_transcript first
        final_transcript = self.transcript_data.get("final_transcript") or ""
        if isinstance(final_transcript, str) and final_transcript.strip():
            return final_transcript

        # Fallback: construct from cleaned_chunks
        cleaned_chunks = self.transcript_data.get("cleaned_chunks") or []
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

    @rx.var
    def intelligence_key_area_cards(self) -> list[KeyAreaDisplay]:
        """Transform intelligence key areas into display-ready cards."""
        return transform_key_area_cards(self.intelligence_key_areas)

    @rx.var
    def intelligence_action_item_cards(self) -> list[ActionItemDisplay]:
        """Transform intelligence action items into display-ready cards."""
        return transform_action_item_cards(self.intelligence_action_items)

    @rx.var
    def intelligence_validation_display(self) -> ValidationDisplay:
        stats = self.intelligence_data.get("processing_stats") if self.intelligence_data else {}
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
            self.intelligence_data.get("aggregation_artifacts")
            if self.intelligence_data
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


