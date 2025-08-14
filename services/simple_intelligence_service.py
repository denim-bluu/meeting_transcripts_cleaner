import asyncio
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
        Main processing pipeline for meeting intelligence with detailed progress tracking.

        Returns MeetingIntelligence with structured action items and markdown summary.
        """
        start_time = time.time()
        logger.info("Starting meeting processing", vtt_chunks=len(cleaned_chunks))

        # Phase 1: Semantic chunking (no API calls)
        logger.info("Phase 1: Starting semantic chunking")
        phase1_start = time.time()
        semantic_chunks = self.chunker.create_chunks(cleaned_chunks)
        phase1_time = int((time.time() - phase1_start) * 1000)
        logger.info(
            "Phase 1 completed: Semantic chunking",
            semantic_chunks=len(semantic_chunks),
            time_ms=phase1_time,
        )

        # Phase 2: Parallel chunk processing (N API calls) with error resilience
        logger.info(
            "Phase 2: Starting parallel chunk processing",
            chunks_to_process=len(semantic_chunks),
        )
        phase2_start = time.time()

        try:
            chunk_results = await self.processor.process_chunks_parallel(
                semantic_chunks
            )
            phase2_time = int((time.time() - phase2_start) * 1000)
            logger.info(
                "Phase 2 completed: Chunk processing",
                processed_chunks=len(chunk_results),
                time_ms=phase2_time,
            )
        except Exception as e:
            phase2_time = int((time.time() - phase2_start) * 1000)
            logger.error(
                "Phase 2 failed: Chunk processing",
                error=str(e),
                time_ms=phase2_time,
                chunks_attempted=len(semantic_chunks),
            )
            raise Exception(f"Chunk processing failed: {str(e)}")

        # Phase 3: Data collection for synthesis (reduced filtering)
        logger.info("Phase 3: Collecting data for synthesis")
        phase3_start = time.time()
        raw_action_items = []
        high_importance_chunks = 0
        medium_importance_chunks = 0

        for result in chunk_results:
            # Collect action items from medium-high importance chunks (lowered from 7 to 6)
            if result["importance_score"] >= 6:
                if result["importance_score"] >= 7:
                    high_importance_chunks += 1
                else:
                    medium_importance_chunks += 1
                raw_action_items.extend(result.get("action_items", []))

        # Extract and cluster topics into major themes
        topics = await self.synthesizer.extract_and_cluster_topics(chunk_results)

        synthesis_data = {
            "chunk_results": chunk_results,
            "topics": topics,
            "raw_action_items": raw_action_items,
        }

        phase3_time = int((time.time() - phase3_start) * 1000)
        logger.info(
            "Phase 3 completed: Data collection",
            unique_topics=len(topics),
            high_importance_chunks=high_importance_chunks,
            medium_importance_chunks=medium_importance_chunks,
            raw_action_items=len(raw_action_items),
            time_ms=phase3_time,
        )

        # Phase 4: Single structured synthesis call
        logger.info("Phase 4: Starting structured synthesis")
        phase4_start = time.time()
        intelligence_result = await self._synthesize_with_structure(synthesis_data)
        phase4_time = int((time.time() - phase4_start) * 1000)
        logger.info(
            "Phase 4 completed: Synthesis",
            action_items_generated=len(intelligence_result.action_items),
            summary_length=len(intelligence_result.summary),
            time_ms=phase4_time,
        )

        total_processing_time = int((time.time() - start_time) * 1000)

        # Calculate API calls: N chunks + 1 synthesis
        api_calls = len(semantic_chunks) + 1

        # Add processing stats with phase breakdowns
        intelligence_result.processing_stats = {
            "vtt_chunks": len(cleaned_chunks),
            "semantic_chunks": len(semantic_chunks),
            "api_calls": api_calls,
            "time_ms": total_processing_time,
            "avg_importance": sum(r["importance_score"] for r in chunk_results)
            / len(chunk_results),
            "phase_times": {
                "semantic_chunking_ms": phase1_time,
                "chunk_processing_ms": phase2_time,
                "data_collection_ms": phase3_time,
                "synthesis_ms": phase4_time,
            },
        }

        logger.info(
            "Meeting processing completed successfully",
            **{
                k: v
                for k, v in intelligence_result.processing_stats.items()
                if k != "phase_times"
            },
        )
        return intelligence_result

    async def _synthesize_with_structure(
        self, synthesis_data: dict
    ) -> MeetingIntelligence:
        """Synthesize meeting data into structured output with progress logging."""
        logger.info(
            "Starting structured synthesis",
            topics_to_process=len(synthesis_data["topics"]),
        )

        # Organize key points by topic for summary generation (reduced filtering)
        topic_points = {}
        points_included = 0
        for topic in synthesis_data["topics"]:
            topic_points[topic] = []
            for result in synthesis_data["chunk_results"]:
                # Lowered threshold from 6 to 5 to include more context
                # Also include high-scoring chunks even if topic doesn't exactly match
                topic_match = topic in result.get("topics", [])
                high_importance = result["importance_score"] >= 8

                if (topic_match and result["importance_score"] >= 5) or high_importance:
                    # Include all key points (no limits)
                    points_to_add = result["key_points"]
                    topic_points[topic].extend(points_to_add)
                    points_included += len(points_to_add)

        logger.info(
            "Organized content for synthesis",
            topics_with_content=len([t for t, p in topic_points.items() if p]),
            total_key_points=points_included,
            raw_action_items=len(synthesis_data["raw_action_items"]),
        )

        # Create enhanced prompt for detailed synthesis
        prompt = f"""
        Create a comprehensive technical meeting summary that preserves ALL important details.

        This is a business/technical meeting transcript. Preserve:
        - Speaker names and attributions (e.g., "Nathaniel Meixler explained that...")
        - Specific numbers, percentages, metrics (e.g., "70% accuracy", "2% threshold", "15% cap")
        - Technical terms and acronyms (e.g., "ARM", "13F filings", "DCF", "Smart Estimates")
        - Company/product names (e.g., "Starmine", "Mubadala", "ADIC", "Refinitiv")
        - Specific examples and use cases
        - Important quotes and explanations

        TOPICS AND DETAILED INFORMATION:
        {self._format_topic_points(topic_points)}

        RAW ACTION ITEMS (need processing):
        {chr(10).join(f"- {item}" for item in synthesis_data["raw_action_items"])}

        Generate a meeting summary with:
        1. summary: Detailed markdown with topic headers (# Topic) and comprehensive bullet points
           - Include speaker names where relevant
           - Preserve all technical details and numbers
           - Use sub-bullets (  -) for additional details
           - Maintain professional, technical tone
           - Group related information logically

        2. action_items: Structured list with description, owner, and due_date fields
           - Extract owner from text patterns like "(Owner: John)", "John should", "Nathaniel will"
           - Extract due_date from patterns like "(Due: Friday)", "by Friday", "ASAP"
           - Clean up and deduplicate similar actions
           - Only include actionable items (not discussion points)

        EXAMPLE OUTPUT FORMAT:
        # Model Development and Architecture
        - Nathaniel Meixler explained that Starmine's Combined Alpha Model (CAM) is a linear combination of factor models
        - ARM (Analyst Revision Model) uses Predicted Surprise with 70% accuracy when above 2% threshold
        - Intrinsic valuation model uses discounted dividend approach rather than DCF due to lower forecast errors
          - Non-dividend payers use simulated dividends based on future earnings and payout ratios
          - Payout ratios ramp over time with eventual 15% cap in year 15
        """

        logger.info("Sending synthesis request to LLM")

        # Add retry logic for synthesis as well
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(
                        f"Retrying synthesis attempt {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(2.0 * attempt)  # Brief delay on retry

                result = await self.synthesis_agent.run(prompt)

                logger.info(
                    "Structured synthesis completed",
                    action_items_count=len(result.output.action_items),
                    summary_length=len(result.output.summary),
                    summary_sections=result.output.summary.count("#"),
                    attempts=attempt + 1,
                )

                return result.output

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Synthesis failed, will retry",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    continue
                else:
                    logger.error(
                        "Synthesis failed after all retries",
                        error=str(e),
                        total_attempts=max_retries,
                    )
                    raise

    def _format_topic_points(self, topic_points: dict) -> str:
        """Format topic points for synthesis with full detail preservation."""
        formatted = []
        for topic, points in topic_points.items():
            if points:
                formatted.append(f"\n{topic}:")
                # Include ALL points (removed the 5-point limit)
                for point in points:
                    formatted.append(f"  - {point}")

        if not formatted:
            return "No detailed points available"

        logger.debug(
            "Formatted topic points",
            topics_count=len([t for t, p in topic_points.items() if p]),
            total_points=sum(len(points) for points in topic_points.values()),
        )

        return "\n".join(formatted)
