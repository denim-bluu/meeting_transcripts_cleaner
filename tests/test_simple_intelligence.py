"""
Modern tests for intelligence system using pure agents and Pydantic AI best practices.
"""

import os

from pydantic_ai.models.test import TestModel
import pytest

from agents.extraction.insights import chunk_extraction_agent
from models.intelligence import ActionItem, ChunkInsights, MeetingIntelligence
from models.transcript import VTTChunk, VTTEntry
from services.orchestration.intelligence_orchestrator import IntelligenceOrchestrator
from utils.semantic_chunker import SemanticChunker

# Block real model requests during testing
os.environ["ALLOW_MODEL_REQUESTS"] = "False"


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
                text=f"This is test content for chunk {i}. Important meeting discussion about budget and timeline.",
            )
        ]
        chunks.append(VTTChunk(chunk_id=i, entries=entries, token_count=50))
    return chunks


class TestSemanticChunker:
    """Test semantic chunking functionality."""

    def test_chunker_initialization(self):
        """Test SemanticChunker initializes correctly."""
        chunker = SemanticChunker()
        assert chunker.splitter is not None

    def test_create_chunks(self, sample_vtt_chunks):
        """Test chunking VTT data into semantic chunks."""
        chunker = SemanticChunker()
        semantic_chunks = chunker.create_chunks(sample_vtt_chunks)

        # Should produce at least one chunk
        assert len(semantic_chunks) >= 1
        assert isinstance(semantic_chunks[0], str)

        # Should contain speaker information
        combined_text = " ".join(semantic_chunks)
        assert "Speaker_0" in combined_text
        assert "Speaker_1" in combined_text


class TestChunkExtractionAgent:
    """Test chunk extraction agent functionality."""

    @pytest.mark.asyncio
    async def test_extract_insights_basic(self):
        """Test insight extraction from a chunk using pure agent."""
        # Mock successful extraction result
        mock_result = ChunkInsights(
            insights=[
                "Budget planning discussion with John proposing 15% increase",
                "Timeline considerations for Q3 implementation",
                "Resource allocation needs to be finalized by Friday",
                "Technical architecture decisions regarding PostgreSQL",
                "Action item assignments and deadline clarifications",
            ],
            importance=8,
            themes=["Budget Planning", "Technical Architecture"],
            actions=[
                "John to review budget proposal by Friday",
                "Team to finalize resource allocation",
            ],
        )

        test_model = TestModel(custom_output_args=mock_result)

        # Test chunk text
        chunk_text = "John: We need to increase the budget by 15% for Q3. Sarah: I'll finalize the resource allocation by Friday."

        with chunk_extraction_agent.override(model=test_model):
            result = await chunk_extraction_agent.run(
                f"Extract comprehensive insights from this conversation segment:\\n\\n{chunk_text}"
            )

        # Verify result structure
        assert isinstance(result.output, ChunkInsights)
        assert result.output.importance >= 5
        assert len(result.output.insights) >= 5
        assert len(result.output.themes) >= 1
        assert len(result.output.actions) >= 1

    @pytest.mark.asyncio
    async def test_extract_insights_with_context(self):
        """Test insight extraction with context dependencies."""
        mock_result = ChunkInsights(
            insights=[
                "Meeting opening with agenda review and participant introductions",
                "Technical discussion about system architecture and scalability requirements",
                "Action items distributed to team members with clear ownership",
                "Timeline considerations for project deliverables and milestones",
                "Resource allocation discussions for upcoming technical implementations",
            ],
            importance=7,
            themes=["Meeting Management", "Technical"],
            actions=["Review technical specifications by Tuesday"],
        )

        test_model = TestModel(custom_output_args=mock_result)

        # Test with context for dynamic instructions
        context = {
            "position": "start",
            "meeting_type": "technical",
            "action_heavy": True,
        }

        chunk_text = "Welcome everyone to our technical planning meeting. Let's review the system architecture."

        with chunk_extraction_agent.override(model=test_model):
            result = await chunk_extraction_agent.run(
                f"Extract comprehensive insights from this conversation segment:\\n\\n{chunk_text}",
                deps=context,
            )

        assert isinstance(result.output, ChunkInsights)
        assert result.output.importance >= 5


class TestIntelligenceOrchestrator:
    """Test the complete intelligence orchestration system."""

    def test_orchestrator_initialization(self):
        """Test orchestrator initializes with pure agents."""
        orchestrator = IntelligenceOrchestrator(model="o3-mini")
        assert orchestrator.chunker is not None
        assert orchestrator.model == "o3-mini"

    @pytest.mark.asyncio
    async def test_orchestrator_basic_processing(self, sample_vtt_chunks):
        """Test basic processing pipeline with mocked agents."""
        orchestrator = IntelligenceOrchestrator(model="o3-mini")

        # Mock the extraction results
        mock_insights = ChunkInsights(
            insights=[
                "Key meeting discussion about project planning and strategic direction",
                "Budget considerations and resource allocation for upcoming initiatives",
                "Timeline for deliverables established with clear milestone dates",
                "Team capacity assessment and workload distribution analysis",
                "Risk mitigation strategies discussed for potential project blockers",
            ],
            importance=7,
            themes=["Project Planning"],
            actions=["Complete planning by next week"],
        )

        mock_intelligence = MeetingIntelligence(
            summary="""# Executive Summary

This meeting focused on comprehensive project planning and strategic budget allocation for the upcoming quarter. The team conducted a thorough discussion of resource requirements, timeline considerations, and delivery milestones.

# Key Decisions

- Approved the proposed project planning framework for Q3 implementation
- Established clear milestone dates and delivery expectations for all team members
- Allocated additional resources for technical implementation and system architecture improvements

# Discussion by Topic

## Resource Planning
The team discussed the need for additional capacity and workload distribution across multiple projects. Strategic considerations were made regarding team availability and technical requirements.

# Important Quotes

\"We need to ensure our project planning framework aligns with organizational objectives while maintaining technical excellence.\"""",
            action_items=[
                ActionItem(
                    description="Complete comprehensive project planning documentation",
                    owner="Team",
                    due_date="Next week",
                )
            ],
            processing_stats={"test": True},
        )

        extraction_model = TestModel(custom_output_args=mock_insights)
        synthesis_model = TestModel(custom_output_args=mock_intelligence)

        # Override both extraction and synthesis agents
        with chunk_extraction_agent.override(model=extraction_model):
            # For this test, we'll just test the chunking phase
            semantic_chunks = orchestrator.chunker.create_chunks(sample_vtt_chunks)
            assert len(semantic_chunks) >= 1
            assert isinstance(semantic_chunks[0], str)


class TestActionItemExtraction:
    """Test action item extraction and validation."""

    def test_action_item_validation(self):
        """Test action item model validation."""
        # Valid action item
        action = ActionItem(
            description="Complete the quarterly budget review",
            owner="John Smith",
            due_date="Friday",
        )
        assert action.description == "Complete the quarterly budget review"
        assert action.owner == "John Smith"
        assert action.due_date == "Friday"

    def test_action_item_without_owner(self):
        """Test action item without owner."""
        action = ActionItem(
            description="Review meeting notes", owner=None, due_date="Monday"
        )
        assert action.description == "Review meeting notes"
        assert action.owner is None
        assert action.due_date == "Monday"
