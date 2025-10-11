from datetime import datetime
import json
from typing import Any

import streamlit as st
from utils.helpers import generate_download_filename


class ExportHandler:
    """Centralized export functionality."""

    @staticmethod
    def render_export_section(
        data: dict[str, Any], original_filename: str, export_prefix: str = "processed"
    ) -> None:
        """Render simplified export section with direct download buttons.

        Logic:
        1. Show three essential download buttons: TXT, MD, VTT
        2. Always include metadata for completeness
        3. Use clean, minimal UI
        """
        if not data:
            st.warning("No data available for export")
            return

        st.subheader("📥 Export Results")

        # Simple three-column layout for essential formats
        col1, col2, col3 = st.columns(3)

        formats = [("txt", "📄 TXT"), ("md", "📝 MD"), ("vtt", "📺 VTT")]

        for i, (fmt, label) in enumerate(formats):
            content, mime_type = ExportHandler._generate_export_content(
                data,
                fmt,
                include_metadata=True,  # Always include metadata
            )

            filename = generate_download_filename(original_filename, export_prefix, fmt)

            with [col1, col2, col3][i]:
                st.download_button(
                    label=label,
                    data=content,
                    file_name=filename,
                    mime=mime_type,
                    use_container_width=True,
                )

    @staticmethod
    def render_intelligence_export_section(
        data: dict[str, Any],
        original_filename: str,
        export_prefix: str = "intelligence",
    ) -> None:
        """Render intelligence-specific export section with TXT and MD only.

        Logic:
        1. Show two essential download buttons: TXT, MD (no VTT for intelligence)
        2. Always include metadata for completeness
        3. Use clean, minimal UI optimized for intelligence content
        """
        if not data:
            st.warning("No data available for export")
            return

        st.subheader("📥 Export Results")

        # Two-column layout for intelligence formats
        col1, col2 = st.columns(2)

        formats = [("txt", "📄 TXT"), ("md", "📝 MD")]

        for i, (fmt, label) in enumerate(formats):
            content, mime_type = ExportHandler._generate_export_content(
                data,
                fmt,
                include_metadata=True,  # Always include metadata
            )

            filename = generate_download_filename(original_filename, export_prefix, fmt)

            with [col1, col2][i]:
                st.download_button(
                    label=label,
                    data=content,
                    file_name=filename,
                    mime=mime_type,
                    use_container_width=True,
                )

    @staticmethod
    def _generate_export_content(
        data: dict[str, Any], format_type: str, include_metadata: bool
    ) -> tuple[str, str]:
        """Generate export content for specific format.

        Logic:
        1. Format data according to export type
        2. Include metadata if requested
        3. Return content and appropriate MIME type
        """
        if format_type == "vtt":
            content = ExportHandler._format_as_vtt(data)
            return content, "text/vtt"
        elif format_type == "json":
            content = json.dumps(data, indent=2, ensure_ascii=False)
            return content, "application/json"
        elif format_type == "md":
            content = ExportHandler._format_as_markdown(data, include_metadata)
            return content, "text/markdown"
        elif format_type == "txt":
            content = ExportHandler._format_as_text(data, include_metadata)
            return content, "text/plain"
        else:
            return str(data), "text/plain"

    @staticmethod
    def _format_as_vtt(data: dict[str, Any]) -> str:
        """Format data as VTT transcript file.

        Logic:
        1. Create VTT header
        2. Process chunks and entries with timestamps
        3. Format as WebVTT specification
        """
        vtt_content = "WEBVTT\n\n"

        chunks = data.get("chunks", [])

        for i, chunk in enumerate(chunks):
            entries = chunk.get("entries", [])
            for entry in entries:
                start_time = entry.get("start_time", 0)
                end_time = entry.get("end_time", 0)
                speaker = entry.get("speaker", "Speaker")
                text = entry.get("text", "")

                # Format timestamps
                start_formatted = ExportHandler._format_timestamp(start_time)
                end_formatted = ExportHandler._format_timestamp(end_time)

                vtt_content += f"{start_formatted} --> {end_formatted}\n"
                vtt_content += f"{speaker}: {text}\n\n"

        return vtt_content

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds to VTT timestamp format (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    @staticmethod
    def _format_as_markdown(data: dict[str, Any], include_metadata: bool) -> str:
        """Format data as Markdown.

        Logic:
        1. Create structured Markdown document
        2. Include main content sections
        3. Add metadata section if requested
        """
        lines = []

        # Title
        lines.append("# Meeting Transcript Results\n")

        # Summary if available
        if "summary" in data:
            lines.append("## Summary\n")
            lines.append(f"{data['summary']}\n")

        # Main content
        if "final_transcript" in data:
            lines.append("## Cleaned Transcript\n")
            lines.append(f"```\n{data['final_transcript']}\n```\n")
        elif "cleaned_transcript" in data:
            lines.append("## Cleaned Transcript\n")
            lines.append(f"```\n{data['cleaned_transcript']}\n```\n")

        # Action items
        if "action_items" in data:
            lines.append("## Action Items\n")
            for i, item in enumerate(data["action_items"], 1):
                if isinstance(item, dict):
                    desc = item.get("description", str(item))
                    owner = item.get("owner", "")
                    due_date = item.get("due_date", "")
                    lines.append(f"{i}. {desc}")
                    if owner:
                        lines.append(f"   - **Owner:** {owner}")
                    if due_date:
                        lines.append(f"   - **Due:** {due_date}")
                else:
                    lines.append(f"{i}. {item}")
                lines.append("")

        # Metadata
        if include_metadata and "processing_stats" in data:
            lines.append("## Processing Statistics\n")
            stats = data["processing_stats"]
            for key, value in stats.items():
                formatted_key = key.replace("_", " ").title()
                lines.append(f"- **{formatted_key}:** {value}")

        return "\n".join(lines)

    @staticmethod
    def _format_as_text(data: dict[str, Any], include_metadata: bool) -> str:
        """Format data as plain text.

        Logic:
        1. Create plain text document
        2. Use simple formatting without markup
        3. Include relevant sections
        """
        lines = []

        # Title
        lines.append("MEETING TRANSCRIPT RESULTS")
        lines.append("=" * 50)
        lines.append("")

        # Generated timestamp
        lines.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary
        if "summary" in data:
            lines.append("SUMMARY:")
            lines.append("-" * 20)
            lines.append(data["summary"])
            lines.append("")

        # Main content
        if "final_transcript" in data:
            lines.append("CLEANED TRANSCRIPT:")
            lines.append("-" * 30)
            lines.append(data["final_transcript"])
            lines.append("")
        elif "cleaned_transcript" in data:
            lines.append("CLEANED TRANSCRIPT:")
            lines.append("-" * 30)
            lines.append(data["cleaned_transcript"])
            lines.append("")

        # Action items
        if "action_items" in data:
            lines.append("ACTION ITEMS:")
            lines.append("-" * 20)
            for i, item in enumerate(data["action_items"], 1):
                if isinstance(item, dict):
                    desc = item.get("description", str(item))
                    owner = item.get("owner", "")
                    due_date = item.get("due_date", "")
                    lines.append(f"{i}. {desc}")
                    if owner:
                        lines.append(f"   Owner: {owner}")
                    if due_date:
                        lines.append(f"   Due: {due_date}")
                else:
                    lines.append(f"{i}. {item}")
                lines.append("")

        # Metadata
        if include_metadata and "processing_stats" in data:
            lines.append("PROCESSING STATISTICS:")
            lines.append("-" * 30)
            stats = data["processing_stats"]
            for key, value in stats.items():
                formatted_key = key.replace("_", " ").title()
                lines.append(f"{formatted_key}: {value}")

        return "\n".join(lines)


def render_quick_export_buttons(data: dict[str, Any], filename_base: str) -> None:
    """Render quick export buttons with essential formats.

    Logic:
    1. Create simple download buttons for TXT, MD, VTT
    2. Use default settings with metadata included
    3. Minimal, clean UI
    """
    if not data:
        return

    col1, col2, col3 = st.columns(3)

    formats = [("txt", "📄 TXT"), ("md", "📝 MD"), ("vtt", "📺 VTT")]

    for i, (fmt, label) in enumerate(formats):
        content, mime_type = ExportHandler._generate_export_content(data, fmt, True)

        filename = generate_download_filename(filename_base, "export", fmt)

        with [col1, col2, col3][i]:
            st.download_button(
                label=label,
                data=content,
                file_name=filename,
                mime=mime_type,
                use_container_width=True,
            )
