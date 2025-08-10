"""
Test cases for the DocumentDiffViewer utility module.

Tests document-level diff generation, change summary calculation, and navigation features.
"""

import pytest

from models.schemas import (
    CleaningResult,
    DocumentSegment,
    ReviewDecision,
    ReviewDecisionEnum,
)
from utils.document_diff_viewer import DocumentDiffViewer


class TestDocumentDiffViewer:
    """Test cases for DocumentDiffViewer class."""

    @pytest.fixture
    def document_diff_viewer(self):
        """Create DocumentDiffViewer instance for testing."""
        return DocumentDiffViewer()

    @pytest.fixture
    def sample_segments(self):
        """Create sample document segments for testing."""
        return [
            DocumentSegment(
                id="seg1",
                content="This is the first segment with, um, some filler words.",
                token_count=12,
                start_index=0,
                end_index=56,
                sequence_number=1
            ),
            DocumentSegment(
                id="seg2",
                content="The second segment has grammar error and needs fixing.",
                token_count=10,
                start_index=57,
                end_index=114,
                sequence_number=2
            ),
            DocumentSegment(
                id="seg3",
                content="This segment is already perfect and needs no changes.",
                token_count=10,
                start_index=115,
                end_index=168,
                sequence_number=3
            )
        ]

    @pytest.fixture
    def sample_cleaning_results(self):
        """Create sample cleaning results for testing."""
        return {
            "seg1": CleaningResult(
                segment_id="seg1",
                cleaned_text="This is the first segment with some filler words.",
                changes_made=["Removed filler word 'um'", "Added missing comma"],
                processing_time_ms=150.0
            ),
            "seg2": CleaningResult(
                segment_id="seg2",
                cleaned_text="The second segment has a grammar error and needs fixing.",
                changes_made=["Fixed article 'a' before 'grammar'", "Improved sentence structure"],
                processing_time_ms=200.0
            ),
            "seg3": CleaningResult(
                segment_id="seg3",
                cleaned_text="This segment is already perfect and needs no changes.",
                changes_made=[],
                processing_time_ms=50.0
            )
        }

    @pytest.fixture
    def sample_review_decisions(self):
        """Create sample review decisions for testing."""
        return {
            "seg1": ReviewDecision(
                segment_id="seg1",
                decision=ReviewDecisionEnum.ACCEPT,
                confidence=0.95,
                preservation_score=0.98,
                issues_found=[],
                reasoning="Changes improve clarity without altering meaning"
            ),
            "seg2": ReviewDecision(
                segment_id="seg2",
                decision=ReviewDecisionEnum.ACCEPT,
                confidence=0.75,
                preservation_score=0.92,
                issues_found=["Minor grammar improvement"],
                reasoning="Grammar correction necessary for clarity"
            ),
            "seg3": ReviewDecision(
                segment_id="seg3",
                decision=ReviewDecisionEnum.ACCEPT,
                confidence=1.0,
                preservation_score=1.0,
                issues_found=[],
                reasoning="No changes needed"
            )
        }

    def test_document_diff_generation_basic(self, document_diff_viewer, sample_segments, sample_cleaning_results):
        """Test basic document diff HTML generation."""
        html_result = document_diff_viewer.generate_document_diff(
            sample_segments,
            sample_cleaning_results,
            view_mode="side_by_side"
        )

        # Should return HTML content
        assert isinstance(html_result, str)
        assert len(html_result) > 0

        # Should contain CSS styles
        assert "document-diff-container" in html_result
        assert "diff-panel" in html_result

        # Should contain both original and cleaned content
        assert "Original Document" in html_result
        assert "Cleaned Document" in html_result

        # Should contain content from segments
        assert "first segment" in html_result
        assert "second segment" in html_result

    def test_document_diff_generation_with_review_decisions(self, document_diff_viewer, sample_segments, sample_cleaning_results, sample_review_decisions):
        """Test document diff generation with review decisions."""
        html_result = document_diff_viewer.generate_document_diff(
            sample_segments,
            sample_cleaning_results,
            sample_review_decisions,
            view_mode="inline"
        )

        # Should include review decision logic in final content
        assert isinstance(html_result, str)
        assert len(html_result) > 0

        # Should not include line numbers when disabled
        # Note: This is a simplified test - in real implementation we'd check for absence of line number spans

    def test_document_diff_generation_empty_segments(self, document_diff_viewer):
        """Test document diff with empty segments list."""
        html_result = document_diff_viewer.generate_document_diff([], {})

        assert isinstance(html_result, str)
        assert "No segments to display" in html_result

    def test_change_summary_calculation(self, document_diff_viewer, sample_segments, sample_cleaning_results, sample_review_decisions):
        """Test document-level change summary statistics."""
        summary = document_diff_viewer.get_change_summary(
            sample_segments,
            sample_cleaning_results,
            sample_review_decisions
        )

        # Check summary structure
        expected_keys = ['total_changes', 'segments_modified', 'change_types', 'confidence_stats', 'change_density', 'avg_confidence']
        for key in expected_keys:
            assert key in summary

        # Check specific values
        assert summary['total_changes'] == 4  # 2 changes in seg1 + 2 changes in seg2
        assert summary['segments_modified'] == 2  # seg1 and seg2 have changes
        assert summary['change_density'] == 2/3  # 2 out of 3 segments modified

        # Check confidence statistics
        assert summary['confidence_stats']['high'] == 2  # seg1 (0.95) and seg3 (1.0)
        assert summary['confidence_stats']['medium'] == 1  # seg2 (0.75)
        assert summary['confidence_stats']['low'] == 0

        # Check average confidence
        expected_avg = (0.95 + 0.75 + 1.0) / 3
        assert abs(summary['avg_confidence'] - expected_avg) < 0.01

    def test_change_summary_empty_segments(self, document_diff_viewer):
        """Test change summary with empty segments."""
        summary = document_diff_viewer.get_change_summary([], {})

        assert summary['total_changes'] == 0
        assert summary['segments_modified'] == 0
        assert summary['change_density'] == 0.0
        assert summary['avg_confidence'] == 0.0

    def test_change_navigation_generation(self, document_diff_viewer, sample_segments, sample_cleaning_results):
        """Test change navigation list generation."""
        navigation_items = document_diff_viewer.get_change_navigation(
            sample_segments,
            sample_cleaning_results
        )

        # Should return navigation items for segments with changes
        assert len(navigation_items) == 2  # Only seg1 and seg2 have changes

        # Check structure of navigation items
        for item in navigation_items:
            required_keys = ['id', 'title', 'type', 'change_count', 'segment_num']
            for key in required_keys:
                assert key in item

        # Check specific values
        first_item = navigation_items[0]
        assert first_item['segment_num'] == '1'
        assert first_item['change_count'] == '2'
        assert 'first segment' in first_item['title']

        second_item = navigation_items[1]
        assert second_item['segment_num'] == '2'
        assert second_item['change_count'] == '2'

    def test_change_navigation_empty_changes(self, document_diff_viewer, sample_segments):
        """Test change navigation with no changes."""
        empty_results = {
            seg.id: CleaningResult(
                segment_id=seg.id,
                cleaned_text=seg.content,
                changes_made=[],
                processing_time_ms=50.0
            ) for seg in sample_segments
        }

        navigation_items = document_diff_viewer.get_change_navigation(
            sample_segments,
            empty_results
        )

        assert len(navigation_items) == 0

    def test_change_categorization(self, document_diff_viewer):
        """Test change type categorization logic."""
        test_cases = [
            ("Removed filler word 'um'", "filler_words"),
            ("Fixed grammar error", "grammar"),
            ("Added comma for clarity", "punctuation"),
            ("Improved sentence structure for clarity", "clarity"),
            ("Fixed spelling mistake", "spelling"),
            ("Made unspecified change", "other")
        ]

        for change_desc, expected_type in test_cases:
            result = document_diff_viewer._categorize_change(change_desc)
            assert result == expected_type, f"Expected {expected_type} for '{change_desc}', got {result}"

    def test_build_document_content(self, document_diff_viewer, sample_segments, sample_cleaning_results, sample_review_decisions):
        """Test document content building logic."""
        # Test original document building
        original_content = document_diff_viewer._build_original_document(sample_segments)

        assert isinstance(original_content, str)
        assert len(original_content) > 0
        assert "first segment" in original_content
        assert "second segment" in original_content
        assert "already perfect" in original_content

        # Test final document building with review decisions
        final_content = document_diff_viewer._build_final_document(
            sample_segments,
            sample_cleaning_results,
            sample_review_decisions
        )

        assert isinstance(final_content, str)
        assert len(final_content) > 0

        # Should contain cleaned content since all decisions are ACCEPT
        assert "um" not in final_content  # Filler word should be removed
        assert "a grammar error" in final_content  # Grammar should be fixed

    def test_build_final_document_with_rejections(self, document_diff_viewer, sample_segments, sample_cleaning_results):
        """Test final document building with mixed review decisions."""
        mixed_review_decisions = {
            "seg1": ReviewDecision(
                segment_id="seg1",
                decision=ReviewDecisionEnum.REJECT,  # Reject cleaning
                confidence=0.3,
                preservation_score=0.7,
                issues_found=["Changed meaning"],
                reasoning="Cleaning altered original intent"
            ),
            "seg2": ReviewDecision(
                segment_id="seg2",
                decision=ReviewDecisionEnum.MODIFY,  # Modify with suggestion
                confidence=0.6,
                preservation_score=0.85,
                issues_found=["Needs different approach"],
                suggested_corrections="The second segment has grammatical errors and needs fixing.",
                reasoning="Different correction needed"
            ),
            "seg3": ReviewDecision(
                segment_id="seg3",
                decision=ReviewDecisionEnum.ACCEPT,
                confidence=1.0,
                preservation_score=1.0,
                issues_found=[],
                reasoning="No changes needed"
            )
        }

        final_content = document_diff_viewer._build_final_document(
            sample_segments,
            sample_cleaning_results,
            mixed_review_decisions
        )

        # seg1 should be original (REJECT)
        assert "with, um, some" in final_content

        # seg2 should use suggested correction (MODIFY)
        assert "grammatical errors" in final_content

        # seg3 should use cleaned version (ACCEPT)
        assert "already perfect" in final_content

    def test_word_level_diff_generation(self, document_diff_viewer):
        """Test word-level diff algorithm for inline changes."""
        original = "This is the original text with, um, some filler words."
        cleaned = "This is the cleaned text with some filler words removed."

        diff_html = document_diff_viewer.generate_word_diff(original, cleaned)

        # Should contain del and ins tags
        assert "<del>" in diff_html
        assert "</del>" in diff_html
        assert "<ins>" in diff_html
        assert "</ins>" in diff_html

        # Specific changes should be marked
        assert "<del>original</del>" in diff_html
        assert "<ins>cleaned</ins>" in diff_html
        assert "<del>, um,</del>" in diff_html
        assert "<ins> removed</ins>" in diff_html  # Note the space before 'removed'

    def test_tokenize_text(self, document_diff_viewer):
        """Test text tokenization for word-level diff."""
        text = "Hello, world! This is a test."
        tokens = document_diff_viewer.tokenize_text(text)

        # Should preserve words, punctuation, and spaces
        assert "Hello" in tokens
        assert "," in tokens
        assert " " in tokens
        assert "world" in tokens
        assert "!" in tokens

    def test_inline_diff_view_generation(self, document_diff_viewer, sample_segments, sample_cleaning_results):
        """Test inline diff view generation (Google Docs style)."""
        html_result = document_diff_viewer._generate_inline_diff(
            sample_segments,
            sample_cleaning_results
        )

        # Should contain inline diff styles
        assert "inline-diff-container" in html_result
        assert "inline-diff-paragraph" in html_result

        # Should contain del and ins tags for changes
        assert "<del>" in html_result or "<ins>" in html_result

        # Should contain segment markers for segments with changes
        assert "inline-segment-marker" in html_result

    def test_multi_view_document_diff(self, document_diff_viewer, sample_segments, sample_cleaning_results):
        """Test document diff generation with different view modes."""
        # Test inline view
        inline_html = document_diff_viewer.generate_document_diff(
            sample_segments,
            sample_cleaning_results,
            view_mode="inline"
        )
        assert "inline-diff-container" in inline_html

        # Test side-by-side view (default)
        side_by_side_html = document_diff_viewer.generate_document_diff(
            sample_segments,
            sample_cleaning_results,
            view_mode="side_by_side"
        )
        assert "document-diff-container" in side_by_side_html
        assert "diff-panel" in side_by_side_html
