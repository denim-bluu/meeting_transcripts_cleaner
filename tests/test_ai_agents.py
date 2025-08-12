"""
Simple, focused tests for AI agents without over-engineering.

Tests only essential functionality for the simplified 2-layer architecture.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from core.ai_agents import TranscriptCleaner, TranscriptReviewer
from models.vtt import VTTChunk, VTTEntry


class TestTranscriptCleanerSimple:
    """Essential tests for TranscriptCleaner."""
    
    def test_cleaner_initialization(self):
        """Test cleaner initializes correctly."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")
        assert cleaner.model == "o3-mini"
        assert cleaner.client is not None
    
    @pytest.mark.asyncio
    async def test_clean_chunk_basic(self):
        """Test basic chunk cleaning works."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")
        cleaner.client = AsyncMock()
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "cleaned_text": "Hello world",
            "confidence": 0.9,
            "changes_made": ["test"]
        })
        cleaner.client.chat.completions.create.return_value = mock_response
        
        # Test chunk
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10
        )
        
        result = await cleaner.clean_chunk(chunk)
        
        assert "cleaned_text" in result
        assert "confidence" in result
        assert "changes_made" in result
        assert result["cleaned_text"] == "Hello world"
        assert result["confidence"] == 0.9
    
    @pytest.mark.asyncio
    async def test_clean_chunk_handles_missing_fields(self):
        """Test cleaner handles incomplete responses gracefully."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")
        cleaner.client = AsyncMock()
        
        # Mock incomplete response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "cleaned_text": "Hello world"
            # Missing confidence and changes_made
        })
        cleaner.client.chat.completions.create.return_value = mock_response
        
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10
        )
        
        result = await cleaner.clean_chunk(chunk)
        
        assert result["cleaned_text"] == "Hello world"
        assert result["confidence"] == 0.5  # Default fallback
        assert result["changes_made"] == []  # Default fallback


class TestTranscriptReviewerSimple:
    """Essential tests for TranscriptReviewer."""
    
    def test_reviewer_initialization(self):
        """Test reviewer initializes correctly."""
        reviewer = TranscriptReviewer("test-key", "o3-mini")
        assert reviewer.model == "o3-mini"
        assert reviewer.client is not None
    
    @pytest.mark.asyncio
    async def test_review_chunk_basic(self):
        """Test basic chunk review works."""
        reviewer = TranscriptReviewer("test-key", "o3-mini")
        reviewer.client = AsyncMock()
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "quality_score": 0.85,
            "issues": [],
            "accept": True
        })
        reviewer.client.chat.completions.create.return_value = mock_response
        
        # Test chunk
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10
        )
        
        result = await reviewer.review_chunk(chunk, "Hello world")
        
        assert "quality_score" in result
        assert "issues" in result
        assert "accept" in result
        assert result["quality_score"] == 0.85
        assert result["accept"] is True
    
    @pytest.mark.asyncio
    async def test_review_acceptance_threshold(self):
        """Test that acceptance logic works correctly."""
        reviewer = TranscriptReviewer("test-key", "o3-mini")
        reviewer.client = AsyncMock()
        
        # Test score >= 0.7 (should accept)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "quality_score": 0.7,
            "issues": []
        })
        reviewer.client.chat.completions.create.return_value = mock_response
        
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            token_count=10
        )
        
        result = await reviewer.review_chunk(chunk, "Hello world")
        assert result["accept"] is True
        
        # Test score < 0.7 (should reject)
        mock_response.choices[0].message.content = json.dumps({
            "quality_score": 0.6,
            "issues": ["Poor quality"]
        })
        
        result = await reviewer.review_chunk(chunk, "Hello world")
        assert result["accept"] is False


class TestAIAgentsIntegrationSimple:
    """Simple integration tests."""
    
    @pytest.mark.asyncio
    async def test_cleaning_and_review_pipeline(self):
        """Test that cleaner and reviewer work together."""
        cleaner = TranscriptCleaner("test-key", "o3-mini")
        reviewer = TranscriptReviewer("test-key", "o3-mini")
        
        # Mock both agents
        cleaner.client = AsyncMock()
        reviewer.client = AsyncMock()
        
        # Mock cleaning response
        clean_mock = MagicMock()
        clean_mock.choices = [MagicMock()]
        clean_mock.choices[0].message.content = json.dumps({
            "cleaned_text": "Welcome to the meeting",
            "confidence": 0.95,
            "changes_made": ["Removed filler words"]
        })
        cleaner.client.chat.completions.create.return_value = clean_mock
        
        # Mock review response
        review_mock = MagicMock()
        review_mock.choices = [MagicMock()]
        review_mock.choices[0].message.content = json.dumps({
            "quality_score": 0.9,
            "issues": [],
            "accept": True
        })
        reviewer.client.chat.completions.create.return_value = review_mock
        
        # Test chunk
        chunk = VTTChunk(
            chunk_id=0,
            entries=[VTTEntry("1", 0.0, 5.0, "Speaker", "Um, welcome to the meeting")],
            token_count=20
        )
        
        # Run pipeline
        clean_result = await cleaner.clean_chunk(chunk)
        review_result = await reviewer.review_chunk(chunk, clean_result["cleaned_text"])
        
        # Verify results
        assert clean_result["confidence"] == 0.95
        assert len(clean_result["changes_made"]) == 1
        assert review_result["quality_score"] == 0.9
        assert review_result["accept"] is True