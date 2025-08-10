"""
Test cases for the DiffViewer utility module.

Tests the diff generation, formatting, and statistics functionality.
Note: Unified diff functionality has been removed as part of cleanup.
"""

import pytest

from utils.diff_viewer import DiffViewer


class TestDiffViewer:
    """Test cases for DiffViewer class."""

    @pytest.fixture
    def diff_viewer(self):
        """Create DiffViewer instance for testing."""
        return DiffViewer()

    def test_side_by_side_diff_equal_lengths(self, diff_viewer):
        """Test side-by-side diff with equal length texts."""
        original = "line 1\nline 2"
        cleaned = "line 1\nline 2 modified"

        result = diff_viewer.generate_side_by_side_diff(original, cleaned)

        assert len(result) == 2
        # First line unchanged
        assert result[0] == ("line 1", "line 1", False)
        # Second line changed
        assert result[1] == ("line 2", "line 2 modified", True)

    def test_side_by_side_diff_different_lengths(self, diff_viewer):
        """Test side-by-side diff with different length texts."""
        original = "line 1\nline 2"
        cleaned = "line 1\nline 2\nline 3"

        result = diff_viewer.generate_side_by_side_diff(original, cleaned)

        # Should handle the added line
        assert len(result) >= 2

        # Check for the added line (None, "line 3", True)
        added_entries = [
            (orig, clean, changed)
            for orig, clean, changed in result
            if orig is None and clean == "line 3" and changed
        ]
        assert len(added_entries) == 1

    def test_side_by_side_diff_with_empty_lines(self, diff_viewer):
        """Test side-by-side diff with empty lines."""
        original = "line 1\n\nline 3"
        cleaned = "line 1\nline 2\nline 3"

        result = diff_viewer.generate_side_by_side_diff(original, cleaned)

        assert len(result) >= 3
        # Should handle the insertion properly

    def test_html_formatting_side_by_side(self, diff_viewer):
        """Test HTML output for side-by-side diff is valid and styled."""
        original = "old line"
        cleaned = "new line"

        diff_lines = diff_viewer.generate_side_by_side_diff(original, cleaned)
        html = diff_viewer.format_side_by_side_html(diff_lines, show_line_numbers=True)

        # Check for required elements
        assert "<style>" in html
        assert "diff-container" in html
        assert "side-by-side" in html
        assert "side-by-side-left" in html
        assert "side-by-side-right" in html

    def test_change_statistics_basic(self, diff_viewer):
        """Test change summary calculations."""
        original = "line 1\nline 2\nline 3"
        cleaned = "line 1\nline 2 modified\nline 3\nline 4"

        stats = diff_viewer.calculate_change_stats(original, cleaned)

        assert "lines_added" in stats
        assert "lines_removed" in stats
        assert "lines_changed" in stats
        assert "similarity_ratio" in stats

        assert stats["lines_added"] > 0
        assert 0.0 <= stats["similarity_ratio"] <= 1.0

    def test_change_statistics_identical(self, diff_viewer):
        """Test change statistics for identical texts."""
        text = "same content\nline 2"

        stats = diff_viewer.calculate_change_stats(text, text)

        assert stats["lines_added"] == 0
        assert stats["lines_removed"] == 0
        assert stats["lines_changed"] == 0
        assert stats["similarity_ratio"] == 1.0

    def test_change_statistics_empty_inputs(self, diff_viewer):
        """Test change statistics for empty inputs."""
        stats = diff_viewer.calculate_change_stats("", "")

        assert stats["lines_added"] == 0
        assert stats["lines_removed"] == 0
        assert stats["lines_changed"] == 0
        assert stats["similarity_ratio"] == 1.0

    def test_change_statistics_completely_different(self, diff_viewer):
        """Test change statistics for completely different texts."""
        original = "completely different"
        cleaned = "totally new content"

        stats = diff_viewer.calculate_change_stats(original, cleaned)

        # Should have low similarity ratio
        assert stats["similarity_ratio"] < 1.0
        # Should detect changes - exact counts may vary based on character-level diff
        assert stats["lines_removed"] > 0
        assert stats["lines_added"] > 0

    def test_format_diff_as_html_side_by_side(self, diff_viewer):
        """Test format_diff_as_html with side-by-side view mode."""
        original = "old content"
        cleaned = "new content"

        diff_lines = diff_viewer.generate_side_by_side_diff(original, cleaned)
        html = diff_viewer.format_diff_as_html(diff_lines, True)

        assert "side-by-side" in html
        assert "<style>" in html
