import pytest
from unittest.mock import AsyncMock, patch
from services.simple_intelligence_service import SimpleIntelligenceService
from services.chunk_processor import ChunkProcessor
from services.topic_synthesizer import TopicSynthesizer
from utils.semantic_chunker import SemanticChunker
from models.vtt import VTTChunk, VTTEntry
from models.simple_intelligence import MeetingIntelligence, ActionItem

@pytest.fixture
def sample_vtt_chunks():
    """Create sample VTT chunks for testing."""
    chunks = []
    for i in range(3):
        entries = [
            VTTEntry(
                cue_id=f"cue_{i}",
                start_time=i * 10.0,
                end_time=(i + 1) * 10.0,
                speaker=f"Speaker_{i % 2}",
                text=f"Important discussion point {i} about project planning and budget allocation."
            )
        ]
        chunks.append(VTTChunk(chunk_id=i, entries=entries, token_count=50))
    return chunks

class TestSemanticChunker:
    """Test semantic chunking functionality."""

    def test_semantic_chunker_initialization(self):
        """Test SemanticChunker initializes correctly."""
        chunker = SemanticChunker(chunk_size=2000, chunk_overlap=100)
        assert chunker.splitter.chunk_size == 2000
        assert chunker.splitter.chunk_overlap == 100

    def test_create_chunks(self, sample_vtt_chunks):
        """Test converting VTT chunks to semantic chunks."""
        chunker = SemanticChunker(chunk_size=100, chunk_overlap=20)
        semantic_chunks = chunker.create_chunks(sample_vtt_chunks)
        
        assert len(semantic_chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in semantic_chunks)
        # Should contain speaker information
        combined_text = " ".join(semantic_chunks)
        assert "Speaker_0" in combined_text
        assert "Speaker_1" in combined_text

class TestChunkProcessor:
    """Test chunk processing functionality."""

    def test_chunk_processor_initialization(self):
        """Test ChunkProcessor initializes correctly."""
        processor = ChunkProcessor("test-key", "o3-mini")
        assert processor.agent is not None

    def test_parse_result(self):
        """Test parsing LLM output into structured dict."""
        processor = ChunkProcessor("test-key")
        
        llm_output = """
        KEY POINTS:
        - Budget planning discussion
        - Timeline considerations
        
        IMPORTANCE: 8
        
        TOPICS:
        - Budget
        - Planning
        
        ACTION ITEMS:
        - Review budget by Friday (Owner: John)
        """
        
        result = processor._parse_result(llm_output, "original text")
        
        assert result["key_points"] == ["Budget planning discussion", "Timeline considerations"]
        assert result["importance_score"] == 8
        assert result["topics"] == ["Budget", "Planning"]
        assert result["action_items"] == ["Review budget by Friday (Owner: John)"]
        assert result["chunk_text"] == "original text"

    def test_parse_result_with_missing_sections(self):
        """Test parsing with incomplete LLM output."""
        processor = ChunkProcessor("test-key")
        
        llm_output = """
        KEY POINTS:
        - Only one point
        
        IMPORTANCE: invalid
        """
        
        result = processor._parse_result(llm_output, "text")
        
        assert result["key_points"] == ["Only one point"]
        assert result["importance_score"] == 5  # Default value
        assert result["topics"] == []
        assert result["action_items"] == []

    @pytest.mark.asyncio
    async def test_process_chunks_parallel(self):
        """Test parallel chunk processing."""
        processor = ChunkProcessor("test-key")
        
        # Mock the process_chunk method
        with patch.object(processor, 'process_chunk', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {
                "key_points": ["Test point"],
                "importance_score": 7,
                "topics": ["Test topic"],
                "action_items": [],
                "chunk_text": "test"
            }
            
            chunks = ["chunk1", "chunk2", "chunk3"]
            results = await processor.process_chunks_parallel(chunks, max_concurrent=2)
            
            assert len(results) == 3
            assert mock_process.call_count == 3
            for result in results:
                assert "key_points" in result
                assert "importance_score" in result

class TestTopicSynthesizer:
    """Test topic synthesis functionality."""

    def test_topic_synthesizer_initialization(self):
        """Test TopicSynthesizer initializes correctly."""
        synthesizer = TopicSynthesizer("test-key", "o3-mini")
        assert synthesizer.agent is not None

    def test_extract_topics(self):
        """Test extracting unique topics from chunk results."""
        synthesizer = TopicSynthesizer("test-key")
        
        chunk_results = [
            {"topics": ["Budget", "Planning"]},
            {"topics": ["Budget", "Timeline"]},
            {"topics": ["Planning", "Resources"]}
        ]
        
        topics = synthesizer.extract_topics(chunk_results)
        
        assert set(topics) == {"Budget", "Planning", "Timeline", "Resources"}

    def test_group_by_topic(self):
        """Test grouping chunks by topic."""
        synthesizer = TopicSynthesizer("test-key")
        
        chunk_results = [
            {"topics": ["Budget"], "importance_score": 8},
            {"topics": ["Planning"], "importance_score": 6},
            {"topics": ["Budget", "Planning"], "importance_score": 9}
        ]
        
        topics = ["Budget", "Planning"]
        groups = synthesizer.group_by_topic(chunk_results, topics)
        
        assert len(groups["Budget"]) == 2  # Chunks 0 and 2
        assert len(groups["Planning"]) == 2  # Chunks 1 and 2

    @pytest.mark.asyncio
    async def test_synthesize_topic(self):
        """Test synthesizing content for a specific topic."""
        synthesizer = TopicSynthesizer("test-key")
        
        # Mock the agent
        with patch.object(synthesizer.agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value.output = "# Budget\n- Budget discussion details\n- Financial planning"
            
            relevant_chunks = [
                {
                    "importance_score": 8,
                    "key_points": ["Budget review", "Cost analysis"]
                },
                {
                    "importance_score": 6,
                    "key_points": ["Timeline planning"]
                }
            ]
            
            result = await synthesizer.synthesize_topic("Budget", relevant_chunks)
            
            assert result.startswith("# Budget")
            assert "Budget discussion details" in result
            mock_run.assert_called_once()

class TestSimpleIntelligenceService:
    """Test the main intelligence service."""

    def test_simple_intelligence_service_initialization(self):
        """Test SimpleIntelligenceService initializes correctly."""
        service = SimpleIntelligenceService("test-key", "o3-mini")
        assert service.chunker is not None
        assert service.processor is not None
        assert service.synthesizer is not None

    @pytest.mark.asyncio
    async def test_process_meeting(self, sample_vtt_chunks):
        """Test complete intelligence processing with structured output."""
        service = SimpleIntelligenceService("test-key")
        
        # Mock all the processing steps
        with patch.object(service.chunker, 'create_chunks') as mock_chunk:
            mock_chunk.return_value = ["semantic chunk 1", "semantic chunk 2"]
            
            with patch.object(service.processor, 'process_chunks_parallel', new_callable=AsyncMock) as mock_process:
                mock_process.return_value = [
                    {
                        "key_points": ["Budget discussion", "Timeline review"],
                        "importance_score": 8,
                        "topics": ["Budget", "Planning"],
                        "action_items": ["Review budget by Friday (Owner: John)"],
                        "chunk_text": "sample text"
                    },
                    {
                        "key_points": ["Resource allocation"],
                        "importance_score": 6,
                        "topics": ["Resources"],
                        "action_items": [],
                        "chunk_text": "sample text 2"
                    }
                ]
                
                with patch.object(service.synthesizer, 'extract_topics') as mock_topics:
                    mock_topics.return_value = ["Budget", "Planning", "Resources"]
                    
                    with patch.object(service, '_synthesize_with_structure', new_callable=AsyncMock) as mock_synth:
                        # Create a proper MeetingIntelligence object
                        mock_result = MeetingIntelligence(
                            summary="# Budget\n- Budget discussion details\n\n# Planning\n- Timeline considerations",
                            action_items=[
                                ActionItem(description="Review budget by Friday", owner="John", due_date="Friday")
                            ],
                            processing_stats={}
                        )
                        mock_synth.return_value = mock_result
                        
                        result = await service.process_meeting(sample_vtt_chunks)
                        
                        # Check that result is MeetingIntelligence
                        assert isinstance(result, MeetingIntelligence)
                        
                        # Check summary format
                        assert result.summary.startswith("# Budget")
                        assert "Budget discussion details" in result.summary
                        
                        # Check structured action items
                        assert len(result.action_items) == 1
                        assert isinstance(result.action_items[0], ActionItem)
                        assert result.action_items[0].description == "Review budget by Friday"
                        assert result.action_items[0].owner == "John"
                        assert result.action_items[0].due_date == "Friday"
                        
                        # Check processing stats
                        stats = result.processing_stats
                        assert stats["vtt_chunks"] == 3
                        assert stats["semantic_chunks"] == 2
                        assert "api_calls" in stats
                        assert "time_ms" in stats

class TestSimpleIntelligenceModels:
    """Test the structured intelligence models."""

    def test_action_item_validation(self):
        """Test ActionItem model validation."""
        # Valid action item
        action = ActionItem(
            description="Complete the budget review",
            owner="John",
            due_date="Friday"
        )
        assert action.description == "Complete the budget review"
        assert action.owner == "John"
        assert action.due_date == "Friday"

        # Test minimum description length
        with pytest.raises(ValueError):
            ActionItem(description="Too short")

        # Test optional fields
        action_minimal = ActionItem(description="Valid description here")
        assert action_minimal.owner is None
        assert action_minimal.due_date is None

    def test_meeting_intelligence_validation(self):
        """Test MeetingIntelligence model validation."""
        # Valid intelligence result
        intelligence = MeetingIntelligence(
            summary="# Budget\n- Discussion about budget allocation",
            action_items=[
                ActionItem(description="Review budget by Friday", owner="John")
            ],
            processing_stats={"time_ms": 5000, "chunks": 10}
        )
        
        assert intelligence.summary.startswith("# Budget")
        assert len(intelligence.action_items) == 1
        assert intelligence.processing_stats["time_ms"] == 5000

        # Test with empty action items
        intelligence_empty = MeetingIntelligence(
            summary="# Meeting\n- No actions needed"
        )
        assert len(intelligence_empty.action_items) == 0
        assert len(intelligence_empty.processing_stats) == 0

    @pytest.mark.asyncio
    async def test_synthesize_with_structure(self):
        """Test structured synthesis method."""
        service = SimpleIntelligenceService("test-key")
        
        synthesis_data = {
            "chunk_results": [
                {
                    "key_points": ["Budget discussion", "Timeline review"],
                    "importance_score": 8,
                    "topics": ["Budget"]
                }
            ],
            "topics": ["Budget"],
            "raw_action_items": ["Review budget by Friday (Owner: John)"]
        }
        
        # Mock the synthesis agent
        with patch.object(service.synthesis_agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_result = MeetingIntelligence(
                summary="# Budget\n- Budget discussion details",
                action_items=[
                    ActionItem(description="Review budget by Friday", owner="John", due_date="Friday")
                ]
            )
            mock_run.return_value.output = mock_result
            
            result = await service._synthesize_with_structure(synthesis_data)
            
            assert isinstance(result, MeetingIntelligence)
            assert result.summary.startswith("# Budget")
            assert len(result.action_items) == 1
            assert result.action_items[0].owner == "John"