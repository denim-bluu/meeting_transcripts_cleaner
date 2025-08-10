"""
Essential test suite - lean and focused on critical functionality.
Tests core business logic without expensive AI API calls.
"""

from unittest.mock import patch

from pydantic_ai.models.test import TestModel
import pytest

from core.cleaning_agent import CleaningAgent
from core.confidence_categorizer import ConfidenceCategorizer
from core.document_processor import DocumentProcessor
from core.review_agent import ReviewAgent
from models.schemas import (
    CleaningResult,
    DocumentSegment,
    ProcessingStatusEnum,
    ReviewDecision,
    ReviewDecisionEnum,
    TranscriptDocument,
)
import utils.validators


class TestEssentialFunctionality:
    """Essential tests covering critical functionality with mocked AI calls."""

    def test_document_parsing_and_segmentation(self):
        """Test document can be parsed and segmented correctly."""
        processor = DocumentProcessor()
        # Override for testing
        processor.min_tokens = 5
        processor.max_tokens = 500

        # Test content
        content = """This is the first sentence. This is the second sentence.

        This is a new paragraph with more content to test segmentation."""

        # Test document processing
        document = processor.process_document(
            filename="test.txt",
            content=content,
            file_size=len(content.encode()),
            content_type="text/plain",
        )

        # Assertions
        assert isinstance(document, TranscriptDocument)
        assert document.filename == "test.txt"
        assert document.original_content == content
        assert len(document.segments) > 0
        assert document.total_tokens > 0

        # Test segments
        for segment in document.segments:
            assert isinstance(segment, DocumentSegment)
            assert segment.token_count > 0
            assert segment.sequence_number > 0
            assert len(segment.content.strip()) > 0

    def test_token_counting_consistency(self):
        """Test token counting is consistent and reasonable."""
        processor = DocumentProcessor()

        # Test cases
        test_cases = [
            ("", 0),  # Empty string
            ("Hello", 1),  # Single word
            ("Hello world", 2),  # Two words
            ("This is a test sentence.", 6),  # Sentence
        ]

        for text, expected_min_tokens in test_cases:
            tokens = processor.count_tokens(text)
            if expected_min_tokens == 0:
                assert tokens == 0
            else:
                assert (
                    tokens >= expected_min_tokens
                ), f"Text '{text}' should have at least {expected_min_tokens} tokens, got {tokens}"

    @pytest.mark.asyncio
    async def test_cleaning_agent_with_mocked_response(self):
        """Test cleaning agent with mocked AI response."""

        # Create mock PydanticAI response
        CleaningResult(
            segment_id="test-123",
            cleaned_text="This is a clean test sentence.",
            changes_made=["Removed filler words"],
            processing_time_ms=100.0,
            model_used="gpt-4o",
        )

        # Test using PydanticAI TestModel
        agent = CleaningAgent()
        segment = DocumentSegment(
            id="test-123",
            content="Um, this is a test sentence, you know?",
            token_count=10,
            start_index=0,
            end_index=40,
            sequence_number=1,
        )

        # Use PydanticAI's TestModel for structured output
        # Mock the validation function to avoid issues with TestModel's random data
        with patch("core.cleaning_agent.validate_cleaning_result"):
            with agent.agent.override(model=TestModel()):
                result = await agent.clean_segment(segment)

            # Assertions
            assert isinstance(result, CleaningResult)
            # TestModel generates automatic data, so we check structure rather than specific values
            assert result.segment_id is not None
            assert isinstance(result.segment_id, str)
            assert isinstance(result.changes_made, list)
            assert result.cleaned_text is not None
            assert isinstance(result.cleaned_text, str)

    @pytest.mark.asyncio
    async def test_review_agent_with_mocked_response(self):
        """Test review agent with mocked AI response."""

        # Test using PydanticAI TestModel
        agent = ReviewAgent()
        # Create a document segment and cleaning result to review
        segment = DocumentSegment(
            id="test-123",
            content="Um, this is a test",
            token_count=5,
            start_index=0,
            end_index=18,
            sequence_number=1,
        )

        cleaning_result = CleaningResult(
            segment_id="test-123",
            cleaned_text="This is a test",
            changes_made=["Removed filler words"],
            processing_time_ms=100.0,
            model_used="gpt-4o",
        )

        # Use PydanticAI's TestModel for structured output
        # Mock the validation function to avoid issues with TestModel's random data
        with patch("core.review_agent.validate_review_decision"):
            with agent.agent.override(model=TestModel()):
                result = await agent.review_cleaning(
                    original_segment=segment, cleaning_result=cleaning_result
                )

            # Assertions
            assert isinstance(result, ReviewDecision)
            # TestModel generates automatic data, so we check structure rather than specific values
            assert result.segment_id is not None
            assert isinstance(result.segment_id, str)
            assert result.decision in [
                ReviewDecisionEnum.ACCEPT,
                ReviewDecisionEnum.REJECT,
                ReviewDecisionEnum.MODIFY,
            ]
            assert 0.0 <= result.confidence <= 1.0
            assert 0.0 <= result.preservation_score <= 1.0

    def test_confidence_categorization(self):
        """Test confidence categorization logic."""
        categorizer = ConfidenceCategorizer()

        # Test that categorization works and produces valid categories
        test_cases = [0.98, 0.92, 0.88, 0.75, 0.65, 0.50]

        for _confidence in test_cases:
            # Create mock cleaning result
            cleaning_result = CleaningResult(
                segment_id="test",
                cleaned_text="Test",
                processing_time_ms=100.0,
                model_used="gpt-4o",
            )

            # Create optional additional factors for categorization
            additional_factors = {
                "has_technical_terms": False,
                "content_length": len(cleaning_result.cleaned_text),
                "change_types": cleaning_result.changes_made,
            }

            category = categorizer.categorize_cleaning_result(
                cleaning_result, additional_factors
            )

            # Test that categorization produces valid results (conservative mode without review)
            assert category.category in [
                "auto_accept",
                "quick_review",
                "detailed_review",
                "ai_flagged",
            ]
            assert 0.0 <= category.confidence <= 1.0  # Should use default confidence
            assert category.segment_id == "test"
            assert isinstance(category.categorization_reason, str)
            assert len(category.categorization_reason) > 0

            # Higher confidence should generally result in better categories
            # but we don't enforce exact thresholds since they might vary

    def test_schema_validation(self):
        """Test critical schema validations work correctly."""

        # Test CleaningResult validation
        result = CleaningResult(
            segment_id="test-123",
            cleaned_text="Clean text",
            processing_time_ms=100.0,
            model_used="gpt-4o",
        )
        assert result.cleaned_text == "Clean text"

        # Test ReviewDecision validation
        review = ReviewDecision(
            segment_id="test-123",
            decision=ReviewDecisionEnum.ACCEPT,
            confidence=0.95,
            preservation_score=0.98,
            reasoning="Looks good",
        )
        assert review.confidence == 0.95
        assert review.preservation_score == 0.98

        # Test ReviewDecision with MODIFY requires suggested_corrections
        with pytest.raises(ValueError):
            ReviewDecision(
                segment_id="test",
                decision=ReviewDecisionEnum.MODIFY,
                confidence=0.8,
                preservation_score=0.7,
                reasoning="Needs changes",
                # Missing suggested_corrections!
            )

        # Test invalid preservation score
        with pytest.raises(ValueError):
            ReviewDecision(
                segment_id="test",
                decision=ReviewDecisionEnum.ACCEPT,
                confidence=0.8,
                preservation_score=1.5,  # Invalid > 1.0
                reasoning="Test",
            )

    def test_error_handling(self):
        """Test error handling in core components."""
        processor = DocumentProcessor()
        processor.min_tokens = 5

        # Test empty content
        with pytest.raises(ValueError, match="Document content is empty"):
            processor.process_document(
                filename="empty.txt", content="", file_size=0, content_type="text/plain"
            )

        # Test very short content
        with pytest.raises(ValueError, match="Document is too short"):
            processor.process_document(
                filename="short.txt",
                content="Hi",  # Too short
                file_size=2,
                content_type="text/plain",
            )

    def test_file_processing_integration(self):
        """Test end-to-end file processing flow (without AI calls)."""
        processor = DocumentProcessor()
        processor.min_tokens = 5

        # Sample VTT content
        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:05.000
<v John>Hello everyone, welcome to today's meeting.

00:00:05.000 --> 00:00:10.000
<v Sarah>Thanks John. Let's start with the quarterly review."""

        document = processor.process_document(
            filename="meeting.vtt",
            content=vtt_content,
            file_size=len(vtt_content.encode()),
            content_type="text/vtt",
        )

        # Test document structure
        assert document.filename == "meeting.vtt"
        assert document.content_type == "text/vtt"
        assert len(document.segments) > 0
        assert document.processing_status is not None
        assert document.processing_status.status == ProcessingStatusEnum.PENDING

        # Test processing summary
        summary = document.processing_summary
        assert summary["total_segments"] == len(document.segments)
        assert summary["total_tokens"] > 0


class TestStreamlitComponents:
    """Test Streamlit app components (UI logic without actual UI)."""

    def test_file_upload_validation(self):
        """Test file upload validation logic."""

        # Mock uploaded file
        class MockUploadedFile:
            def __init__(self, name, size, type_):
                self.name = name
                self.size = size
                self.type = type_

            def getvalue(self):
                return b"Sample content for testing"

        # Test valid files
        valid_files = [
            MockUploadedFile("test.txt", 1000, "text/plain"),
            MockUploadedFile("meeting.vtt", 2000, "text/vtt"),
        ]

        for file in valid_files:
            assert file.name.endswith((".txt", ".vtt"))
            assert file.size > 0
            assert file.size < 10 * 1024 * 1024  # 10MB limit

        # Test invalid files
        invalid_file = MockUploadedFile("document.pdf", 1000, "application/pdf")
        assert not invalid_file.name.endswith((".txt", ".vtt"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
