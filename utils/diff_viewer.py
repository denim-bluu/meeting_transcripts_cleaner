"""Diff viewer utility for transcript comparison."""

import difflib
import html


def get_diff_styles(show_line_numbers: bool = True) -> str:
    """Return CSS with conditional line number styles."""
    base_styles = """
    .diff-container {
        font-family: 'Courier New', monospace;
        background: #f6f8fa;
        border: 1px solid #d1d5da;
        border-radius: 6px;
        padding: 12px;
        overflow-x: auto;
    }
    .diff-line {
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.5;
    }
    .diff-removed {
        background-color: #ffeef0;
        color: #cb2431;
        display: block;
    }
    .diff-added {
        background-color: #e6ffed;
        color: #22863a;
        display: block;
    }
    .diff-context {
        color: #24292e;
        display: block;
    }
    .diff-marker {
        user-select: none;
        padding: 0 4px;
    }
    .side-by-side {
        display: table;
        width: 100%;
    }
    .side-by-side-row {
        display: table-row;
    }
    .side-by-side-left, .side-by-side-right {
        display: table-cell;
        width: 50%;
        vertical-align: top;
        padding: 2px 8px;
        border: 1px solid #e1e4e8;
    }
    .side-by-side-left {
        border-right: none;
    }
    .side-by-side-changed {
        background-color: #fff5b4;
    }"""

    if show_line_numbers:
        base_styles += """
    .diff-line-num {
        color: #6a737d;
        min-width: 40px;
        display: inline-block;
        text-align: right;
        padding-right: 10px;
        user-select: none;
    }"""

    return f"<style>{base_styles}</style>"


class DiffViewer:
    """Generate and format diffs for transcript comparison."""

    def generate_side_by_side_diff(
        self, original: str, cleaned: str
    ) -> list[tuple[str | None, str | None, bool]]:
        """Generate side-by-side comparison.

        Args:
            original: Original text
            cleaned: Cleaned text

        Returns:
            List of (original_line, cleaned_line, is_changed) tuples
        """
        if not original and not cleaned:
            return []

        original_lines = original.splitlines(keepends=False)
        cleaned_lines = cleaned.splitlines(keepends=False)

        # Handle large diffs gracefully
        if len(original_lines) + len(cleaned_lines) > 1000:
            # Truncate to first 250 lines each for manageable display
            original_lines = original_lines[:250]
            cleaned_lines = cleaned_lines[:250]
            truncate_message = True
        else:
            truncate_message = False

        # Use SequenceMatcher to find matching lines
        matcher = difflib.SequenceMatcher(None, original_lines, cleaned_lines)
        result = []

        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                # Lines are the same
                for k in range(i2 - i1):
                    result.append(
                        (original_lines[i1 + k], cleaned_lines[j1 + k], False)
                    )
            elif op == "delete":
                # Lines removed
                for k in range(i2 - i1):
                    result.append((original_lines[i1 + k], None, True))
            elif op == "insert":
                # Lines added
                for k in range(j2 - j1):
                    result.append((None, cleaned_lines[j1 + k], True))
            elif op == "replace":
                # Lines changed
                max_lines = max(i2 - i1, j2 - j1)
                for k in range(max_lines):
                    orig_line = original_lines[i1 + k] if k < (i2 - i1) else None
                    clean_line = cleaned_lines[j1 + k] if k < (j2 - j1) else None
                    result.append((orig_line, clean_line, True))

        # Add truncation message if diff was truncated
        if truncate_message:
            result.append(("", "", False))  # Empty line
            result.append(
                (
                    "[... Large diff truncated. Showing first 250 lines only ...]",
                    "[... Large diff truncated. Showing first 250 lines only ...]",
                    True,
                )
            )

        return result

    def format_diff_as_html(
        self,
        diff_lines: list[tuple[str | None, str | None, bool]],
        show_line_numbers: bool = True,
    ) -> str:
        """Convert diff to styled HTML for Streamlit.

        Args:
            diff_lines: Diff data as (original_line, cleaned_line, is_changed) tuples
            show_line_numbers: Whether to include line numbers

        Returns:
            HTML string with embedded CSS for diff visualization
        """
        # Only support side_by_side view mode now
        return self.format_side_by_side_html(diff_lines, show_line_numbers)

    def format_side_by_side_html(
        self,
        diff_lines: list[tuple[str | None, str | None, bool]],
        show_line_numbers: bool,
    ) -> str:
        """Format side-by-side diff as HTML."""
        html_rows = []
        left_line_num = 1
        right_line_num = 1

        for orig_line, clean_line, is_changed in diff_lines:
            left_content = ""
            right_content = ""
            row_class = "side-by-side-changed" if is_changed else ""

            # Left side (original)
            if orig_line is not None:
                escaped_orig = html.escape(orig_line)
                left_num_html = ""
                if show_line_numbers:
                    left_num_html = (
                        f'<span class="diff-line-num">{left_line_num:4d}</span>'
                    )
                    left_line_num += 1
                left_content = f"{left_num_html}{escaped_orig}"

            # Right side (cleaned)
            if clean_line is not None:
                escaped_clean = html.escape(clean_line)
                right_num_html = ""
                if show_line_numbers:
                    right_num_html = (
                        f'<span class="diff-line-num">{right_line_num:4d}</span>'
                    )
                    right_line_num += 1
                right_content = f"{right_num_html}{escaped_clean}"

            html_rows.append(
                f'<div class="side-by-side-row">'
                f'<div class="side-by-side-left {row_class}">{left_content}</div>'
                f'<div class="side-by-side-right {row_class}">{right_content}</div>'
                f"</div>"
            )

        content = "".join(html_rows)
        styles = get_diff_styles(show_line_numbers)
        return f'{styles}<div class="diff-container"><div class="side-by-side">{content}</div></div>'

    def calculate_change_stats(
        self, original: str, cleaned: str
    ) -> dict[str, int | float]:
        """Calculate change statistics for text comparison.

        Args:
            original: Original text
            cleaned: Cleaned text

        Returns:
            Dict with: lines_added, lines_removed, lines_changed, similarity_ratio
        """
        if not original and not cleaned:
            return {
                "lines_added": 0,
                "lines_removed": 0,
                "lines_changed": 0,
                "similarity_ratio": 1.0,
            }

        # Calculate similarity ratio
        matcher = difflib.SequenceMatcher(None, original, cleaned)
        similarity = matcher.ratio()

        # Count changes using sequence matcher directly (no unified diff needed)
        lines_added = 0
        lines_removed = 0

        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "delete":
                lines_removed += i2 - i1
            elif op == "insert":
                lines_added += j2 - j1
            elif op == "replace":
                lines_removed += i2 - i1
                lines_added += j2 - j1

        lines_changed = min(lines_added, lines_removed)

        return {
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "lines_changed": lines_changed,
            "similarity_ratio": similarity,
        }
