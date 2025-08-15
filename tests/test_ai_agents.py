"""
Modern tests for AI agents using Pydantic AI best practices.

Tests essential functionality using TestModel, Agent.override(), and proper mocking strategies.
"""

import os
import pytest
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.models.test import TestModel

from agents.transcript.cleaner import cleaning_agent
from agents.transcript.reviewer import review_agent
from models.agents import CleaningResult, ReviewResult
from models.transcript import VTTChunk, VTTEntry

# Block real model requests during testing
os.environ["ALLOW_MODEL_REQUESTS"] = "False"


class TestTranscriptCleaningAgent:
    """Test transcript cleaning agent using Pydantic AI best practices."""

    @pytest.mark.asyncio
    async def test_cleaning_agent_basic(self):
        """Test basic cleaning functionality with TestModel."""
        # Create test data
        entry = VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=5.0,
            speaker="John",
            text="Um, so like, we need to, uh, finalize the budget."
        )
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=20)
        
        # Mock successful cleaning result
        mock_result = CleaningResult(
            cleaned_text="John: We need to finalize the budget.",
            confidence=0.95,
            changes_made=["Removed filler words", "Fixed punctuation"]
        )
        
        # Use TestModel for deterministic testing
        test_model = TestModel(custom_output_args=mock_result)
        
        with cleaning_agent.override(model=test_model):
            result = await cleaning_agent.run(
                f"Clean this transcript:\\n{chunk.to_transcript_text()}",
                deps={"prev_text": ""}
            )
            
        assert isinstance(result.output, CleaningResult)
        assert result.output.confidence >= 0.8
        assert len(result.output.changes_made) > 0
        assert "John:" in result.output.cleaned_text

    @pytest.mark.asyncio
    async def test_cleaning_agent_with_context(self):
        """Test cleaning agent with dependency context."""
        entry = VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=5.0,
            speaker="Sarah",
            text="The database migration is critical."
        )
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=15)
        
        # Test context for dynamic instructions
        context = {
            'position': 'start',
            'meeting_type': 'technical',
            'action_heavy': True
        }
        
        mock_result = CleaningResult(
            cleaned_text="Sarah: The database migration is critical.",
            confidence=0.98,
            changes_made=["Preserved technical terms"]
        )
        
        test_model = TestModel(custom_output_args=mock_result)
        
        with cleaning_agent.override(model=test_model):
            result = await cleaning_agent.run(
                f"Clean this transcript:\\n{chunk.to_transcript_text()}",
                deps=context
            )
            
        assert isinstance(result.output, CleaningResult)
        assert "Sarah:" in result.output.cleaned_text

    @pytest.mark.asyncio
    async def test_cleaning_agent_message_capture(self):
        """Test agent messages are captured correctly."""
        entry = VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=5.0,
            speaker="Mike",
            text="Let's review the quarterly report."
        )
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=12)
        
        mock_result = CleaningResult(
            cleaned_text="Mike: Let's review the quarterly report.",
            confidence=0.92,
            changes_made=["Minor formatting"]
        )
        
        test_model = TestModel(custom_output_args=mock_result)
        
        with cleaning_agent.override(model=test_model):
            with capture_run_messages() as captured_messages:
                result = await cleaning_agent.run(
                    f"Clean this transcript:\\n{chunk.to_transcript_text()}",
                    deps={"prev_text": ""}
                )
        
        # Verify message structure
        assert len(captured_messages) >= 1
        assert any("Clean this transcript" in str(msg) for msg in captured_messages)
        assert isinstance(result.output, CleaningResult)


class TestTranscriptReviewAgent:
    """Test transcript review agent using Pydantic AI best practices."""

    @pytest.mark.asyncio
    async def test_review_agent_basic(self):
        """Test basic review functionality with TestModel."""
        # Create test data
        entry = VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=5.0,
            speaker="John",
            text="Um, so like, we need to, uh, finalize the budget."
        )
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=20)
        cleaned_text = "John: We need to finalize the budget."
        
        # Mock successful review result
        mock_result = ReviewResult(
            quality_score=0.85,
            issues=["Minor grammatical improvements possible"],
            accept=True
        )
        
        # Use TestModel for deterministic testing
        test_model = TestModel(custom_output_args=mock_result)
        
        with review_agent.override(model=test_model):
            result = await review_agent.run(
                f"Original: {chunk.to_transcript_text()}\\n\\nCleaned: {cleaned_text}"
            )
            
        assert isinstance(result.output, ReviewResult)
        assert result.output.quality_score >= 0.7
        assert result.output.accept is True
        assert isinstance(result.output.issues, list)

    @pytest.mark.asyncio
    async def test_review_agent_rejection(self):
        """Test review agent rejecting poor quality cleaning."""
        entry = VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=5.0,
            speaker="John",
            text="We need to finalize the budget."
        )
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=15)
        # Simulate poor cleaning
        cleaned_text = "Budget finalize need we."
        
        mock_result = ReviewResult(
            quality_score=0.45,
            issues=["Speaker attribution lost", "Word order incorrect", "Meaning unclear"],
            accept=False
        )
        
        test_model = TestModel(custom_output_args=mock_result)
        
        with review_agent.override(model=test_model):
            result = await review_agent.run(
                f"Original: {chunk.to_transcript_text()}\\n\\nCleaned: {cleaned_text}"
            )
            
        assert isinstance(result.output, ReviewResult)
        assert result.output.quality_score < 0.7
        assert result.output.accept is False
        assert len(result.output.issues) > 0

    @pytest.mark.asyncio
    async def test_review_agent_edge_cases(self):
        """Test review agent with edge cases."""
        # Empty chunk
        entry = VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=1.0,
            speaker="Unknown",
            text=""
        )
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=1)
        cleaned_text = ""
        
        mock_result = ReviewResult(
            quality_score=0.3,
            issues=["Empty content"],
            accept=False
        )
        
        test_model = TestModel(custom_output_args=mock_result)
        
        with review_agent.override(model=test_model):
            result = await review_agent.run(
                f"Original: {chunk.to_transcript_text()}\\n\\nCleaned: {cleaned_text}"
            )
            
        assert isinstance(result.output, ReviewResult)
        assert result.output.accept is False


@pytest.fixture
def mock_vtt_chunk():
    """Fixture providing a standard VTT chunk for testing."""
    entries = [
        VTTEntry(
            cue_id="test-1",
            start_time=0.0,
            end_time=5.0,
            speaker="John",
            text="Hello everyone, let's start the meeting."
        ),
        VTTEntry(
            cue_id="test-2",
            start_time=5.0,
            end_time=10.0,
            speaker="Sarah",
            text="Good morning John, I'm ready."
        )
    ]
    return VTTChunk(chunk_id=0, entries=entries, token_count=25)


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    @pytest.mark.asyncio
    async def test_cleaning_and_review_pipeline(self, mock_vtt_chunk):
        """Test complete cleaning -> review pipeline."""
        # Mock cleaning result
        cleaning_result = CleaningResult(
            cleaned_text="John: Hello everyone, let's start the meeting.\\nSarah: Good morning John, I'm ready.",
            confidence=0.93,
            changes_made=["Improved punctuation", "Preserved speaker names"]
        )
        
        # Mock review result
        review_result = ReviewResult(
            quality_score=0.88,
            issues=[],
            accept=True
        )
        
        cleaning_model = TestModel(custom_output_args=cleaning_result)
        review_model = TestModel(custom_output_args=review_result)
        
        # Test cleaning
        with cleaning_agent.override(model=cleaning_model):
            clean_result = await cleaning_agent.run(
                f"Clean this transcript:\\n{mock_vtt_chunk.to_transcript_text()}",
                deps={"prev_text": ""}
            )
        
        # Test review
        with review_agent.override(model=review_model):
            review_result = await review_agent.run(
                f"Original: {mock_vtt_chunk.to_transcript_text()}\\n\\nCleaned: {clean_result.output.cleaned_text}"
            )
        
        assert clean_result.output.confidence > 0.8
        assert review_result.output.accept is True
        assert review_result.output.quality_score > 0.8