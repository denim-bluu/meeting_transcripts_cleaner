"""Document-level diff viewer for full transcript comparison.

This module provides document-level diff generation and change analysis,
complementing the segment-level diff_viewer.py for comprehensive UX.
"""

import difflib
import html
import re
from typing import Any, Literal

import structlog

from models.schemas import (
    CleaningResult,
    DocumentSegment,
    ReviewDecision,
    ReviewDecisionEnum,
)
from utils.diff_viewer import DiffViewer

logger = structlog.get_logger(__name__)


# CSS Styles for inline diff (Google Docs style)
INLINE_DIFF_STYLES = """
<style>
    /* Inline diff container */
    .inline-diff-container {
        background: white;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
        line-height: 1.8;
        font-size: 14px;
        max-height: 70vh;
        overflow-y: auto;
        color: #333;
    }

    /* Inline change markers - Google Docs style */
    del {
        background-color: #ffdddd;
        color: #a33;
        text-decoration: line-through;
        text-decoration-color: #a33;
        text-decoration-thickness: 2px;
        padding: 2px 4px;
        border-radius: 3px;
        margin: 0 2px;
    }

    ins {
        background-color: #ddffdd;
        color: #080;
        text-decoration: none;
        font-weight: 500;
        padding: 2px 4px;
        border-radius: 3px;
        margin: 0 2px;
    }

    /* Paragraph spacing */
    .inline-diff-paragraph {
        margin-bottom: 1em;
        text-align: justify;
    }

    /* Segment markers */
    .inline-segment-marker {
        display: inline-block;
        background: #e3f2fd;
        color: #1976d2;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 12px;
        margin: 0 8px;
        vertical-align: super;
        font-weight: 600;
    }

    /* Speaker block styling for transcript structure */
    .speaker-block {
        margin-bottom: 1.2em;
        padding: 8px 12px;
        border-left: 3px solid #e0e0e0;
        background: #fafafa;
        border-radius: 4px;
    }

    /* Speaker separator for visual breaks between dialogue */
    .speaker-separator {
        border: none;
        height: 1px;
        background: linear-gradient(to right, transparent, #ccc, transparent);
        margin: 1em 0;
    }

    /* Change summary tooltip */
    .change-tooltip {
        position: relative;
        cursor: help;
        border-bottom: 1px dotted #666;
    }

    .change-tooltip:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        background: #333;
        color: white;
        padding: 5px 10px;
        border-radius: 4px;
        font-size: 12px;
        white-space: nowrap;
        z-index: 1000;
    }
</style>
"""


# CSS Styles for side-by-side view (current style)
DOCUMENT_DIFF_STYLES = """
<style>
    .document-diff-container {
        display: flex;
        gap: 20px;
        max-height: 70vh;
        overflow: hidden;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        background: #f8f9fa;
    }
    .diff-panel {
        flex: 1;
        background: white;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        overflow-y: auto;
        padding: 16px;
        font-family: 'Courier New', monospace;
        line-height: 1.6;
        font-size: 13px;
    }
    .diff-panel-header {
        font-weight: bold;
        padding: 8px 0;
        border-bottom: 2px solid #dee2e6;
        margin-bottom: 16px;
        background: white;
        position: sticky;
        top: -16px;
        z-index: 10;
        font-size: 14px;
        color: #495057;
    }
    .change-highlight {
        background: #fff5b4;
        border-left: 4px solid #ffc107;
        padding: 4px;
        margin: 2px 0;
        border-radius: 2px;
    }
    .segment-separator {
        border-top: 1px dashed #dee2e6;
        margin: 12px 0;
        padding-top: 12px;
    }
    .segment-header {
        font-size: 11px;
        color: #6c757d;
        background: #f8f9fa;
        padding: 4px 8px;
        border-radius: 3px;
        margin-bottom: 8px;
        display: inline-block;
    }
</style>
"""


class DocumentDiffViewer:
    """Generate document-level diff view with change highlighting and navigation."""

    def __init__(self):
        """Initialize the document diff viewer."""
        self.diff_viewer = DiffViewer()

    def tokenize_text(self, text: str) -> list[str]:
        """Tokenize text into words for word-level diff.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens (words and punctuation)
        """
        # Use regex to split on word boundaries while preserving punctuation
        tokens = re.findall(r"\w+|[^\w\s]|\s+", text)
        return tokens

    def generate_word_diff(self, original: str, cleaned: str) -> str:
        """Generate word-level diff with inline HTML markup.

        Args:
            original: Original text
            cleaned: Cleaned text

        Returns:
            HTML with <del> for removed and <ins> for added words
        """
        # Tokenize both texts
        original_tokens = self.tokenize_text(original)
        cleaned_tokens = self.tokenize_text(cleaned)

        # Use SequenceMatcher for word-level comparison
        matcher = difflib.SequenceMatcher(None, original_tokens, cleaned_tokens)

        result_parts = []

        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                # Words are the same - add as is
                for token in original_tokens[i1:i2]:
                    result_parts.append(html.escape(token))

            elif op == "delete":
                # Words removed - wrap in <del>
                deleted_text = "".join(original_tokens[i1:i2])
                if deleted_text.strip():  # Only wrap non-whitespace
                    result_parts.append(f"<del>{html.escape(deleted_text)}</del>")

            elif op == "insert":
                # Words added - wrap in <ins>
                inserted_text = "".join(cleaned_tokens[j1:j2])
                if inserted_text.strip():  # Only wrap non-whitespace
                    result_parts.append(f"<ins>{html.escape(inserted_text)}</ins>")

            elif op == "replace":
                # Words changed - show both deleted and inserted
                deleted_text = "".join(original_tokens[i1:i2])
                inserted_text = "".join(cleaned_tokens[j1:j2])

                if deleted_text.strip():
                    result_parts.append(f"<del>{html.escape(deleted_text)}</del>")
                if inserted_text.strip():
                    result_parts.append(f"<ins>{html.escape(inserted_text)}</ins>")

        return "".join(result_parts)

    def detect_speaker_structure(self, text: str) -> dict[str, Any]:
        """Detect speaker patterns in text and identify structure.

        Args:
            text: Text to analyze for speaker patterns

        Returns:
            Dict with: has_speakers (bool), speaker_pattern (str), speakers (list),
                      inferred_breaks (list of line numbers)
        """
        lines = text.split("\n")

        # Common speaker patterns in transcripts
        patterns = [
            r"^([A-Z][a-zA-Z\s]*[A-Z]\.?):",  # "John D.:", "Sarah L.:"
            r"^([A-Z][a-zA-Z]*):",  # "John:", "Sarah:"
            r"^(\w+\s+\w+):",  # "John Smith:"
            r"^(\w+):",  # Simple "Name:"
        ]

        speakers_found = set()
        speaker_lines = []
        matched_pattern = None

        for i, line in enumerate(lines):
            for pattern in patterns:
                match = re.match(pattern, line.strip())
                if match:
                    speaker_name = match.group(1)
                    speakers_found.add(speaker_name)
                    speaker_lines.append(i)
                    if not matched_pattern:
                        matched_pattern = pattern
                    break

        has_speakers = len(speakers_found) >= 2  # Need at least 2 different speakers

        # If we found speaker patterns, infer paragraph breaks
        inferred_breaks = []
        if has_speakers and len(speaker_lines) > 1:
            # Add breaks before each speaker change
            inferred_breaks = speaker_lines[1:]  # Skip first speaker

        return {
            "has_speakers": has_speakers,
            "speaker_pattern": matched_pattern,
            "speakers": list(speakers_found),
            "inferred_breaks": inferred_breaks,
            "speaker_lines": speaker_lines,
        }

    def _add_speaker_paragraph_breaks(self, text: str, structure: dict) -> str:
        """Add paragraph breaks at inferred speaker changes.

        Args:
            text: Original text without paragraph breaks
            structure: Result from detect_speaker_structure()

        Returns:
            Text with paragraph breaks added before speaker changes
        """
        if not structure["inferred_breaks"]:
            return text

        lines = text.split("\n")
        result_lines = []

        for i, line in enumerate(lines):
            # Add extra newline before speaker changes (except first)
            if i in structure["inferred_breaks"] and result_lines:
                result_lines.append("")  # Add empty line for paragraph break
            result_lines.append(line)

        return "\n".join(result_lines)

    def _apply_sentence_level_fallback(self, original: str, cleaned: str) -> str:
        """Apply sentence-level diff when no speaker structure is detected.

        Args:
            original: Original text
            cleaned: Cleaned text

        Returns:
            HTML with sentence-level diff highlighting
        """
        # Split into sentences using basic punctuation
        original_sentences = re.split(r"[.!?]+\s+", original)
        cleaned_sentences = re.split(r"[.!?]+\s+", cleaned)

        # Use sequence matcher on sentences
        matcher = difflib.SequenceMatcher(None, original_sentences, cleaned_sentences)
        result_parts = []

        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                # Sentences are the same
                for sentence in original_sentences[i1:i2]:
                    if sentence.strip():
                        result_parts.append(
                            f"<span>{html.escape(sentence.strip())}.</span> "
                        )
            elif op == "delete":
                # Sentences removed
                for sentence in original_sentences[i1:i2]:
                    if sentence.strip():
                        result_parts.append(
                            f"<del>{html.escape(sentence.strip())}.</del> "
                        )
            elif op == "insert":
                # Sentences added
                for sentence in cleaned_sentences[j1:j2]:
                    if sentence.strip():
                        result_parts.append(
                            f"<ins>{html.escape(sentence.strip())}.</ins> "
                        )
            elif op == "replace":
                # Sentences changed
                for sentence in original_sentences[i1:i2]:
                    if sentence.strip():
                        result_parts.append(
                            f"<del>{html.escape(sentence.strip())}.</del> "
                        )
                for sentence in cleaned_sentences[j1:j2]:
                    if sentence.strip():
                        result_parts.append(
                            f"<ins>{html.escape(sentence.strip())}.</ins> "
                        )

        return "".join(result_parts)

    def generate_paragraph_aware_diff(self, original: str, cleaned: str) -> str:
        """Process paragraphs separately to preserve speaker breaks.

        This is critical for transcript readability - we need to maintain
        the dialogue structure and speaker separation. Now handles both
        structured (with paragraph breaks) and unstructured original text.

        Args:
            original: Original text
            cleaned: Cleaned text

        Returns:
            HTML with <div class="speaker-block"> wrappers and preserved structure
        """
        result_parts = []

        # Detect speaker structure in original text
        original_structure = self.detect_speaker_structure(original)
        self.detect_speaker_structure(cleaned)

        # Check if original text lacks paragraph structure but has speakers
        original_has_paragraphs = "\n\n" in original

        if not original_has_paragraphs and original_structure["has_speakers"]:
            # Original text has speakers but no paragraph breaks - need to pre-process
            original = self._add_speaker_paragraph_breaks(original, original_structure)

            # Add visual indicator that structure was inferred
            result_parts.append(
                '<div class="structure-inferred-notice" style="background: #e3f2fd; '
                'border-left: 4px solid #2196f3; padding: 8px 12px; margin-bottom: 1em; '
                'font-size: 12px; color: #1976d2;">'
                '💡 <strong>Structure Inferred:</strong> Added paragraph breaks at speaker changes '
                f'({len(original_structure["speakers"])} speakers detected)'
                '</div>'
            )
        elif not original_has_paragraphs and not original_structure["has_speakers"]:
            # No paragraph structure and no speakers - use sentence-level fallback
            sentence_diff = self._apply_sentence_level_fallback(original, cleaned)
            result_parts.append(
                '<div class="sentence-level-notice" style="background: #fff3e0; '
                "border-left: 4px solid #ff9800; padding: 8px 12px; margin-bottom: 1em; "
                'font-size: 12px; color: #f57c00;">'
                "📝 <strong>Sentence-Level Diff:</strong> No speaker structure detected, using sentence-based comparison"
                "</div>"
            )
            result_parts.append('<div class="sentence-diff-container">')
            result_parts.append(sentence_diff)
            result_parts.append("</div>")
            return "".join(result_parts)

        # Split by double newlines to maintain speaker/paragraph separation
        original_paragraphs = original.split("\n\n")
        cleaned_paragraphs = cleaned.split("\n\n")

        # Handle case where paragraph count doesn't match exactly
        max_paragraphs = max(len(original_paragraphs), len(cleaned_paragraphs))

        for i in range(max_paragraphs):
            # Get paragraphs, using empty string if one side has fewer
            orig_para = original_paragraphs[i] if i < len(original_paragraphs) else ""
            clean_para = cleaned_paragraphs[i] if i < len(cleaned_paragraphs) else ""

            # Skip empty paragraphs on both sides
            if not orig_para.strip() and not clean_para.strip():
                continue

            # Start speaker block
            result_parts.append('<div class="speaker-block">')

            if orig_para == clean_para:
                # No changes in this paragraph - just add the text
                result_parts.append(html.escape(orig_para))
            else:
                # Generate word-level diff for this paragraph only
                para_diff = self.generate_word_diff(orig_para, clean_para)
                result_parts.append(para_diff)

            # End speaker block
            result_parts.append("</div>")

            # Add visual separator between speakers (except for last paragraph)
            if i < max_paragraphs - 1:
                result_parts.append('<hr class="speaker-separator">')

        return "".join(result_parts)

    def generate_document_diff(
        self,
        segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
        review_decisions: dict[str, ReviewDecision] | None = None,
        view_mode: Literal["inline", "side_by_side"] = "side_by_side",
    ) -> str:
        """Generate full document diff HTML in the specified view mode.

        Args:
            segments: List of document segments
            cleaning_results: Cleaning results keyed by segment ID
            review_decisions: Review decisions keyed by segment ID (optional)
            show_line_numbers: Whether to include line numbers
            view_mode: Type of diff view - "inline" or "side_by_side"

        Returns:
            HTML with diff visualization in the requested format
        """
        if not segments:
            return (
                '<div style="padding: 20px; color: #666;">No segments to display</div>'
            )

        # Sort segments by sequence number
        sorted_segments = sorted(segments, key=lambda s: s.sequence_number)

        # Generate full document content
        original_content = self._build_original_document(sorted_segments)
        final_content = self._build_final_document(
            sorted_segments, cleaning_results, review_decisions
        )

        # Generate diff based on view mode
        if view_mode == "inline":
            return self._generate_inline_diff(
                sorted_segments, cleaning_results, review_decisions
            )
        else:  # side_by_side
            return self._generate_side_by_side_diff(
                original_content,
                final_content,
                sorted_segments,
                cleaning_results,
            )

    def _generate_inline_diff(
        self,
        segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
        review_decisions: dict[str, ReviewDecision] | None = None,
    ) -> str:
        """Generate inline diff view with Google Docs style track changes.

        Returns HTML with <del> and <ins> tags showing changes inline.
        """
        html_parts = [INLINE_DIFF_STYLES]
        html_parts.append('<div class="inline-diff-container">')

        for i, segment in enumerate(segments):
            cleaning_result = cleaning_results.get(segment.id)
            review_decision = (
                review_decisions.get(segment.id) if review_decisions else None
            )

            # Get the final text based on review decision
            if (
                review_decision
                and review_decision.decision == ReviewDecisionEnum.REJECT
            ):
                # If rejected, no diff to show
                html_parts.append('<div class="inline-diff-paragraph">')
                html_parts.append(html.escape(segment.content))
                html_parts.append("</div>")
            elif cleaning_result:
                # Generate paragraph-aware diff to preserve speaker structure
                diff_html = self.generate_paragraph_aware_diff(
                    segment.content, cleaning_result.cleaned_text
                )

                # Add segment marker if there are changes
                if cleaning_result.changes_made:
                    html_parts.append(
                        f'<span class="inline-segment-marker">S{segment.sequence_number}</span>'
                    )

                # The paragraph-aware diff already includes proper div structure
                html_parts.append(diff_html)
            else:
                # No cleaning result - show original
                html_parts.append('<div class="inline-diff-paragraph">')
                html_parts.append(html.escape(segment.content))
                html_parts.append("</div>")

            # Add paragraph break between segments
            if i < len(segments) - 1:
                html_parts.append("<br>")

        html_parts.append("</div>")
        return "".join(html_parts)

    def generate_side_by_side_data(
        self,
        segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
        review_decisions: dict[str, ReviewDecision] | None = None,
    ) -> dict:
        """Generate side-by-side data structure for Streamlit native rendering.

        Returns structured data instead of HTML for better Streamlit integration.

        Args:
            segments: List of document segments
            cleaning_results: Cleaning results keyed by segment ID
            review_decisions: Review decisions keyed by segment ID (optional)

        Returns:
            Dict with segments data for original and cleaned versions
        """
        if not segments:
            return {"segments": []}

        # Sort segments by sequence number
        sorted_segments = sorted(segments, key=lambda s: s.sequence_number)

        segments_data = []

        for segment in sorted_segments:
            cleaning_result = cleaning_results.get(segment.id)
            review_decision = (
                review_decisions.get(segment.id) if review_decisions else None
            )

            # Determine final text based on review decision
            if review_decision:
                if review_decision.decision == ReviewDecisionEnum.ACCEPT:
                    cleaned_text = (
                        cleaning_result.cleaned_text
                        if cleaning_result
                        else segment.content
                    )
                elif review_decision.decision == ReviewDecisionEnum.MODIFY:
                    cleaned_text = (
                        review_decision.suggested_corrections or segment.content
                    )
                else:  # REJECT
                    cleaned_text = segment.content
            elif cleaning_result:
                cleaned_text = cleaning_result.cleaned_text
            else:
                cleaned_text = segment.content

            # Check if this segment has changes
            has_changes = (
                cleaning_result
                and cleaning_result.changes_made
                and len(cleaning_result.changes_made) > 0
            )

            segment_data = {
                "id": segment.id,
                "sequence_number": segment.sequence_number,
                "original": segment.content,
                "cleaned": cleaned_text,
                "has_changes": has_changes,
                "changes": cleaning_result.changes_made if cleaning_result else [],
                "confidence": review_decision.confidence if review_decision else None,
            }

            segments_data.append(segment_data)

        return {"segments": segments_data}

    def _generate_side_by_side_diff(
        self,
        original_content: str,
        final_content: str,
        sorted_segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
    ) -> str:
        """Generate side-by-side diff view (current implementation).

        Returns HTML with original and cleaned versions side-by-side.
        """
        html_content = f"""
        {DOCUMENT_DIFF_STYLES}
        <div class="document-diff-container">
            <div class="diff-panel">
                <div class="diff-panel-header">📄 Original Document</div>
                {self._format_document_content(original_content, sorted_segments, "original")}
            </div>
            <div class="diff-panel">
                <div class="diff-panel-header">✨ Cleaned Document</div>
                {self._format_document_content(final_content, sorted_segments, "cleaned", cleaning_results)}
            </div>
        </div>
        """

        return html_content

    def _build_original_document(self, segments: list[DocumentSegment]) -> str:
        """Build the original full document text."""
        return "\n\n".join(segment.content for segment in segments)

    def _build_final_document(
        self,
        segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
        review_decisions: dict[str, ReviewDecision] | None = None,
    ) -> str:
        """Build the final cleaned document text."""
        final_parts = []

        for segment in segments:
            cleaning_result = cleaning_results.get(segment.id)
            review_decision = (
                review_decisions.get(segment.id) if review_decisions else None
            )

            # Determine final text based on review decision
            if review_decision:
                if review_decision.decision == ReviewDecisionEnum.ACCEPT:
                    final_text = (
                        cleaning_result.cleaned_text
                        if cleaning_result
                        else segment.content
                    )
                elif review_decision.decision == ReviewDecisionEnum.MODIFY:
                    final_text = (
                        review_decision.suggested_corrections or segment.content
                    )
                else:  # REJECT
                    final_text = segment.content
            elif cleaning_result:
                final_text = cleaning_result.cleaned_text
            else:
                final_text = segment.content

            final_parts.append(final_text)

        return "\n\n".join(final_parts)

    def _format_document_content(
        self,
        content: str,
        segments: list[DocumentSegment],
        panel_type: str,
        cleaning_results: dict[str, CleaningResult] | None = None,
    ) -> str:
        """Format document content with highlighting and segment markers."""
        lines = content.split("\n")
        formatted_lines = []
        line_num = 1

        # Track which segment we're in
        current_segment_idx = 0
        lines_in_current_segment = 0
        segment_content_lines = (
            segments[current_segment_idx].content.split("\n") if segments else []
        )

        for line in lines:
            # Check if we need to add segment separator
            if current_segment_idx < len(
                segments
            ) - 1 and lines_in_current_segment >= len(segment_content_lines):
                # Move to next segment
                current_segment_idx += 1
                lines_in_current_segment = 0
                if current_segment_idx < len(segments):
                    segment_content_lines = segments[current_segment_idx].content.split(
                        "\n"
                    )

                # Add segment separator
                formatted_lines.append('<div class="segment-separator"></div>')
                segment = (
                    segments[current_segment_idx]
                    if current_segment_idx < len(segments)
                    else None
                )
                if segment:
                    has_changes = bool(
                        cleaning_results and cleaning_results[segment.id].changes_made
                    )
                    change_indicator = "✨ Modified" if has_changes else "📝 Original"
                    formatted_lines.append(
                        f'<div class="segment-header">Segment {segment.sequence_number} - {change_indicator}</div>'
                    )

            # Format the line
            escaped_line = html.escape(line)
            line_num_html = ""

            line_num_html = f'<span style="color: #6a737d; min-width: 40px; display: inline-block; text-align: right; padding-right: 10px; user-select: none;">{line_num:4d}</span>'
            line_num += 1

            # Check if this line has changes (simple heuristic)
            has_highlight = (
                panel_type == "cleaned"
                and current_segment_idx < len(segments)
                and cleaning_results
                and cleaning_results[segments[current_segment_idx].id].changes_made
            )

            line_class = "change-highlight" if has_highlight else ""
            anchor_id = (
                f"change-{current_segment_idx}-{lines_in_current_segment}"
                if has_highlight
                else ""
            )

            formatted_lines.append(
                f'<div class="{line_class} change-anchor" id="{anchor_id}">'
                f"{line_num_html}{escaped_line}</div>"
            )

            lines_in_current_segment += 1

        return "".join(formatted_lines)

    def get_change_summary(
        self,
        segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
        review_decisions: dict[str, ReviewDecision] | None = None,
    ) -> dict[str, Any]:
        """Calculate document-level change statistics.

        Args:
            segments: List of document segments
            cleaning_results: Cleaning results keyed by segment ID
            review_decisions: Review decisions keyed by segment ID (optional)

        Returns:
            Dict with: total_changes, change_types, confidence_stats,
                      change_density, segments_modified, avg_confidence
        """
        if not segments:
            return {
                "total_changes": 0,
                "segments_modified": 0,
                "change_types": {},
                "confidence_stats": {"high": 0, "medium": 0, "low": 0},
                "change_density": 0.0,
                "avg_confidence": 0.0,
            }

        summary = {
            "total_changes": 0,
            "segments_modified": 0,
            "change_types": {},
            "confidence_stats": {"high": 0, "medium": 0, "low": 0},
            "change_density": 0.0,
            "avg_confidence": 0.0,
        }

        confidence_scores = []

        # Analyze each segment with results
        for segment in segments:
            cleaning_result = cleaning_results.get(segment.id)
            review_decision = (
                review_decisions.get(segment.id) if review_decisions else None
            )

            if cleaning_result and cleaning_result.changes_made:
                summary["segments_modified"] += 1
                summary["total_changes"] += len(cleaning_result.changes_made)

                # Categorize change types
                for change in cleaning_result.changes_made:
                    change_type = self._categorize_change(change)
                    summary["change_types"][change_type] = (
                        summary["change_types"].get(change_type, 0) + 1
                    )

            # Track confidence scores
            if review_decision:
                confidence_scores.append(review_decision.confidence)

                # Categorize confidence levels
                if review_decision.confidence >= 0.8:
                    summary["confidence_stats"]["high"] += 1
                elif review_decision.confidence >= 0.6:
                    summary["confidence_stats"]["medium"] += 1
                else:
                    summary["confidence_stats"]["low"] += 1

        # Calculate aggregate metrics
        if segments:
            summary["change_density"] = summary["segments_modified"] / len(segments)

        if confidence_scores:
            summary["avg_confidence"] = sum(confidence_scores) / len(confidence_scores)

        return summary

    def get_change_navigation(
        self,
        segments: list[DocumentSegment],
        cleaning_results: dict[str, CleaningResult],
    ) -> list[dict[str, str]]:
        """Generate navigation list for jumping between changes.

        Args:
            segments: List of document segments
            cleaning_results: Cleaning results keyed by segment ID

        Returns:
            List of {id, title, type, confidence, segment_num} for each significant change
        """
        navigation_items = []

        for segment in sorted(segments, key=lambda s: s.sequence_number):
            cleaning_result = cleaning_results.get(segment.id)

            if cleaning_result and cleaning_result.changes_made:
                # Create a meaningful title for the change
                change_types = [
                    self._categorize_change(change)
                    for change in cleaning_result.changes_made
                ]
                primary_type = (
                    max(set(change_types), key=change_types.count)
                    if change_types
                    else "other"
                )

                # Truncate segment content for preview
                content_preview = (
                    segment.content[:50] + "..."
                    if len(segment.content) > 50
                    else segment.content
                )

                navigation_items.append(
                    {
                        "id": f"change-{segment.sequence_number}",
                        "title": f"Segment {segment.sequence_number}: {content_preview}",
                        "type": primary_type.replace("_", " ").title(),
                        "change_count": str(len(cleaning_result.changes_made)),
                        "segment_num": str(segment.sequence_number),
                    }
                )

        return navigation_items

    def _categorize_change(self, change_description: str) -> str:
        """Categorize a change description into type."""
        change_lower = change_description.lower()

        if any(
            word in change_lower
            for word in ["filler", "um", "uh", "ah", "like", "you know"]
        ):
            return "filler_words"
        elif any(
            word in change_lower
            for word in ["grammar", "tense", "subject", "verb", "agreement"]
        ):
            return "grammar"
        elif any(
            word in change_lower
            for word in ["punctuation", "comma", "period", "capitalization"]
        ):
            return "punctuation"
        elif any(
            word in change_lower
            for word in ["clarity", "restructured", "readability", "flow"]
        ):
            return "clarity"
        elif any(word in change_lower for word in ["spelling", "typo", "misspelled"]):
            return "spelling"
        else:
            return "other"
