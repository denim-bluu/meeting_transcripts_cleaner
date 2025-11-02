"""Export helpers for transcript and intelligence outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def generate_export_content(
    data: dict[str, Any], format_type: str, include_metadata: bool = True
) -> tuple[str, str]:
    """Generate export content in the requested format."""
    format_type = format_type.lower()

    if format_type == "vtt":
        return _format_as_vtt(data), "text/vtt"
    if format_type == "md":
        return _format_as_markdown(data, include_metadata), "text/markdown"
    if format_type == "txt":
        return _format_as_text(data, include_metadata), "text/plain"
    if format_type == "json":
        import json

        return json.dumps(data, indent=2, ensure_ascii=False), "application/json"

    return str(data), "text/plain"


def _format_as_vtt(data: dict[str, Any]) -> str:
    """Format data as WebVTT."""
    lines = ["WEBVTT", ""]

    chunks = data.get("chunks", [])
    for chunk in chunks:
        for entry in chunk.get("entries", []):
            start_formatted = _format_timestamp(entry.get("start_time", 0.0))
            end_formatted = _format_timestamp(entry.get("end_time", 0.0))
            speaker = entry.get("speaker", "Speaker")
            text = entry.get("text", "")
            cue_id = entry.get("cue_id")

            if cue_id:
                lines.append(str(cue_id))
            lines.append(f"{start_formatted} --> {end_formatted}")
            lines.append(f"{speaker}: {text}")
            lines.append("")

    return "\n".join(lines)


def _format_timestamp(seconds: float) -> str:
    """Format seconds as VTT timestamp (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _format_as_markdown(data: dict[str, Any], include_metadata: bool) -> str:
    """Format data as Markdown."""
    lines: list[str] = []
    lines.append("# Meeting Transcript Results\n")

    summary = data.get("summary")
    if summary:
        lines.append("## Summary\n")
        lines.append(f"{summary}\n")

    final_transcript = data.get("final_transcript") or data.get("cleaned_transcript")
    if final_transcript:
        lines.append("## Cleaned Transcript\n")
        lines.append(f"```\n{final_transcript}\n```\n")

    action_items = data.get("action_items") or []
    if action_items:
        lines.append("## Action Items\n")
        for idx, item in enumerate(action_items, 1):
            if isinstance(item, dict):
                description = item.get("description", str(item))
                owner = item.get("owner")
                due_date = item.get("due_date")
                lines.append(f"{idx}. {description}")
                if owner:
                    lines.append(f"   - **Owner:** {owner}")
                if due_date:
                    lines.append(f"   - **Due:** {due_date}")
            else:
                lines.append(f"{idx}. {item}")
            lines.append("")

    key_areas = data.get("key_areas") or []
    if key_areas:
        lines.append("## Key Areas\n")
        for area in key_areas:
            lines.append(f"### {area.get('title', 'Theme')}\n")
            if area.get("summary"):
                lines.append(f"{area['summary']}\n")
            bullet_points = area.get("bullet_points") or []
            if bullet_points:
                lines.append("**Highlights:**")
                for point in bullet_points:
                    lines.append(f"- {point}")
                lines.append("")

    artifacts = data.get("aggregation_artifacts") or {}
    timeline_events = artifacts.get("timeline_events") or []
    if timeline_events:
        lines.append("## Timeline Highlights\n")
        for event in timeline_events:
            lines.append(f"- {event}")
        lines.append("")

    unresolved_topics = artifacts.get("unresolved_topics") or []
    if unresolved_topics:
        lines.append("## Unresolved Topics\n")
        for topic in unresolved_topics:
            lines.append(f"- {topic}")
        lines.append("")

    if include_metadata and "processing_stats" in data:
        lines.append("## Processing Statistics\n")
        stats = data["processing_stats"]
        for key, value in stats.items():
            formatted_key = key.replace("_", " ").title()
            lines.append(f"- **{formatted_key}:** {value}")

    return "\n".join(lines)


def _format_as_text(data: dict[str, Any], include_metadata: bool) -> str:
    """Format data as plain text."""
    lines: list[str] = []
    lines.append("MEETING TRANSCRIPT RESULTS")
    lines.append("=" * 50)
    lines.append("")

    lines.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    summary = data.get("summary")
    if summary:
        lines.append("SUMMARY:")
        lines.append("-" * 20)
        lines.append(summary)
        lines.append("")

    final_transcript = data.get("final_transcript") or data.get("cleaned_transcript")
    if final_transcript:
        lines.append("CLEANED TRANSCRIPT:")
        lines.append("-" * 30)
        lines.append(final_transcript)
        lines.append("")

    action_items = data.get("action_items") or []
    if action_items:
        lines.append("ACTION ITEMS:")
        lines.append("-" * 20)
        for idx, item in enumerate(action_items, 1):
            if isinstance(item, dict):
                description = item.get("description", str(item))
                owner = item.get("owner")
                due_date = item.get("due_date")
                lines.append(f"{idx}. {description}")
                if owner:
                    lines.append(f"   Owner: {owner}")
                if due_date:
                    lines.append(f"   Due: {due_date}")
            else:
                lines.append(f"{idx}. {item}")
            lines.append("")

    if include_metadata and "processing_stats" in data:
        lines.append("PROCESSING STATISTICS:")
        lines.append("-" * 30)
        stats = data["processing_stats"]
        for key, value in stats.items():
            formatted_key = key.replace("_", " ").title()
            lines.append(f"{formatted_key}: {value}")

    return "\n".join(lines)

