import pytest
from unittest.mock import AsyncMock, patch
from services.orchestration.intelligence_orchestrator import IntelligenceOrchestrator
from services.extraction.chunk_extractor import ChunkExtractor
from utils.semantic_chunker import SemanticChunker
from models.transcript import VTTChunk, VTTEntry
from models.intelligence import MeetingIntelligence, ActionItem, ChunkInsights

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

class TestChunkExtractor:
    """Test chunk processing functionality."""

    def test_chunk_extractor_initialization(self):
        """Test ChunkExtractor initializes correctly."""
        processor = ChunkExtractor("o3-mini")
        assert processor.agent is not None

    @pytest.mark.asyncio
    async def test_extract_insights(self):
        """Test insight extraction from a single chunk."""
        processor = ChunkExtractor("o3-mini")
        
        # Mock the agent to return a proper ChunkInsights object
        with patch.object(processor.agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_result = ChunkInsights(
                insights=[
                    "Budget planning discussion with John proposing 15% increase",
                    "Timeline considerations for Q3 implementation",
                    "Resource allocation needs to be finalized by Friday",
                    "Technical architecture decisions regarding PostgreSQL",
                    "Action item assignments and deadline clarifications"
                ],
                importance=8,
                themes=["Budget", "Planning"],
                actions=["Review budget by Friday (Owner: John)"]
            )
            mock_run.return_value.output = mock_result
            
            result = await processor.extract_insights("Sample meeting text", 1, 3)
            
            assert isinstance(result, ChunkInsights)
            assert result.importance == 8
            assert len(result.insights) == 5
            assert len(result.themes) == 2
            assert len(result.actions) == 1

class TestIntelligenceOrchestrator:
    """Test the main intelligence service."""

    def test_intelligence_orchestrator_initialization(self):
        """Test IntelligenceOrchestrator initializes correctly."""
        service = IntelligenceOrchestrator("o3-mini")
        assert service.chunker is not None
        assert service.extractor is not None
        assert service.synthesizer is not None
        # Production thresholds set correctly
        assert service.MIN_IMPORTANCE == 4
        assert service.CRITICAL_IMPORTANCE == 8
        assert service.CONTEXT_LIMIT == 50000

    @pytest.mark.asyncio
    async def test_process_meeting(self, sample_vtt_chunks):
        """Test complete intelligence processing."""
        service = IntelligenceOrchestrator("o3-mini")
        
        # Mock the semantic chunker
        with patch.object(service.chunker, 'create_chunks') as mock_chunk:
            mock_chunk.return_value = ["semantic chunk 1", "semantic chunk 2"]
            
            # Mock chunk extraction
            mock_insights = [
                ChunkInsights(
                    insights=[
                        "Budget discussion with John proposing 15% increase",
                        "Timeline review for Q3 implementation deadlines",
                        "Resource allocation planning for development team",
                        "Technical decisions regarding PostgreSQL migration",
                        "Action item assignments and responsibility tracking"
                    ],
                    importance=8,
                    themes=["Budget", "Planning"],
                    actions=["Review budget by Friday (Owner: John)"]
                ),
                ChunkInsights(
                    insights=[
                        "Resource allocation for engineering team discussed",
                        "Database migration timeline established by Sarah",
                        "Testing requirements specified for new features",
                        "Deployment strategy reviewed with DevOps team",
                        "Performance benchmarks set for Q3 delivery"
                    ],
                    importance=6,
                    themes=["Resources"],
                    actions=[]
                )
            ]
            
            with patch.object(service.extractor, 'extract_all_insights', new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = mock_insights
                
                # Mock token estimation (should use direct synthesis for small content)
                with patch.object(service, '_estimate_tokens') as mock_estimate:
                    mock_estimate.return_value = 10000  # Small enough for direct synthesis
                    
                    # Mock direct synthesis
                    with patch.object(service.synthesizer, 'synthesize_intelligence_direct', new_callable=AsyncMock) as mock_synth:
                        mock_result = MeetingIntelligence(
                            summary="# Executive Summary\nBudget and planning meeting with key decisions.\n\n# Key Decisions\n- Budget increase approved\n\n# Discussion by Topic\n## Budget Planning\n- John proposed 15% budget increase for Q3\n- Resource allocation planning discussed\n\n## Timeline Management\n- Q3 implementation deadlines reviewed\n- Action item assignments clarified\n\n# Action Items\n- Action: Review budget by Friday\n  Owner: John\n  Due: Friday\n  Context: Budget approval process",
                            action_items=[
                                ActionItem(description="Review budget by Friday", owner="John", due_date="Friday")
                            ],
                            processing_stats={}
                        )
                        mock_synth.return_value = mock_result
                        
                        result = await service.process_meeting(sample_vtt_chunks)
                    
                    # Check that result is MeetingIntelligence
                    assert isinstance(result, MeetingIntelligence)
                    
                    # Check Microsoft Teams Premium style format
                    assert result.summary.startswith("# Executive Summary")
                    assert "# Key Decisions" in result.summary
                    assert "# Discussion by Topic" in result.summary
                    assert "# Action Items" in result.summary
                    assert "Budget Planning" in result.summary
                    
                    # Check structured action items
                    assert len(result.action_items) == 1
                    assert isinstance(result.action_items[0], ActionItem)
                    assert result.action_items[0].description == "Review budget by Friday"
                    assert result.action_items[0].owner == "John"
                    assert result.action_items[0].due_date == "Friday"

    @pytest.mark.asyncio
    async def test_hierarchical_synthesis_fallback(self, sample_vtt_chunks):
        """Test hierarchical synthesis for large content."""
        service = IntelligenceOrchestrator("o3-mini")
        
        # Mock the semantic chunker
        with patch.object(service.chunker, 'create_chunks') as mock_chunk:
            mock_chunk.return_value = ["semantic chunk 1", "semantic chunk 2"]
            
            # Mock chunk extraction with large content
            mock_insights = [
                ChunkInsights(
                    insights=[f"Insight {i} with detailed content" for i in range(10)],
                    importance=8,
                    themes=["Budget", "Planning"],
                    actions=["Action item"]
                ) for _ in range(20)  # Many insights to trigger hierarchical
            ]
            
            with patch.object(service.extractor, 'extract_all_insights', new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = mock_insights
                
                # Mock token estimation (large enough for hierarchical synthesis)
                with patch.object(service, '_estimate_tokens') as mock_estimate:
                    mock_estimate.return_value = 60000  # Large enough for hierarchical
                    
                    # Mock hierarchical synthesis
                    with patch.object(service.synthesizer, 'synthesize_intelligence_hierarchical', new_callable=AsyncMock) as mock_synth:
                        mock_result = MeetingIntelligence(
                            summary="# Executive Summary\nLong meeting with comprehensive coverage.\n\n# Key Decisions\n- Multiple decisions across segments",
                            action_items=[
                                ActionItem(description="Follow up on long meeting outcomes", owner="Team")
                            ],
                            processing_stats={}
                        )
                        mock_synth.return_value = mock_result
                        
                        result = await service.process_meeting(sample_vtt_chunks)
                        
                        # Verify hierarchical synthesis was called
                        mock_synth.assert_called_once()
                        assert isinstance(result, MeetingIntelligence)
                        assert "Long meeting" in result.summary

class TestIntelligenceModels:
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

    def test_chunk_insights_validation(self):
        """Test ChunkInsights model validation."""
        insights = ChunkInsights(
            insights=[
                "Important point 1 with detailed context",
                "Important point 2 with speaker attribution",
                "Technical decision made regarding architecture",
                "Budget allocation discussed for next quarter",
                "Action items assigned to team members"
            ],
            importance=7,
            themes=["Budget", "Planning"],
            actions=["Action item with owner"]
        )
        
        assert len(insights.insights) == 5
        assert insights.importance == 7
        assert len(insights.themes) == 2
        assert len(insights.actions) == 1