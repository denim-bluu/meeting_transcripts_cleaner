"""Pure transformer functions for state data formatting.

These functions transform raw state data into display-ready formats.
They are pure functions (no side effects) to improve testability.
"""

from __future__ import annotations

from typing import Any

from shared.utils.time_formatters import format_timestamp_vtt


def format_speakers_display(speakers: list[str], placeholder: str = "—") -> str:
    """Format speakers list as comma-separated string."""
    if not speakers:
        return placeholder
    return ", ".join(speakers)


def format_confidence(confidence: Any) -> str:
    """Format confidence value as percentage string."""
    if confidence is None:
        return ""
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return ""
    return f"Confidence: {value * 100:.0f}%"


def format_decision(decision: Any) -> str:
    """Format decision dict as readable string."""
    if isinstance(decision, dict):
        statement = str(decision.get("statement") or "Decision")
        decided_by = str(decision.get("decided_by") or "Unknown")
        rationale = str(decision.get("rationale") or "No rationale provided")
        return f"{statement} (by {decided_by}, rationale: {rationale})"
    return str(decision)


def format_action_item(action: Any) -> str:
    """Format action item dict as readable string."""
    if isinstance(action, dict):
        description = str(action.get("description") or "Action")
        owner = str(action.get("owner") or "Unassigned")
        due = str(action.get("due_date") or "No due date")
        return f"{description} (owner: {owner}, due: {due})"
    return str(action)


def format_validation_issue(issue: Any) -> str:
    """Format validation issue dict as readable string."""
    if isinstance(issue, dict):
        level = str(issue.get("level", "info")).upper()
        message = str(issue.get("message") or "No details")
        related = issue.get("related_chunks") or []
        related_text = ", ".join(str(chunk) for chunk in related) if related else ""
        context = f" (chunks: {related_text})" if related_text else ""
        return f"[{level}] {message}{context}"
    return str(issue)


def format_original_chunk(chunk: dict[str, Any]) -> str:
    """Format chunk entries as readable text with timestamps."""
    entries = chunk.get("entries") if isinstance(chunk, dict) else None
    if entries is None and hasattr(chunk, "entries"):
        entries = chunk.entries
    if not entries:
        return "—"

    lines: list[str] = []
    for entry in entries:
        speaker = (
            entry.get("speaker")
            if isinstance(entry, dict)
            else getattr(entry, "speaker", "Speaker")
        )
        text = (
            entry.get("text")
            if isinstance(entry, dict)
            else getattr(entry, "text", "")
        )
        start_time = (
            entry.get("start_time")
            if isinstance(entry, dict)
            else getattr(entry, "start_time", 0.0)
        )
        timestamp = format_timestamp_vtt(float(start_time))
        lines.append(f"[{timestamp}] {speaker or 'Speaker'}: {text}")
    return "\n".join(lines) if lines else "—"


def quality_label(score: float) -> str:
    """Get quality label for score."""
    if score >= 0.8:
        return "High Quality"
    if score >= 0.6:
        return "Medium Quality"
    return "Low Quality"


def quality_badge_class(score: float) -> str:
    """Get CSS class for quality badge."""
    if score >= 0.8:
        return "text-xs font-bold px-2 py-1 border-2 border-black bg-cyan-300 text-black"
    if score >= 0.6:
        return "text-xs font-bold px-2 py-1 border-2 border-black bg-yellow-200 text-black"
    return "text-xs font-bold px-2 py-1 border-2 border-black bg-red-300 text-black"


def status_badge_class(accepted: bool) -> str:
    """Get CSS class for status badge."""
    base = "text-xs font-bold px-3 py-1 border-2 border-black "
    suffix = "bg-cyan-300 text-black" if accepted else "bg-yellow-200 text-black"
    return f"{base}{suffix}"


def transform_chunk_pairs(
    chunks: list[dict[str, Any]],
    cleaned_chunks: list[dict[str, Any]],
    review_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Transform chunks into display-ready chunk review pairs."""
    pairs: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        cleaned = cleaned_chunks[idx] if idx < len(cleaned_chunks) else {}
        review = review_results[idx] if idx < len(review_results) else {}

        quality_score = (
            float(review.get("quality_score", 0.0)) if review else 0.0
        )
        accept = bool(review.get("accept", False)) if review else False
        issues = [str(issue) for issue in (review.get("issues") or []) if issue]
        confidence_text = (
            format_confidence(cleaned.get("confidence")) if cleaned else ""
        )

        pairs.append(
            {
                "index_label": f"Chunk {idx + 1}",
                "quality_score": f"{quality_score:.2f}",
                "quality_label": quality_label(quality_score),
                "quality_badge_class": quality_badge_class(quality_score),
                "status_label": "Accepted" if accept else "Needs Review",
                "status_badge_class": status_badge_class(accept),
                "original_text": format_original_chunk(chunk),
                "cleaned_text": cleaned.get("cleaned_text", "—") if cleaned else "—",
                "confidence_text": confidence_text,
                "has_issues": len(issues) > 0,
                "issues_text": "\n".join(issues),
            }
        )
    return pairs


def transform_key_area_cards(key_areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform intelligence key areas into display-ready cards."""
    cards: list[dict[str, Any]] = []
    for area in key_areas:
        if not isinstance(area, dict):
            continue
        title = str(area.get("title") or "Theme")
        summary = str(area.get("summary") or "Summary unavailable.")

        temporal_span = str(area.get("temporal_span") or "Timeline not specified")
        confidence = area.get("confidence")
        meta_parts: list[str] = []
        if temporal_span:
            meta_parts.append(temporal_span)
        if isinstance(confidence, float | int):
            meta_parts.append(f"Confidence {float(confidence) * 100:.0f}%")
        meta = " • ".join(meta_parts) if meta_parts else "Timeline not specified"

        highlights = [
            str(point) for point in (area.get("bullet_points") or []) if point
        ]

        decisions_raw = area.get("decisions") or []
        decisions = [format_decision(decision) for decision in decisions_raw if decision]

        actions_raw = area.get("action_items") or []
        actions = [format_action_item(action) for action in actions_raw if action]

        supporting = area.get("supporting_chunks") or []
        supporting_chunks = (
            ", ".join(str(chunk) for chunk in supporting) if supporting else ""
        )
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


def transform_action_item_cards(action_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform intelligence action items into display-ready cards."""
    cards: list[dict[str, Any]] = []
    for item in action_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("description") or "Action item")
        owner = str(item.get("owner") or "Unassigned")
        due = str(item.get("due_date") or "No due date")

        confidence_text = format_confidence(item.get("confidence"))

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

