"""Application state for the Reflex frontend."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from dotenv import load_dotenv
import reflex as rx

from app.config import ERROR_MESSAGES
from app.services.pipeline import (
    run_intelligence_pipeline_async,
    run_transcript_pipeline_async,
)
from app.utils.exports import generate_export_content
from app.utils.files import (
    format_file_size,
    generate_download_filename,
    validate_file_metadata,
)
from backend.config import configure_structlog

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

        progress_state = {
            "pct": self.processing_progress,
            "status": self.processing_status,
        }

        yield

        def on_progress(pct: float, msg: str) -> None:
            progress_state["pct"] = pct
            progress_state["status"] = msg

        try:
            result = await run_transcript_pipeline_async(self.vtt_content, on_progress)
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

        self.processing_progress = progress_state.get("pct", 1.0)
        status_msg = progress_state.get("status", "Processing complete")
        self.processing_status = status_msg or "Processing complete"
        self.transcript_data = result
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

        # Use raw chunks (VTTChunk objects) for intelligence pipeline
        # The intelligence pipeline needs VTTChunk objects with entries, not CleaningResult objects
        raw_chunks = self.transcript_data.get("chunks", [])
        if not raw_chunks:
            self.intelligence_error = "No chunks available for intelligence extraction. Please process a transcript first."
            self.intelligence_running = False
            self.intelligence_status = ""
            self.intelligence_progress = 0.0
            yield
            return

        payload = raw_chunks

        progress_state = {
            "status": self.intelligence_status,
            "pct": self.intelligence_progress,
        }

        def on_progress(pct: float, msg: str) -> None:
            progress_state["pct"] = pct
            progress_state["status"] = msg
            self.intelligence_progress = pct
            self.intelligence_status = msg

        try:
            result = await run_intelligence_pipeline_async(payload or [], on_progress)
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

        status_msg = progress_state.get("status", "Intelligence ready")
        self.intelligence_status = status_msg or "Intelligence ready"
        self.intelligence_progress = progress_state.get("pct", 1.0)
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
        return list(self.transcript_data.get("chunks", []))

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
        speakers = self.transcript_data.get("speakers") or []
        return list(speakers)

    @rx.var
    def transcript_speakers_display(self) -> str:
        speakers = self.transcript_data.get("speakers") or []
        return ", ".join(speakers)

    @rx.var
    def transcript_speakers_display_or_placeholder(self) -> str:
        speakers = self.transcript_data.get("speakers") or []
        if not speakers:
            return "—"
        return ", ".join(speakers)

    @rx.var
    def transcript_has_speakers(self) -> bool:
        speakers = self.transcript_data.get("speakers") or []
        return len(speakers) > 0

    @rx.var
    def transcript_duration_display(self) -> str:
        duration = float(self.transcript_data.get("duration") or 0.0)
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
        pairs: list[ChunkReviewDisplay] = []
        chunks = self.transcript_chunks
        cleaned_chunks = self.transcript_cleaned_chunks
        review_results = self.transcript_review_results

        for idx, chunk in enumerate(chunks):
            cleaned = cleaned_chunks[idx] if idx < len(cleaned_chunks) else {}
            review = review_results[idx] if idx < len(review_results) else {}

            quality_score = float(review.get("quality_score", 0.0)) if review else 0.0
            accept = bool(review.get("accept", False)) if review else False
            issues = [str(issue) for issue in (review.get("issues") or []) if issue]
            confidence_text = self._format_confidence(cleaned.get("confidence")) if cleaned else ""

            pairs.append(
                {
                    "index_label": f"Chunk {idx + 1}",
                    "quality_score": f"{quality_score:.2f}",
                    "quality_label": self._quality_label(quality_score),
                    "quality_badge_class": self._quality_badge_class(quality_score),
                    "status_label": "Accepted" if accept else "Needs Review",
                    "status_badge_class": self._status_badge_class(accept),
                    "original_text": self._format_original_chunk(chunk),
                    "cleaned_text": cleaned.get("cleaned_text", "—") if cleaned else "—",
                    "confidence_text": confidence_text,
                    "has_issues": len(issues) > 0,
                    "issues_text": "\n".join(issues),
                }
            )
        return pairs

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
    def intelligence_processing_time(self) -> float:
        stats = self.intelligence_data.get("processing_stats") or {}
        return float(stats.get("time_ms", 0.0)) / 1000.0

    @rx.var
    def intelligence_confidence_display(self) -> str:
        confidence = self.intelligence_confidence
        if confidence <= 0:
            return "—"
        return f"{confidence * 100:.0f}%"

    @rx.var
    def intelligence_processing_time_display(self) -> str:
        duration = self.intelligence_processing_time
        if duration <= 0:
            return "—"
        if duration < 60:
            return f"{duration:.1f}s"
        minutes = int(duration // 60)
        seconds = duration % 60
        return f"{minutes}m {seconds:.0f}s"

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
    def intelligence_summary_html(self) -> str:
        """Convert markdown summary to HTML."""
        try:
            import markdown

            summary = self.intelligence_summary_text
            if not summary or summary == "Summary not available.":
                return "<p>Summary not available.</p>"

            md = markdown.Markdown(extensions=["fenced_code", "tables", "nl2br"])
            html = md.convert(summary)
            return html
        except ImportError:
            # Fallback to plain text if markdown library not available
            summary = self.intelligence_summary_text
            if not summary or summary == "Summary not available.":
                return "Summary not available."
            # Simple conversion: newlines to <br>, bold/headers preserved as-is for now
            lines = summary.split("\n")
            html_lines = []
            for line in lines:
                if line.strip().startswith("###"):
                    text = line.replace("###", "").strip()
                    html_lines.append(f"<h3>{text}</h3>")
                elif line.strip().startswith("##"):
                    text = line.replace("##", "").strip()
                    html_lines.append(f"<h2>{text}</h2>")
                elif line.strip().startswith("#"):
                    text = line.replace("#", "").strip()
                    html_lines.append(f"<h1>{text}</h1>")
                elif line.strip().startswith("-") or line.strip().startswith("*"):
                    text = line.strip().lstrip("-* ").strip()
                    html_lines.append(f"<li>{text}</li>")
                elif line.strip():
                    html_lines.append(f"<p>{line}</p>")
                else:
                    html_lines.append("<br>")
            return "".join(html_lines) if html_lines else summary

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
        cards: list[KeyAreaDisplay] = []
        for area in self.intelligence_key_areas:
            if not isinstance(area, dict):
                continue
            title = str(area.get("title") or "Theme")
            summary = str(area.get("summary") or "Summary unavailable.")

            temporal_span = str(area.get("temporal_span") or "Timeline not specified")
            confidence = area.get("confidence")
            meta_parts: list[str] = []
            if temporal_span:
                meta_parts.append(temporal_span)
            if isinstance(confidence, (float, int)):
                meta_parts.append(f"Confidence {float(confidence) * 100:.0f}%")
            meta = " • ".join(meta_parts) if meta_parts else "Timeline not specified"

            highlights = [str(point) for point in (area.get("bullet_points") or []) if point]

            decisions_raw = area.get("decisions") or []
            decisions = [self._format_decision(decision) for decision in decisions_raw if decision]

            actions_raw = area.get("action_items") or []
            actions = [self._format_action_item(action) for action in actions_raw if action]

            supporting = area.get("supporting_chunks") or []
            supporting_chunks = ", ".join(str(chunk) for chunk in supporting) if supporting else ""
            supporting_text = (
                f"Supporting chunks: {supporting_chunks}" if supporting_chunks else ""
            )

            cards.append(
                {
                    "title": title,
                    "meta": meta,
                    "summary": summary,
                    "highlights": highlights,
                    "decisions": decisions,
                    "actions": actions,
                    "supporting_text": supporting_text,
                    "has_highlights": len(highlights) > 0,
                    "has_decisions": len(decisions) > 0,
                    "has_actions": len(actions) > 0,
                    "has_supporting": bool(supporting_text),
                }
            )
        return cards

    @rx.var
    def intelligence_action_item_cards(self) -> list[ActionItemDisplay]:
        cards: list[ActionItemDisplay] = []
        for item in self.intelligence_action_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("description") or "Action item")
            owner = str(item.get("owner") or "Unassigned")
            due = str(item.get("due_date") or "No due date")

            confidence_text = self._format_confidence(item.get("confidence"))

            cards.append(
                {
                    "title": title,
                    "owner_text": f"Owner: {owner}",
                    "due_text": f"Due: {due}",
                    "confidence_text": confidence_text,
                    "has_confidence": bool(confidence_text),
                }
            )
        return cards

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
        issue_lines = [self._format_validation_issue(issue) for issue in issues_raw if issue]
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_confidence(self, confidence: Any) -> str:
        if confidence is None:
            return ""
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            return ""
        return f"Confidence: {value * 100:.0f}%"

    def _format_original_chunk(self, chunk: dict[str, Any]) -> str:
        entries = chunk.get("entries") if isinstance(chunk, dict) else None
        if entries is None and hasattr(chunk, "entries"):
            entries = chunk.entries
        if not entries:
            return "—"

        lines: list[str] = []
        for entry in entries:
            speaker = entry.get("speaker") if isinstance(entry, dict) else getattr(entry, "speaker", "Speaker")
            text = entry.get("text") if isinstance(entry, dict) else getattr(entry, "text", "")
            start_time = entry.get("start_time") if isinstance(entry, dict) else getattr(entry, "start_time", 0.0)
            timestamp = self._format_timestamp(float(start_time))
            lines.append(f"[{timestamp}] {speaker or 'Speaker'}: {text}")
        return "\n".join(lines) if lines else "—"

    def _quality_label(self, score: float) -> str:
        if score >= 0.8:
            return "High Quality"
        if score >= 0.6:
            return "Medium Quality"
        return "Low Quality"

    def _quality_badge_class(self, score: float) -> str:
        if score >= 0.8:
            return "text-xs font-bold px-2 py-1 border-2 border-black bg-cyan-300 text-black"
        if score >= 0.6:
            return "text-xs font-bold px-2 py-1 border-2 border-black bg-yellow-200 text-black"
        return "text-xs font-bold px-2 py-1 border-2 border-black bg-red-300 text-black"

    def _status_badge_class(self, accepted: bool) -> str:
        base = "text-xs font-bold px-3 py-1 border-2 border-black "
        suffix = "bg-cyan-300 text-black" if accepted else "bg-yellow-200 text-black"
        return f"{base}{suffix}"

    def _format_decision(self, decision: Any) -> str:
        if isinstance(decision, dict):
            statement = str(decision.get("statement") or "Decision")
            decided_by = str(decision.get("decided_by") or "Unknown")
            rationale = str(decision.get("rationale") or "No rationale provided")
            return f"{statement} (by {decided_by}, rationale: {rationale})"
        return str(decision)

    def _format_action_item(self, action: Any) -> str:
        if isinstance(action, dict):
            description = str(action.get("description") or "Action")
            owner = str(action.get("owner") or "Unassigned")
            due = str(action.get("due_date") or "No due date")
            return f"{description} (owner: {owner}, due: {due})"
        return str(action)

    def _format_validation_issue(self, issue: Any) -> str:
        if isinstance(issue, dict):
            level = str(issue.get("level", "info")).upper()
            message = str(issue.get("message") or "No details")
            related = issue.get("related_chunks") or []
            related_text = ", ".join(str(chunk) for chunk in related) if related else ""
            context = f" (chunks: {related_text})" if related_text else ""
            return f"[{level}] {message}{context}"
        return str(issue)

    def _format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

