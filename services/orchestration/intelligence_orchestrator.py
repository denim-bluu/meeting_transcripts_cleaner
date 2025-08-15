"""Main intelligence orchestration - clean, simple pipeline."""

import time

import structlog

from models.intelligence import MeetingIntelligence
from models.transcript import VTTChunk
from services.extraction.chunk_extractor import ChunkExtractor
from services.extraction.topic_clusterer import TopicClusterer
from services.synthesis.intelligence_synthesizer import IntelligenceSynthesizer
from utils.semantic_chunker import SemanticChunker

logger = structlog.get_logger(__name__)


class IntelligenceOrchestrator:
    """
    Clean, simple orchestration of the intelligence pipeline.

    Responsibilities:
    - Coordinate the 4-phase processing pipeline
    - Semantic chunking → Extraction → Clustering → Synthesis
    - Track processing stats and performance
    """

    def __init__(self, model: str = "o3-mini"):
        self.chunker = SemanticChunker()
        self.extractor = ChunkExtractor(model)
        self.clusterer = TopicClusterer(model)
        self.synthesizer = IntelligenceSynthesizer(model)

        logger.info("IntelligenceOrchestrator initialized", model=model)

    async def process_meeting(
        self, cleaned_chunks: list[VTTChunk]
    ) -> MeetingIntelligence:
        """
        Main processing pipeline with comprehensive logging.

        Returns MeetingIntelligence with structured output.
        """
        start_time = time.time()
        logger.info("Starting intelligence processing", vtt_chunks=len(cleaned_chunks))

        # Phase 1: Semantic chunking (no API calls)
        logger.info("Phase 1: Starting semantic chunking")
        phase1_start = time.time()
        semantic_chunks = self.chunker.create_chunks(cleaned_chunks)
        phase1_time = int((time.time() - phase1_start) * 1000)
        logger.info(
            "Phase 1 completed",
            semantic_chunks=len(semantic_chunks),
            time_ms=phase1_time,
        )

        # Phase 2: Extract insights from all chunks (N API calls)
        logger.info(
            "Phase 2: Starting insight extraction",
            chunks_to_process=len(semantic_chunks),
        )
        phase2_start = time.time()
        insights_list = await self.extractor.extract_all_insights(semantic_chunks)
        phase2_time = int((time.time() - phase2_start) * 1000)
        logger.info(
            "Phase 2 completed",
            insights_extracted=len(insights_list),
            time_ms=phase2_time,
        )

        # Phase 3: Cluster themes (1 API call if needed)
        logger.info("Phase 3: Starting theme clustering")
        phase3_start = time.time()
        all_themes = self.clusterer.extract_all_themes(insights_list)
        major_themes = await self.clusterer.cluster_themes(all_themes)
        phase3_time = int((time.time() - phase3_start) * 1000)
        logger.info(
            "Phase 3 completed", major_themes=len(major_themes), time_ms=phase3_time
        )

        # Phase 4: Synthesize final intelligence (1 API call)
        logger.info("Phase 4: Starting intelligence synthesis")
        phase4_start = time.time()
        intelligence = await self.synthesizer.synthesize_intelligence(
            insights_list, major_themes
        )
        phase4_time = int((time.time() - phase4_start) * 1000)
        logger.info(
            "Phase 4 completed",
            summary_length=len(intelligence.summary),
            action_items=len(intelligence.action_items),
            time_ms=phase4_time,
        )

        # Calculate final stats
        total_time = int((time.time() - start_time) * 1000)
        api_calls = len(semantic_chunks) + (1 if len(all_themes) > 8 else 0) + 1
        avg_importance = sum(i.importance for i in insights_list) / len(insights_list)

        # Add processing stats
        intelligence.processing_stats = {
            "vtt_chunks": len(cleaned_chunks),
            "semantic_chunks": len(semantic_chunks),
            "api_calls": api_calls,
            "time_ms": total_time,
            "avg_importance": round(avg_importance, 2),
            "phase_times": {
                "semantic_chunking_ms": phase1_time,
                "insight_extraction_ms": phase2_time,
                "theme_clustering_ms": phase3_time,
                "synthesis_ms": phase4_time,
            },
        }

        logger.info(
            "Intelligence processing completed successfully",
            api_calls=api_calls,
            total_time_ms=total_time,
            avg_importance=round(avg_importance, 2),
        )

        return intelligence
