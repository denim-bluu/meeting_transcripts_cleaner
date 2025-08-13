"""
Tests for meeting intelligence extraction system.

Covers data models, agents, service orchestration, and integration with existing components.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest
from pydantic import ValidationError

from models.intelligence import ActionItem, ChunkSummary, IntelligenceResult
from models.vtt import VTTChunk, VTTEntry
from core.intelligence_agents import SummaryExtractor, ActionItemExtractor, IntelligenceSynthesizer
from services.intelligence_service import IntelligenceService, ReviewLevel


class TestDataModels:
    """Test intelligence data models validation and behavior."""
    
    def test_action_item_validation(self):
        """Test ActionItem model validation rules."""
        # Valid action item
        valid_item = ActionItem(
            description="Complete the project documentation",
            owner="John Doe",
            deadline="2024-01-15",
            source_chunks=[1],
            confidence=0.75
        )
        assert valid_item.description == "Complete the project documentation"
        assert valid_item.needs_review is True  # confidence < 0.8 should trigger review
        
        # Test minimum description length
        with pytest.raises(ValidationError):
            ActionItem(
                description="Too short",  # Less than 10 chars
                source_chunks=[1],
                confidence=0.9
            )
        
        # Test confidence range
        with pytest.raises(ValidationError):
            ActionItem(
                description="Valid description here",
                source_chunks=[1],
                confidence=1.5  # > 1.0
            )
        
        # Test needs_review auto-calculation
        high_confidence_item = ActionItem(
            description="High confidence item",
            source_chunks=[1],
            confidence=0.95,
            is_critical=False
        )
        assert high_confidence_item.needs_review is False
        
        critical_item = ActionItem(
            description="Critical item regardless of confidence",
            source_chunks=[1],
            confidence=0.95,
            is_critical=True
        )
        assert critical_item.needs_review is True
    
    def test_chunk_summary_validation(self):
        """Test ChunkSummary model validation rules."""
        # Valid summary
        valid_summary = ChunkSummary(
            key_points=["Point 1", "Point 2"],
            decisions=["Decision made"],
            topics=["Topic A"],
            speakers=["Speaker 1"],
            confidence=0.8
        )
        assert len(valid_summary.key_points) == 2
        
        # Test key_points limits
        with pytest.raises(ValidationError):
            ChunkSummary(
                key_points=[],  # Empty list
                topics=["Topic A"],
                speakers=["Speaker 1"],
                confidence=0.8
            )
        
        with pytest.raises(ValidationError):
            ChunkSummary(
                key_points=["Point 1", "Point 2", "Point 3", "Point 4", "Point 5", "Point 6"],  # > 5
                topics=["Topic A"],
                speakers=["Speaker 1"],
                confidence=0.8
            )
    
    def test_intelligence_result_validation(self):
        """Test IntelligenceResult model validation rules."""
        # Valid result
        valid_result = IntelligenceResult(
            executive_summary="Brief summary",
            detailed_summary="Detailed summary here",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Topic A"],
            confidence_score=0.85
        )
        assert valid_result.confidence_score == 0.85
        
        # Test summary length limits
        with pytest.raises(ValidationError):
            IntelligenceResult(
                executive_summary="x" * 501,  # > 500 chars
                detailed_summary="Valid",
                bullet_points=["Point 1", "Point 2", "Point 3"],
                topics_discussed=["Topic A"],
                confidence_score=0.85
            )
        
        # Test bullet points limits
        with pytest.raises(ValidationError):
            IntelligenceResult(
                executive_summary="Valid",
                detailed_summary="Valid",
                bullet_points=["Point 1", "Point 2"],  # < 3 items
                topics_discussed=["Topic A"],
                confidence_score=0.85
            )


class TestIntelligenceAgents:
    """Test intelligence extraction agents."""
    
    @pytest.fixture
    def sample_window(self):
        """Sample context window for testing."""
        return {
            'chunk_id': 1,
            'full_context': 'Previous context. John: We need to complete the project by Friday. Sarah: I agree, let me handle the documentation. Next context.',
            'speakers': ['John', 'Sarah']
        }
    
    def test_summary_extractor_initialization(self):
        """Test SummaryExtractor initializes correctly."""
        extractor = SummaryExtractor("test-key", "gpt-4")
        assert extractor.model_name == "gpt-4"
        assert extractor.agent is not None
    
    @pytest.mark.asyncio
    async def test_summary_extractor_extract(self, sample_window):
        """Test summary extraction with mocked agent."""
        extractor = SummaryExtractor("test-key", "gpt-4")
        
        # Mock the agent run method
        mock_result = MagicMock()
        mock_result.output = ChunkSummary(
            key_points=["Project deadline discussion"],
            decisions=["Project due Friday"],
            topics=["Project timeline"],
            speakers=["John", "Sarah"],
            confidence=0.9
        )
        
        with patch.object(extractor.agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            
            result = await extractor.extract(sample_window)
            
            assert isinstance(result, ChunkSummary)
            assert "Project deadline discussion" in result.key_points
            assert result.confidence == 0.9
            mock_run.assert_called_once()
    
    def test_action_item_extractor_initialization(self):
        """Test ActionItemExtractor initializes correctly."""
        extractor = ActionItemExtractor("test-key", "gpt-4")
        assert extractor.model_name == "gpt-4"
        assert extractor.agent is not None
    
    @pytest.mark.asyncio
    async def test_action_item_extractor_extract(self, sample_window):
        """Test action item extraction with mocked agent."""
        extractor = ActionItemExtractor("test-key", "gpt-4")
        
        # Mock the agent run method
        mock_action_item = ActionItem(
            description="Handle the documentation",
            owner="Sarah",
            source_chunks=[1],
            confidence=0.85
        )
        
        mock_result = MagicMock()
        mock_result.output = [mock_action_item]
        
        with patch.object(extractor.agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            
            result = await extractor.extract(sample_window)
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0].description == "Handle the documentation"
            assert result[0].owner == "Sarah"
            mock_run.assert_called_once()
    
    def test_intelligence_synthesizer_initialization(self):
        """Test IntelligenceSynthesizer initializes correctly."""
        synthesizer = IntelligenceSynthesizer("test-key", "gpt-4")
        assert synthesizer.model_name == "gpt-4"
        assert synthesizer.agent is not None
    
    @pytest.mark.asyncio
    async def test_intelligence_synthesizer_synthesize(self):
        """Test intelligence synthesis with mocked agent."""
        synthesizer = IntelligenceSynthesizer("test-key", "gpt-4")
        
        # Sample extractions
        extractions = [
            {
                'summary': ChunkSummary(
                    key_points=["Point 1"],
                    topics=["Topic A"],
                    speakers=["John"],
                    confidence=0.9
                ),
                'actions': [
                    ActionItem(
                        description="Complete task 1",
                        source_chunks=[1],
                        confidence=0.8
                    )
                ]
            }
        ]
        
        # Mock the agent run method
        mock_result = MagicMock()
        mock_result.output = IntelligenceResult(
            executive_summary="Meeting summary",
            detailed_summary="Detailed meeting summary",
            bullet_points=["Key point 1", "Key point 2", "Key point 3"],
            action_items=[
                ActionItem(
                    description="Complete task 1",
                    source_chunks=[1],
                    confidence=0.8
                )
            ],
            topics_discussed=["Topic A"],
            confidence_score=0.85,
            processing_stats={}
        )
        
        with patch.object(synthesizer.agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            
            result = await synthesizer.synthesize(extractions)
            
            assert isinstance(result, IntelligenceResult)
            assert result.executive_summary == "Meeting summary"
            assert len(result.action_items) == 1
            assert "total_processing_time_ms" in result.processing_stats
            mock_run.assert_called_once()


class TestIntelligenceService:
    """Test intelligence service orchestration."""
    
    @pytest.fixture
    def sample_chunks(self):
        """Sample VTT chunks for testing."""
        return [
            VTTChunk(
                chunk_id=0,
                entries=[
                    VTTEntry(
                        cue_id="1",
                        start_time=0.0,
                        end_time=5.0,
                        speaker="John",
                        text="We need to complete the project by Friday."
                    )
                ],
                token_count=50
            ),
            VTTChunk(
                chunk_id=1,
                entries=[
                    VTTEntry(
                        cue_id="2",
                        start_time=5.0,
                        end_time=10.0,
                        speaker="Sarah",
                        text="I'll handle the documentation."
                    )
                ],
                token_count=45
            )
        ]
    
    def test_intelligence_service_initialization(self):
        """Test IntelligenceService initializes correctly."""
        service = IntelligenceService("test-key", max_concurrent=5)
        assert service.api_key == "test-key"
        assert service.semaphore._value == 5
        assert service.summary_extractor is not None
        assert service.action_extractor is not None
        assert service.synthesizer is not None
    
    def test_create_context_windows(self, sample_chunks):
        """Test context window creation."""
        service = IntelligenceService("test-key")
        windows = service.create_context_windows(sample_chunks)
        
        assert len(windows) == 2
        
        # First window should have no context before
        assert windows[0]['chunk_id'] == 0
        assert 'John: We need to complete' in windows[0]['full_context']
        assert 'I\'ll handle the documentation' in windows[0]['full_context']  # Context after
        
        # Second window should have context before
        assert windows[1]['chunk_id'] == 1
        assert 'We need to complete the project' in windows[1]['full_context']  # Context before
        assert 'Sarah: I\'ll handle' in windows[1]['full_context']
    
    def test_determine_review_level(self):
        """Test review level determination logic."""
        service = IntelligenceService("test-key")
        
        # High confidence, no critical content
        high_confidence_result = IntelligenceResult(
            executive_summary="Normal meeting summary",
            detailed_summary="No critical content here",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Regular topic"],
            confidence_score=0.95
        )
        assert service.determine_review_level(high_confidence_result) == ReviewLevel.NONE
        
        # Medium confidence
        medium_confidence_result = IntelligenceResult(
            executive_summary="Meeting summary",
            detailed_summary="Regular content",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Regular topic"],
            confidence_score=0.8
        )
        assert service.determine_review_level(medium_confidence_result) == ReviewLevel.LIGHT
        
        # Low confidence
        low_confidence_result = IntelligenceResult(
            executive_summary="Meeting summary",
            detailed_summary="Regular content",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Regular topic"],
            confidence_score=0.6
        )
        assert service.determine_review_level(low_confidence_result) == ReviewLevel.DETAILED
        
        # Critical content regardless of confidence
        critical_content_result = IntelligenceResult(
            executive_summary="Discussion about budget cuts and legal implications",
            detailed_summary="We need to review the million dollar contract",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Budget"],
            confidence_score=0.95
        )
        assert service.determine_review_level(critical_content_result) == ReviewLevel.DETAILED
    
    def test_contains_critical_content(self):
        """Test critical content detection."""
        service = IntelligenceService("test-key")
        
        # Test with critical keywords
        critical_result = IntelligenceResult(
            executive_summary="Meeting about budget approval",
            detailed_summary="We discussed the legal implications",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            action_items=[
                ActionItem(
                    description="Review the million dollar contract",
                    source_chunks=[1],
                    confidence=0.9
                )
            ],
            topics_discussed=["Budget"],
            confidence_score=0.9
        )
        assert service._contains_critical_content(critical_result) is True
        
        # Test without critical keywords
        normal_result = IntelligenceResult(
            executive_summary="Regular project meeting",
            detailed_summary="Discussed timeline and deliverables",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Project"],
            confidence_score=0.9
        )
        assert service._contains_critical_content(normal_result) is False
    
    def test_export_json(self):
        """Test JSON export functionality."""
        service = IntelligenceService("test-key")
        
        result = IntelligenceResult(
            executive_summary="Test summary",
            detailed_summary="Test detailed summary",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Test topic"],
            confidence_score=0.9
        )
        
        json_export = service.export_json(result)
        assert isinstance(json_export, str)
        assert "Test summary" in json_export
        assert "confidence_score" in json_export
    
    def test_export_markdown(self):
        """Test Markdown export functionality."""
        service = IntelligenceService("test-key")
        
        result = IntelligenceResult(
            executive_summary="Test summary",
            detailed_summary="Test detailed summary",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            action_items=[
                ActionItem(
                    description="Test action item",
                    owner="John",
                    deadline="Friday",
                    source_chunks=[1],
                    confidence=0.8
                )
            ],
            topics_discussed=["Test topic"],
            confidence_score=0.9
        )
        
        markdown_export = service.export_markdown(result)
        assert isinstance(markdown_export, str)
        assert "# Meeting Intelligence Report" in markdown_export
        assert "## Executive Summary" in markdown_export
        assert "## Action Items" in markdown_export
        assert "Test action item" in markdown_export
        assert "@John" in markdown_export
    
    def test_export_csv(self):
        """Test CSV export functionality."""
        service = IntelligenceService("test-key")
        
        result = IntelligenceResult(
            executive_summary="Test summary",
            detailed_summary="Test detailed summary",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            action_items=[
                ActionItem(
                    description="Test action item",
                    owner="John",
                    deadline="Friday",
                    dependencies=["Task A"],
                    source_chunks=[1, 2],
                    confidence=0.8,
                    is_critical=True
                )
            ],
            topics_discussed=["Test topic"],
            confidence_score=0.9
        )
        
        csv_export = service.export_csv(result)
        assert isinstance(csv_export, str)
        assert "Description,Owner,Deadline" in csv_export
        assert "Test action item,John,Friday" in csv_export
        assert "Yes" in csv_export  # is_critical = True
    
    @pytest.mark.asyncio
    async def test_extract_intelligence_basic_flow(self, sample_chunks):
        """Test basic intelligence extraction flow with mocks."""
        service = IntelligenceService("test-key")
        
        # Mock the extractors and synthesizer
        mock_summary = ChunkSummary(
            key_points=["Key point"],
            topics=["Topic"],
            speakers=["John"],
            confidence=0.9
        )
        
        mock_action = ActionItem(
            description="Test action item",
            source_chunks=[1],
            confidence=0.8
        )
        
        mock_intelligence_result = IntelligenceResult(
            executive_summary="Test summary",
            detailed_summary="Test detailed summary",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            action_items=[mock_action],
            topics_discussed=["Topic"],
            confidence_score=0.85,
            processing_stats={}
        )
        
        with patch.object(service.summary_extractor, 'extract', new_callable=AsyncMock) as mock_summary_extract, \
             patch.object(service.action_extractor, 'extract', new_callable=AsyncMock) as mock_action_extract, \
             patch.object(service.synthesizer, 'synthesize', new_callable=AsyncMock) as mock_synthesize:
            
            mock_summary_extract.return_value = mock_summary
            mock_action_extract.return_value = [mock_action]
            mock_synthesize.return_value = mock_intelligence_result
            
            result = await service.extract_intelligence(sample_chunks)
            
            assert isinstance(result, IntelligenceResult)
            assert result.executive_summary == "Test summary"
            assert len(result.action_items) == 1
            assert "total_pipeline_time_ms" in result.processing_stats
            
            # Verify all extractors were called
            assert mock_summary_extract.call_count == len(sample_chunks)
            assert mock_action_extract.call_count == len(sample_chunks)
            mock_synthesize.assert_called_once()


class TestIntegration:
    """Test integration with existing TranscriptService."""
    
    @pytest.mark.asyncio
    async def test_transcript_service_intelligence_integration(self):
        """Test that TranscriptService can extract intelligence."""
        from services.transcript_service import TranscriptService
        
        service = TranscriptService("test-key")
        
        # Mock transcript with chunks
        mock_transcript = {
            'chunks': [
                VTTChunk(
                    chunk_id=0,
                    entries=[
                        VTTEntry(
                            cue_id="1",
                            start_time=0.0,
                            end_time=5.0,
                            speaker="John",
                            text="Test meeting content."
                        )
                    ],
                    token_count=50
                )
            ]
        }
        
        mock_intelligence_result = IntelligenceResult(
            executive_summary="Test summary",
            detailed_summary="Test detailed summary",
            bullet_points=["Point 1", "Point 2", "Point 3"],
            topics_discussed=["Topic"],
            confidence_score=0.85,
            processing_stats={}
        )
        
        # Mock the IntelligenceService where it's imported in the method
        from services import intelligence_service
        with patch.object(intelligence_service, 'IntelligenceService') as mock_intelligence_service_class:
            mock_intelligence_service = MagicMock()
            mock_intelligence_service.extract_intelligence = AsyncMock(return_value=mock_intelligence_result)
            mock_intelligence_service_class.return_value = mock_intelligence_service
            
            result = await service.extract_intelligence(mock_transcript)
            
            assert 'intelligence' in result
            assert result['intelligence'] == mock_intelligence_result
            mock_intelligence_service.extract_intelligence.assert_called_once()
    
    def test_transcript_service_intelligence_no_chunks(self):
        """Test intelligence extraction fails gracefully with no chunks."""
        from services.transcript_service import TranscriptService
        
        service = TranscriptService("test-key")
        
        # Empty transcript
        empty_transcript = {}
        
        with pytest.raises(ValueError, match="No chunks available"):
            asyncio.run(service.extract_intelligence(empty_transcript))