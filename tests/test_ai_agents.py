"""
Simple, focused tests for AI agents using Pydantic AI.

Tests essential functionality for the Pydantic AI-based architecture.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ai_agents import TranscriptCleaner, TranscriptReviewer
from models.agents import CleaningResult, ReviewResult
from models.transcript import VTTChunk, VTTEntry


class TestTranscriptCleanerSimple:
    """Essential tests for TranscriptCleaner with Pydantic AI."""

    def test_cleaner_initialization(self):
        """Test cleaner initializes correctly."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")
        assert cleaner.model_name == "o3-mini"
        assert cleaner.agent is not None

    @pytest.mark.asyncio
    async def test_clean_chunk_basic(self):
        """Test basic chunk cleaning works."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")

        # Mock the agent run method to return a structured result
        mock_result = MagicMock()
        mock_result.output = CleaningResult(
            cleaned_text="Hello world", confidence=0.9, changes_made=["Fixed grammar"]
        )
        cleaner.agent.run = AsyncMock(return_value=mock_result)

        # Test chunk
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10,
        )

        result = await cleaner.clean_chunk(chunk)

        assert isinstance(result, CleaningResult)
        assert result.cleaned_text == "Hello world"
        assert result.confidence == 0.9
        assert result.changes_made == ["Fixed grammar"]

    @pytest.mark.asyncio
    async def test_clean_chunk_handles_errors(self):
        """Test cleaner handles API errors gracefully."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")

        # Mock the agent to raise an exception
        cleaner.agent.run = AsyncMock(side_effect=Exception("API Error"))

        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10,
        )

        with pytest.raises(Exception, match="API Error"):
            await cleaner.clean_chunk(chunk)


class TestTranscriptReviewerSimple:
    """Essential tests for TranscriptReviewer with Pydantic AI."""

    def test_reviewer_initialization(self):
        """Test reviewer initializes correctly."""
        reviewer = TranscriptReviewer("test-key", "o3-mini")
        assert reviewer.model_name == "o3-mini"
        assert reviewer.agent is not None

    @pytest.mark.asyncio
    async def test_review_chunk_basic(self):
        """Test basic chunk review works."""
        reviewer = TranscriptReviewer("test-key", "o3-mini")

        # Mock the agent run method
        mock_result = MagicMock()
        mock_result.output = ReviewResult(quality_score=0.85, issues=[], accept=True)
        reviewer.agent.run = AsyncMock(return_value=mock_result)

        # Test data
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10,
        )
        cleaned_text = "Hello world."

        result = await reviewer.review_chunk(chunk, cleaned_text)

        assert isinstance(result, ReviewResult)
        assert result.quality_score == 0.85
        assert result.accept == True
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_review_acceptance_threshold(self):
        """Test review accepts/rejects based on quality score."""
        reviewer = TranscriptReviewer("test-key", "o3-mini")

        # Mock poor quality result
        mock_result = MagicMock()
        mock_result.output = ReviewResult(
            quality_score=0.6, issues=["Grammar errors"], accept=False
        )
        reviewer.agent.run = AsyncMock(return_value=mock_result)

        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10,
        )

        result = await reviewer.review_chunk(chunk, "Poor quality text")

        assert result.quality_score == 0.6
        assert result.accept == False
        assert "Grammar errors" in result.issues


class TestAIAgentsIntegrationSimple:
    """Integration tests for cleaner and reviewer working together."""

    @pytest.mark.asyncio
    async def test_cleaning_and_review_pipeline(self):
        """Test complete cleaning and review pipeline."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")
        reviewer = TranscriptReviewer("test-key", "o3-mini")

        # Mock cleaner
        clean_mock_result = MagicMock()
        clean_mock_result.output = CleaningResult(
            cleaned_text="Good morning, everyone.",
            confidence=0.95,
            changes_made=["Added punctuation"],
        )
        cleaner.agent.run = AsyncMock(return_value=clean_mock_result)

        # Mock reviewer
        review_mock_result = MagicMock()
        review_mock_result.output = ReviewResult(
            quality_score=0.9, issues=[], accept=True
        )
        reviewer.agent.run = AsyncMock(return_value=review_mock_result)

        # Test chunk
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Good morning everyone")],
            token_count=15,
        )

        # Clean and review
        cleaned = await cleaner.clean_chunk(chunk)
        review = await reviewer.review_chunk(chunk, cleaned.cleaned_text)

        assert cleaned.confidence == 0.95
        assert review.accept == True
        assert review.quality_score == 0.9
