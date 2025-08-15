"""Main intelligence orchestration - clean, simple pipeline."""

import time

import structlog

# Use pure agents following Pydantic AI best practices
from agents.extraction.insights import chunk_extraction_agent
from agents.synthesis.direct import direct_synthesis_agent
from agents.synthesis.hierarchical import hierarchical_synthesis_agent
from agents.synthesis.segment import segment_synthesis_agent
from models.intelligence import ChunkInsights, MeetingIntelligence
from models.transcript import VTTChunk
from utils.semantic_chunker import SemanticChunker

logger = structlog.get_logger(__name__)


class IntelligenceOrchestrator:
    """
    Production-grade intelligence orchestration using industry-standard approach.

    Responsibilities:
    - Coordinate the 3-phase processing pipeline
    - Semantic chunking → Extraction → Hierarchical Synthesis
    - Automatic fallback for long meetings with temporal segmentation
    - Track processing stats and performance
    """

    def __init__(self, model: str = "o3-mini"):
        self.model = model
        self.chunker = SemanticChunker()

        self.MIN_IMPORTANCE = 2  # Include more contextual content for richer summaries
        self.CRITICAL_IMPORTANCE = 8  # Never exclude these
        self.CONTEXT_LIMIT = 50000  # Conservative token limit
        self.SEGMENT_MINUTES = 30  # Temporal segmentation

        logger.info(
            "IntelligenceOrchestrator initialized with pure agents",
            model=model,
            min_importance=self.MIN_IMPORTANCE,
            context_limit=self.CONTEXT_LIMIT,
        )

    async def process_meeting(
        self, cleaned_chunks: list[VTTChunk]
    ) -> MeetingIntelligence:
        """
        Two approaches:
        - Direct synthesis
        - Hierarchical synthesis with temporal segmentation

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
        insights_list = await self._extract_all_insights(semantic_chunks)
        phase2_time = int((time.time() - phase2_start) * 1000)
        logger.info(
            "Phase 2 completed",
            insights_extracted=len(insights_list),
            time_ms=phase2_time,
        )

        # Phase 3: Smart synthesis (industry-standard approach)
        logger.info("Phase 3: Starting intelligent synthesis")
        phase3_start = time.time()

        # Filter by importance (battle-tested threshold)
        important_insights = [
            i for i in insights_list if i.importance >= self.MIN_IMPORTANCE
        ]

        # Estimate tokens and choose synthesis path
        estimated_tokens = self._estimate_tokens(important_insights)

        if estimated_tokens <= self.CONTEXT_LIMIT:
            # COMMON CASE: Direct synthesis
            logger.info(
                "Using direct synthesis",
                estimated_tokens=estimated_tokens,
                filtered_insights=len(important_insights),
            )
            intelligence = await self._synthesize_direct(important_insights)
            synthesis_method = "direct"
        else:
            # EDGE CASE: Hierarchical synthesis
            logger.info(
                "Using hierarchical synthesis",
                estimated_tokens=estimated_tokens,
                filtered_insights=len(important_insights),
            )
            intelligence = await self._synthesize_hierarchical(
                important_insights, self.SEGMENT_MINUTES
            )
            synthesis_method = "hierarchical"

        phase3_time = int((time.time() - phase3_start) * 1000)
        logger.info(
            "Phase 3 completed",
            synthesis_method=synthesis_method,
            summary_length=len(intelligence.summary),
            action_items=len(intelligence.action_items),
            time_ms=phase3_time,
        )

        # Calculate final stats
        total_time = int((time.time() - start_time) * 1000)
        api_calls = len(semantic_chunks) + (1 if synthesis_method == "direct" else 2)
        avg_importance = sum(i.importance for i in insights_list) / len(insights_list)

        # Preserve critical insights check
        critical_insights = [
            i for i in insights_list if i.importance >= self.CRITICAL_IMPORTANCE
        ]
        critical_preserved = len(critical_insights)

        # Add processing stats
        intelligence.processing_stats = {
            "vtt_chunks": len(cleaned_chunks),
            "semantic_chunks": len(semantic_chunks),
            "api_calls": api_calls,
            "time_ms": total_time,
            "synthesis_method": synthesis_method,
            "avg_importance": round(avg_importance, 2),
            "insights_filtered": len(important_insights),
            "insights_total": len(insights_list),
            "critical_insights_preserved": critical_preserved,
            "estimated_tokens": estimated_tokens,
            "phase_times": {
                "semantic_chunking_ms": phase1_time,
                "insight_extraction_ms": phase2_time,
                "synthesis_ms": phase3_time,
            },
        }

        logger.info(
            "Intelligence processing completed successfully",
            api_calls=api_calls,
            total_time_ms=total_time,
            synthesis_method=synthesis_method,
            avg_importance=round(avg_importance, 2),
            critical_preserved=critical_preserved,
        )

        return intelligence

    def _estimate_tokens(self, insights_list) -> int:
        """
        Estimate tokens for synthesis based on insights content.

        Standard estimation (1 token ≈ 4 characters for GPT models).
        """
        total_chars = 0

        for insight in insights_list:
            # Count insights text
            total_chars += sum(len(text) for text in insight.insights)
            # Count themes
            total_chars += sum(len(theme) for theme in insight.themes)
            # Count actions
            total_chars += sum(len(action) for action in insight.actions)
            # Add metadata overhead
            total_chars += 100  # Importance, structure, etc.

        # Add prompt overhead (synthesis instructions)
        total_chars += 2000

        # Convert to tokens (standard GPT estimate)
        estimated_tokens = total_chars // 4

        logger.debug(
            "Token estimation completed",
            insights_count=len(insights_list),
            total_chars=total_chars,
            estimated_tokens=estimated_tokens,
        )

        return estimated_tokens

    async def _extract_all_insights(
        self, semantic_chunks: list[str]
    ) -> list[ChunkInsights]:
        """Extract insights from all semantic chunks using pure agent."""
        insights_list = []

        for i, chunk_text in enumerate(semantic_chunks):
            # Create context for dynamic instructions
            context = {
                "position": "start"
                if i == 0
                else "end"
                if i == len(semantic_chunks) - 1
                else "middle",
                "chunk_index": i,
                "total_chunks": len(semantic_chunks),
            }

            user_prompt = f"Extract comprehensive insights from this conversation segment:\n\n{chunk_text}"

            try:
                logger.info(
                    "Starting chunk extraction",
                    chunk_index=i + 1,
                    total_chunks=len(semantic_chunks),
                    chunk_size_chars=len(chunk_text),
                    position=context.get("position", "middle"),
                )

                result = await chunk_extraction_agent.run(user_prompt, deps=context)
                insights_list.append(result.output)

                logger.info(
                    "Chunk extraction completed",
                    chunk_index=i + 1,
                    importance=result.output.importance,
                    insights_count=len(result.output.insights),
                    themes=result.output.themes,
                    actions_count=len(result.output.actions),
                )
            except Exception as e:
                logger.error(
                    "Chunk extraction failed",
                    chunk_index=i + 1,
                    total_chunks=len(semantic_chunks),
                    error=str(e),
                    chunk_size_chars=len(chunk_text),
                )
                raise

        return insights_list

    async def _synthesize_direct(
        self, insights_list: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """Direct synthesis using pure agent."""
        formatted_insights = self._format_insights_for_synthesis(insights_list)

        user_prompt = f"""Create comprehensive meeting intelligence from these insights:

{formatted_insights}

Return both summary (detailed markdown) and action_items (structured list)."""

        try:
            result = await direct_synthesis_agent.run(user_prompt)
            return result.output
        except Exception as e:
            logger.error("Direct synthesis failed", error=str(e))
            raise

    async def _synthesize_hierarchical(
        self, insights_list: list[ChunkInsights], segment_minutes: int
    ) -> MeetingIntelligence:
        """Hierarchical synthesis using pure agents with temporal segmentation."""
        logger.info(
            "Starting hierarchical synthesis",
            total_insights=len(insights_list),
            segment_minutes=segment_minutes,
        )

        # Step 1: Group insights into temporal segments
        segments = self._group_insights_by_time(insights_list, segment_minutes)

        logger.info(
            "Temporal segmentation completed",
            segments_count=len(segments),
            avg_insights_per_segment=sum(len(seg) for seg in segments) / len(segments)
            if segments
            else 0,
        )

        # Step 2: Create segment summaries using segment_synthesis_agent
        segment_summaries = []
        for i, segment_insights in enumerate(segments):
            logger.info(
                "Processing segment",
                segment_index=i + 1,
                insights_in_segment=len(segment_insights),
            )

            # Format insights for segment synthesis
            segment_text = self._format_insights_for_synthesis(segment_insights)

            try:
                result = await segment_synthesis_agent.run(
                    f"Summarize this meeting segment:\n\n{segment_text}"
                )
                segment_summaries.append(result.output)

                logger.info(
                    "Segment synthesis completed",
                    segment_index=i + 1,
                    summary_length=len(result.output),
                )
            except Exception as e:
                logger.error(
                    "Segment synthesis failed",
                    segment_index=i + 1,
                    error=str(e),
                )
                raise

        # Step 3: Combine all segment summaries using hierarchical_synthesis_agent
        logger.info(
            "Starting final hierarchical synthesis",
            segment_summaries_count=len(segment_summaries),
        )

        # Combine all segment summaries
        combined_segments = "\n\n".join(
            [
                f"## Temporal Segment {i+1}\n{summary}"
                for i, summary in enumerate(segment_summaries)
            ]
        )

        try:
            result = await hierarchical_synthesis_agent.run(
                f"Create comprehensive meeting intelligence from these temporal segments:\n\n{combined_segments}"
            )

            logger.info(
                "Hierarchical synthesis completed",
                final_summary_length=len(result.output.summary),
                action_items_count=len(result.output.action_items),
            )

            return result.output
        except Exception as e:
            logger.error("Hierarchical synthesis failed", error=str(e))
            raise

    def _group_insights_by_time(
        self, insights_list: list[ChunkInsights], segment_minutes: int
    ) -> list[list[ChunkInsights]]:
        """Group insights into temporal segments."""
        if not insights_list:
            return []

        # For simplicity, group insights by chunk order since we don't have timestamps
        # In production, this would use actual meeting timestamps
        insights_per_segment = max(1, len(insights_list) // 3)  # Aim for ~3 segments

        segments = []
        for i in range(0, len(insights_list), insights_per_segment):
            segment = insights_list[i : i + insights_per_segment]
            if segment:  # Only add non-empty segments
                segments.append(segment)

        return segments

    def _format_insights_for_synthesis(self, insights_list: list[ChunkInsights]) -> str:
        """Format insights for synthesis prompts."""
        formatted_sections = []

        for i, insight in enumerate(insights_list, 1):
            section = f"""--- Insight Group {i} (Importance: {insight.importance}) ---
Themes: {', '.join(insight.themes)}

Key Insights:
"""
            for insight_text in insight.insights:
                section += f"• {insight_text}\n"

            if insight.actions:
                section += "\nAction Items:\n"
                for action in insight.actions:
                    section += f"• {action}\n"

            formatted_sections.append(section)

        return "\n\n".join(formatted_sections)
