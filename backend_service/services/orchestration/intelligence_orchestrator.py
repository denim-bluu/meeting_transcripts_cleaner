"""Main intelligence orchestration - clean, simple pipeline."""

import time

import structlog

# Use pure agents following Pydantic AI best practices
from backend_service.agents.extraction.insights import chunk_extraction_agent
from backend_service.agents.synthesis.direct import direct_synthesis_agent
from backend_service.agents.synthesis.hierarchical import hierarchical_synthesis_agent
from backend_service.agents.synthesis.segment import segment_synthesis_agent
from backend_service.models.intelligence import ChunkInsights, MeetingIntelligence
from backend_service.models.transcript import VTTChunk
from backend_service.utils.semantic_chunker import SemanticChunker

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
        self, 
        cleaned_chunks: list[VTTChunk], 
        detail_level: str = "comprehensive",
        progress_callback=None
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
        if progress_callback:
            progress_callback(0.1, "Phase 1: Semantic chunking...")
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
        if progress_callback:
            progress_callback(0.2, f"Phase 2: Extracting insights from {len(semantic_chunks)} chunks...")
        logger.info(
            "Phase 2: Starting insight extraction",
            chunks_to_process=len(semantic_chunks),
        )
        phase2_start = time.time()
        insights_list = await self._extract_all_insights(semantic_chunks, detail_level, progress_callback)
        phase2_time = int((time.time() - phase2_start) * 1000)
        logger.info(
            "Phase 2 completed",
            insights_extracted=len(insights_list),
            time_ms=phase2_time,
        )

        # Phase 3: Smart synthesis (industry-standard approach)
        if progress_callback:
            progress_callback(0.8, "Phase 3: Synthesizing meeting intelligence...")
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
        self, semantic_chunks: list[str], detail_level: str = "comprehensive", progress_callback=None
    ) -> list[ChunkInsights]:
        """Extract insights from all semantic chunks using concurrent processing."""
        import asyncio
        
        async def extract_single_chunk(i: int, chunk_text: str) -> tuple[int, ChunkInsights]:
            """Extract insights from a single chunk with proper error handling."""
            # Create context for dynamic instructions
            context = {
                "position": "start"
                if i == 0
                else "end"
                if i == len(semantic_chunks) - 1
                else "middle",
                "chunk_index": i,
                "total_chunks": len(semantic_chunks),
                "detail_level": detail_level,  # Industry-standard detail level control
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

                logger.info(
                    "Chunk extraction completed",
                    chunk_index=i + 1,
                    importance=result.output.importance,
                    insights_count=len(result.output.insights),
                    themes=result.output.themes,
                    actions_count=len(result.output.actions),
                )
                
                return i, result.output

            except Exception as e:
                logger.error(
                    "Chunk extraction failed",
                    chunk_index=i + 1,
                    total_chunks=len(semantic_chunks),
                    error=str(e),
                    chunk_size_chars=len(chunk_text),
                )
                raise

        # Create concurrent tasks for all chunks
        logger.info(
            "Starting concurrent insight extraction",
            total_chunks=len(semantic_chunks),
            detail_level=detail_level,
        )
        
        tasks = [
            extract_single_chunk(i, chunk_text)
            for i, chunk_text in enumerate(semantic_chunks)
        ]

        # Execute all tasks concurrently with simple progress tracking
        if progress_callback:
            progress_callback(0.3, f"Processing {len(tasks)} chunks concurrently...")
        results: list[tuple[int, ChunkInsights] | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)
        if progress_callback:
            progress_callback(0.7, "Consolidating extraction results...")

        # Process results and handle exceptions
        insights_list: list[ChunkInsights | None] = [None] * len(semantic_chunks)  # Pre-allocate with correct order
        
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Concurrent chunk extraction failed", error=str(result))
                raise result
            else:
                # Type narrowing: result is tuple[int, ChunkInsights]
                chunk_index, insights = result
                insights_list[chunk_index] = insights

        # Ensure no None values (safety check)
        final_insights: list[ChunkInsights] = [insights for insights in insights_list if insights is not None]
        
        logger.info(
            "Concurrent insight extraction completed",
            chunks_processed=len(final_insights),
            total_chunks=len(semantic_chunks),
        )

        return final_insights

    async def _synthesize_direct(
        self, insights_list: list[ChunkInsights]
    ) -> MeetingIntelligence:
        """Direct synthesis using pure agent with detailed logging."""
        logger.info(
            "Starting direct synthesis", 
            insights_count=len(insights_list),
            total_actions=sum(len(insight.actions) for insight in insights_list),
            total_insights_items=sum(len(insight.insights) for insight in insights_list),
            avg_importance=round(sum(insight.importance for insight in insights_list) / len(insights_list), 2) if insights_list else 0
        )
        
        formatted_insights = self._format_insights_for_synthesis(insights_list)
        
        logger.info(
            "Formatted insights for synthesis",
            formatted_size_chars=len(formatted_insights),
            estimated_tokens=len(formatted_insights) // 4  # Rough token estimate
        )

        user_prompt = f"""Create comprehensive meeting intelligence from these insights:

{formatted_insights}

Return both summary (detailed markdown) and action_items (structured list)."""

        synthesis_start_time = time.time()
        
        try:
            logger.info(
                "Calling direct synthesis agent", 
                agent_retries=2,  # Built-in Pydantic AI retries
                model="o3-mini"
            )
            
            # Use capture_run_messages to log all interactions including retries
            from pydantic_ai import capture_run_messages
            
            with capture_run_messages() as run_messages:
                result = await direct_synthesis_agent.run(user_prompt)
            
            synthesis_time = int((time.time() - synthesis_start_time) * 1000)
            
            # Log detailed information about the run
            logger.info(
                "Direct synthesis run details",
                total_messages=len(run_messages),
                synthesis_time_ms=synthesis_time
            )
            
            # Simple message logging without accessing potentially undefined attributes
            if len(run_messages) > 2:  # More than expected messages suggests retries
                logger.info(
                    f"Multiple messages detected ({len(run_messages)})",
                    message_count=len(run_messages),
                    likely_retries=len(run_messages) > 2,
                    synthesis_time_ms=synthesis_time
                )
            
            logger.info(
                "Direct synthesis completed successfully",
                synthesis_time_ms=synthesis_time,
                summary_length=len(result.output.summary),
                action_items_count=len(result.output.action_items),
                has_processing_stats=bool(result.output.processing_stats),
                summary_sections=result.output.summary.count('#'),  # Count markdown headers
                summary_preview=result.output.summary[:200].replace('\n', ' ') + '...' if len(result.output.summary) > 200 else result.output.summary.replace('\n', ' ')
            )
            
            return result.output
        except Exception as e:
            synthesis_time = int((time.time() - synthesis_start_time) * 1000)
            logger.error(
                "Direct synthesis failed after retries",
                error=str(e),
                error_type=type(e).__name__,
                synthesis_time_ms=synthesis_time,
                formatted_insights_preview=formatted_insights[:300] + '...' if len(formatted_insights) > 300 else formatted_insights
            )
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

        # Step 2: Create segment summaries using concurrent segment_synthesis_agent
        async def synthesize_single_segment(i: int, segment_insights: list[ChunkInsights]) -> tuple[int, str]:
            """Synthesize a single segment with proper error handling."""
            logger.info(
                "Processing segment",
                segment_index=i + 1,
                insights_in_segment=len(segment_insights),
            )

            # Format insights for segment synthesis
            segment_text = self._format_insights_for_synthesis(segment_insights)

            try:
                from pydantic_ai import capture_run_messages
                
                with capture_run_messages() as segment_messages:
                    result = await segment_synthesis_agent.run(
                        f"Summarize this meeting segment:\n\n{segment_text}"
                    )

                logger.info(
                    "Segment synthesis completed",
                    segment_index=i + 1,
                    summary_length=len(result.output),
                    total_messages=len(segment_messages),
                    likely_retries=len(segment_messages) > 2
                )
                
                return i, result.output

            except Exception as e:
                logger.error(
                    "Segment synthesis failed",
                    segment_index=i + 1,
                    error=str(e),
                )
                raise

        # Create concurrent tasks for all segments
        logger.info(
            "Starting concurrent segment synthesis",
            segments_count=len(segments),
        )
        
        segment_tasks = [
            synthesize_single_segment(i, segment_insights)
            for i, segment_insights in enumerate(segments)
        ]

        # Execute all segment synthesis tasks concurrently
        import asyncio
        segment_results: list[tuple[int, str] | BaseException] = await asyncio.gather(*segment_tasks, return_exceptions=True)

        # Process segment results
        segment_summaries: list[str | None] = [None] * len(segments)
        
        for result in segment_results:
            if isinstance(result, BaseException):
                logger.error("Concurrent segment synthesis failed", error=str(result))
                raise result
            else:
                # Type narrowing: result is tuple[int, str]
                segment_index, summary = result
                segment_summaries[segment_index] = summary

        # Filter out None values
        final_summaries: list[str] = [summary for summary in segment_summaries if summary is not None]

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
            from pydantic_ai import capture_run_messages
            
            with capture_run_messages() as hierarchical_messages:
                result = await hierarchical_synthesis_agent.run(
                    f"Create comprehensive meeting intelligence from these temporal segments:\n\n{combined_segments}"
                )

            logger.info(
                "Hierarchical synthesis completed",
                final_summary_length=len(result.output.summary),
                action_items_count=len(result.output.action_items),
                total_messages=len(hierarchical_messages),
                likely_retries=len(hierarchical_messages) > 2
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
