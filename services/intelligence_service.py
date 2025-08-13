"""Intelligence extraction service orchestrating parallel processing pipeline."""

import asyncio
from collections.abc import Callable
import csv
from enum import Enum
import io
import time

import structlog

from core.intelligence_agents import (
    ActionItemExtractor,
    IntelligenceSynthesizer,
    SummaryExtractor,
)
from models.intelligence import IntelligenceResult
from models.vtt import VTTChunk

logger = structlog.get_logger(__name__)


class ReviewLevel(Enum):
    NONE = "none"
    LIGHT = "light"
    DETAILED = "detailed"


class IntelligenceService:
    """
    Orchestrates intelligence extraction pipeline.

    Responsibilities:
    - Create sliding context windows from chunks
    - Coordinate parallel extraction across chunks
    - Manage rate limiting and concurrency
    - Trigger selective review based on confidence
    - Export results in multiple formats

    Expected behavior:
    - Processes 40 chunks in <30 seconds
    - Respects 10 concurrent / 50 req/min limits
    - Enriches chunks with ±200 char context
    - Auto-reviews items with confidence <0.8
    - Handles partial failures gracefully
    """

    def __init__(self, api_key: str, max_concurrent: int = 10):
        self.api_key = api_key
        self.summary_extractor = SummaryExtractor(api_key)
        self.action_extractor = ActionItemExtractor(api_key)
        self.synthesizer = IntelligenceSynthesizer(api_key)
        self.semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(
            "IntelligenceService initialized",
            max_concurrent=max_concurrent,
        )

    def create_context_windows(self, chunks: list[VTTChunk]) -> list[dict]:
        """
        Enrich chunks with surrounding context.

        Creates sliding windows with 200 chars before/after each chunk.
        Preserves chunk boundaries while adding context for continuity.

        Input: List of VTTChunk objects
        Output: List of dicts with 'chunk_id', 'full_context', 'core_text', 'speakers'
        """
        start_time = time.time()
        windows = []

        for i, chunk in enumerate(chunks):
            context_before = chunks[i - 1].to_transcript_text()[-200:] if i > 0 else ""
            context_after = (
                chunks[i + 1].to_transcript_text()[:200] if i < len(chunks) - 1 else ""
            )

            core_text = chunk.to_transcript_text()
            full_context = context_before + core_text + context_after
            speakers = list({e.speaker for e in chunk.entries})

            windows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "full_context": full_context,
                    "core_text": core_text,
                    "speakers": speakers,
                }
            )

        processing_time = time.time() - start_time

        logger.info(
            "Context windows created",
            total_chunks=len(chunks),
            total_windows=len(windows),
            processing_time_ms=int(processing_time * 1000),
            avg_context_length=int(
                sum(len(w["full_context"]) for w in windows) / len(windows)
            )
            if windows
            else 0,
        )

        return windows

    async def extract_intelligence(
        self,
        cleaned_chunks: list[VTTChunk],
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> IntelligenceResult:
        """
        Main extraction pipeline.

        1. Creates context windows
        2. Extracts summaries and actions in parallel
        3. Synthesizes into final result
        4. Applies selective review if needed

        Input: List of cleaned VTTChunk objects
        Output: Complete IntelligenceResult
        Raises: Exception if synthesis fails
        """
        start_time = time.time()
        total_chunks = len(cleaned_chunks)

        logger.info(
            "Starting intelligence extraction",
            total_chunks=total_chunks,
        )

        if progress_callback:
            progress_callback(0.0, "Creating context windows...")

        # Phase 1: Create enriched windows
        windows = self.create_context_windows(cleaned_chunks)

        if progress_callback:
            progress_callback(0.1, "Starting parallel extraction...")

        # Phase 2: Parallel extraction phase
        extraction_tasks = []

        for i, window in enumerate(windows):

            async def extract_with_semaphore(w=window, idx=i):
                async with self.semaphore:
                    try:
                        result = await self._extract_from_window(w)
                        if (
                            progress_callback and (idx + 1) % 5 == 0
                        ):  # Update every 5 chunks
                            progress = 0.1 + 0.7 * (idx + 1) / total_chunks
                            progress_callback(
                                progress,
                                f"Processed {idx + 1}/{total_chunks} chunks...",
                            )
                        return result
                    except Exception as e:
                        logger.error(
                            "Window extraction failed",
                            chunk_id=w["chunk_id"],
                            error=str(e),
                        )
                        # Return empty results for failed extraction
                        return {
                            "summary": None,
                            "actions": [],
                            "chunk_id": w["chunk_id"],
                            "error": str(e),
                        }

            extraction_tasks.append(extract_with_semaphore())

        # Execute all extractions in parallel
        extractions = await asyncio.gather(*extraction_tasks, return_exceptions=True)

        # Filter out failed extractions and log them
        successful_extractions = []
        failed_count = 0

        for extraction in extractions:
            if isinstance(extraction, Exception):
                failed_count += 1
                logger.error("Extraction task failed", error=str(extraction))
            elif extraction.get("error"):
                failed_count += 1
                logger.error(
                    "Extraction failed for chunk",
                    chunk_id=extraction.get("chunk_id"),
                    error=extraction.get("error"),
                )
            elif extraction.get("summary") is not None:
                successful_extractions.append(extraction)

        if not successful_extractions:
            raise Exception("All chunk extractions failed")

        logger.info(
            "Extraction phase completed",
            successful_extractions=len(successful_extractions),
            failed_extractions=failed_count,
            success_rate=f"{len(successful_extractions)/total_chunks*100:.1f}%",
        )

        if progress_callback:
            progress_callback(0.8, "Synthesizing results...")

        # Phase 3: Synthesis phase
        result = await self.synthesizer.synthesize(successful_extractions)

        if progress_callback:
            progress_callback(0.9, "Applying selective review...")

        # Phase 4: Selective review
        review_level = self.determine_review_level(result)
        if review_level != ReviewLevel.NONE:
            result = await self._apply_review(result, review_level)

        # Add final processing stats
        total_processing_time = time.time() - start_time
        result.processing_stats.update(
            {
                "total_pipeline_time_ms": int(total_processing_time * 1000),
                "successful_chunks": len(successful_extractions),
                "failed_chunks": failed_count,
                "success_rate": len(successful_extractions) / total_chunks,
                "review_level": review_level.value,
            }
        )

        logger.info(
            "Intelligence extraction completed",
            total_time_ms=int(total_processing_time * 1000),
            final_confidence=result.confidence_score,
            review_level=review_level.value,
            action_items_count=len(result.action_items),
        )

        if progress_callback:
            progress_callback(1.0, "Intelligence extraction complete!")

        return result

    async def _extract_from_window(self, window: dict) -> dict:
        """Extract both summary and actions from single window."""
        summary, actions = await asyncio.gather(
            self.summary_extractor.extract(window),
            self.action_extractor.extract(window),
        )
        return {"summary": summary, "actions": actions, "chunk_id": window["chunk_id"]}

    def determine_review_level(self, result: IntelligenceResult) -> ReviewLevel:
        """
        Determine review requirements based on confidence and content.

        Rules:
        - Critical content (financial/legal) → DETAILED
        - Confidence >0.9 → NONE
        - Confidence 0.7-0.9 → LIGHT
        - Confidence <0.7 → DETAILED
        """
        if self._contains_critical_content(result):
            logger.info("Critical content detected, requiring detailed review")
            return ReviewLevel.DETAILED

        if result.confidence_score > 0.9:
            return ReviewLevel.NONE
        elif result.confidence_score > 0.7:
            return ReviewLevel.LIGHT
        else:
            return ReviewLevel.DETAILED

    def _contains_critical_content(self, result: IntelligenceResult) -> bool:
        """Check for financial, legal, or strategic content."""
        critical_keywords = [
            "budget",
            "legal",
            "contract",
            "strategic",
            "million",
            "lawsuit",
            "compliance",
            "regulation",
            "acquisition",
            "merger",
            "investment",
            "revenue",
            "profit",
            "loss",
            "audit",
            "risk",
            "liability",
        ]

        # Check both summaries and action items
        text_to_check = (
            result.executive_summary
            + " "
            + result.detailed_summary
            + " "
            + " ".join(item.description for item in result.action_items)
        )

        return any(keyword in text_to_check.lower() for keyword in critical_keywords)

    async def _apply_review(
        self, result: IntelligenceResult, review_level: ReviewLevel
    ) -> IntelligenceResult:
        """
        Apply selective review based on review level.
        For now, this is a placeholder that logs the review requirement.
        In a full implementation, this would trigger human review workflows.
        """
        logger.info(
            "Review required",
            review_level=review_level.value,
            confidence=result.confidence_score,
            action_items_needing_review=sum(
                1 for item in result.action_items if item.needs_review
            ),
        )

        # Mark result as reviewed (placeholder)
        result.processing_stats["review_applied"] = review_level.value
        result.processing_stats["review_timestamp"] = time.time()

        return result

    def export_json(self, result: IntelligenceResult) -> str:
        """Export as JSON string."""
        return result.model_dump_json(indent=2)

    def export_markdown(self, result: IntelligenceResult) -> str:
        """Export as formatted Markdown."""
        lines = []

        # Header
        lines.append("# Meeting Intelligence Report")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append(result.executive_summary)
        lines.append("")

        # Key Points
        lines.append("## Key Takeaways")
        for point in result.bullet_points:
            lines.append(f"- {point}")
        lines.append("")

        # Action Items
        lines.append("## Action Items")
        if result.action_items:
            for i, item in enumerate(result.action_items, 1):
                status = "🔴" if item.needs_review else "✅"
                owner_text = f" (@{item.owner})" if item.owner else ""
                deadline_text = f" - Due: {item.deadline}" if item.deadline else ""

                lines.append(
                    f"{i}. {status} {item.description}{owner_text}{deadline_text}"
                )
                if item.dependencies:
                    lines.append(f"   - Dependencies: {', '.join(item.dependencies)}")
                lines.append(f"   - Confidence: {item.confidence:.2f}")
                lines.append("")
        else:
            lines.append("No action items identified.")
            lines.append("")

        # Key Decisions
        if result.key_decisions:
            lines.append("## Key Decisions")
            for decision in result.key_decisions:
                if isinstance(decision, dict):
                    decision_text = decision.get("description", str(decision))
                else:
                    decision_text = str(decision)
                lines.append(f"- {decision_text}")
            lines.append("")

        # Topics Discussed
        lines.append("## Topics Discussed")
        for topic in result.topics_discussed:
            lines.append(f"- {topic}")
        lines.append("")

        # Detailed Summary
        lines.append("## Detailed Summary")
        lines.append(result.detailed_summary)
        lines.append("")

        # Metadata
        lines.append("## Processing Information")
        lines.append(f"- Overall Confidence: {result.confidence_score:.2f}")
        if result.processing_stats:
            lines.append(
                f"- Processing Time: {result.processing_stats.get('total_pipeline_time_ms', 0)} ms"
            )
            lines.append(
                f"- Chunks Processed: {result.processing_stats.get('successful_chunks', 0)}"
            )
            lines.append(
                f"- Success Rate: {result.processing_stats.get('success_rate', 0):.1%}"
            )

        return "\n".join(lines)

    def export_csv(self, result: IntelligenceResult) -> str:
        """Export action items as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "Description",
                "Owner",
                "Deadline",
                "Dependencies",
                "Confidence",
                "Is Critical",
                "Needs Review",
                "Source Chunks",
            ]
        )

        # Write action items
        for item in result.action_items:
            writer.writerow(
                [
                    item.description,
                    item.owner or "",
                    item.deadline or "",
                    "; ".join(item.dependencies) if item.dependencies else "",
                    f"{item.confidence:.2f}",
                    "Yes" if item.is_critical else "No",
                    "Yes" if item.needs_review else "No",
                    "; ".join(map(str, item.source_chunks)),
                ]
            )

        return output.getvalue()
