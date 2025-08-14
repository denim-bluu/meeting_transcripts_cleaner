import time

from pydantic_ai import Agent
import structlog

from models.simple_intelligence import MeetingIntelligence
from models.vtt import VTTChunk
from services.chunk_processor import ChunkProcessor
from services.topic_synthesizer import TopicSynthesizer
from utils.semantic_chunker import SemanticChunker

logger = structlog.get_logger(__name__)


class SimpleIntelligenceService:
    """
    Main interface for simple topic-based meeting intelligence.

    Responsibilities:
    - Orchestrate the 4-phase processing pipeline
    - Semantic chunking -> Parallel processing -> Topic synthesis -> Action extraction
    - Return markdown summary and action items
    - Track processing stats

    Expected behavior:
    - 60-min meeting processes in <10 seconds
    - Uses 10-15 API calls total
    - Returns human-readable markdown
    """

    def __init__(self, api_key: str, model: str = "o3-mini"):
        self.chunker = SemanticChunker()
        self.processor = ChunkProcessor(api_key, model)
        self.synthesizer = TopicSynthesizer(api_key, model)
        self.api_key = api_key
        # Create structured output agent for final synthesis
        self.synthesis_agent = Agent(f"openai:{model}", output_type=MeetingIntelligence)
        logger.info("SimpleIntelligenceService initialized", model=model)

    async def process_meeting(
        self, cleaned_chunks: list[VTTChunk]
    ) -> MeetingIntelligence:
        """
        Main processing pipeline for meeting intelligence.

        Returns MeetingIntelligence with structured action items and markdown summary.
        """
        start_time = time.time()
        logger.info("Starting meeting processing", vtt_chunks=len(cleaned_chunks))

        # Phase 1: Semantic chunking (no API calls)
        semantic_chunks = self.chunker.create_chunks(cleaned_chunks)

        # Phase 2: Parallel chunk processing (N API calls)
        chunk_results = await self.processor.process_chunks_parallel(semantic_chunks)

        # Phase 3: Collect all data for structured synthesis
        raw_action_items = []
        for result in chunk_results:
            if result["importance_score"] >= 7:  # High importance
                raw_action_items.extend(result.get("action_items", []))

        # Phase 4: Single structured synthesis call
        synthesis_data = {
            "chunk_results": chunk_results,
            "topics": self.synthesizer.extract_topics(chunk_results),
            "raw_action_items": raw_action_items,
        }

        intelligence_result = await self._synthesize_with_structure(synthesis_data)

        processing_time = int((time.time() - start_time) * 1000)

        # Calculate API calls: N chunks + 1 synthesis
        api_calls = len(semantic_chunks) + 1

        # Add processing stats
        intelligence_result.processing_stats = {
            "vtt_chunks": len(cleaned_chunks),
            "semantic_chunks": len(semantic_chunks),
            "api_calls": api_calls,
            "time_ms": processing_time,
            "avg_importance": sum(r["importance_score"] for r in chunk_results)
            / len(chunk_results),
        }

        logger.info(
            "Meeting processing completed", **intelligence_result.processing_stats
        )
        return intelligence_result

    async def _synthesize_with_structure(
        self, synthesis_data: dict
    ) -> MeetingIntelligence:
        """Synthesize meeting data into structured output with minimal complexity."""

        # Organize key points by topic for summary generation
        topic_points = {}
        for topic in synthesis_data["topics"]:
            topic_points[topic] = []
            for result in synthesis_data["chunk_results"]:
                if (
                    topic in result.get("topics", [])
                    and result["importance_score"] >= 6
                ):
                    topic_points[topic].extend(result["key_points"])

        # Create prompt for structured synthesis
        prompt = f"""
        Create a comprehensive meeting summary and extract action items.

        TOPICS AND KEY POINTS:
        {self._format_topic_points(topic_points)}

        RAW ACTION ITEMS (need processing):
        {chr(10).join(f"- {item}" for item in synthesis_data["raw_action_items"])}

        Generate a meeting summary with:
        1. summary: Markdown format with topic headers (# Topic) and bullet points
        2. action_items: Structured list with description, owner, and due_date fields

        For action items:
        - Extract owner from text like "(Owner: John)" or "John should"
        - Extract due_date from text like "(Due: Friday)" or "by Friday"
        - Clean up and deduplicate
        - Only include actionable items (not discussion points)
        """

        result = await self.synthesis_agent.run(prompt)

        logger.info(
            "Structured synthesis completed",
            action_items_count=len(result.output.action_items),
            summary_length=len(result.output.summary),
        )

        return result.output

    def _format_topic_points(self, topic_points: dict) -> str:
        """Format topic points for the synthesis prompt."""
        formatted = []
        for topic, points in topic_points.items():
            if points:
                formatted.append(f"\n{topic}:")
                for point in points[:5]:  # Limit to 5 points per topic
                    formatted.append(f"  - {point}")
        return "\n".join(formatted)
