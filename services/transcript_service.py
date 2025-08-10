"""
Transcript Service - Core business logic for transcript processing.

This service encapsulates all AI processing logic, separating it from the UI layer
for better maintainability, testability, and reusability.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
import time
from typing import Any, Literal

from asyncio_throttle.throttler import Throttler
import structlog

from core.cleaning_agent import CleaningAgent
from core.confidence_categorizer import ConfidenceCategorizer
from core.document_processor import DocumentProcessor
from core.review_agent import ReviewAgent
from models.schemas import (
    DocumentSegment,
    ProcessingStatusEnum,
    SegmentCategory,
    SegmentCategoryEnum,
    TranscriptDocument,
)
from utils.diff_viewer import DiffViewer
from utils.document_diff_viewer import DocumentDiffViewer

logger = structlog.get_logger(__name__)


class TranscriptService:
    """Service class for transcript processing operations."""

    def __init__(self):
        """Initialize the service with AI agents."""
        self.cleaning_agent = CleaningAgent()
        self.review_agent = ReviewAgent()
        self.categorizer = ConfidenceCategorizer()
        self.document_processor = DocumentProcessor()
        self.diff_viewer = DiffViewer()
        self.document_diff_viewer = DocumentDiffViewer()
        self.throttler = Throttler(rate_limit=5, period=1.0)  # 5 requests per second

    def process_document(
        self, filename: str, content: str, file_size: int, content_type: str
    ) -> TranscriptDocument:
        """Process uploaded file into document segments.

        Args:
            filename: Name of the uploaded file
            content: Content of the file
            file_size: Size of the file in bytes
            content_type: MIME type of the file

        Returns:
            TranscriptDocument with segments ready for AI processing
        """
        # Handle VTT files specially
        if filename.endswith(".vtt"):
            content = self.document_processor.parse_vtt_content(content)
            self.document_processor._vtt_mode = True

        # Process document into segments
        try:
            return self.document_processor.process_document(
                filename, content, file_size, content_type
            )
        finally:
            self.document_processor._vtt_mode = False

    async def process_transcript(
        self,
        document: TranscriptDocument,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> None:
        """
        Run the complete dual-agent processing pipeline.

        Args:
            document: The transcript document to process
            progress_callback: Optional callback for progress updates (progress, status)
        """
        logger.info(
            "Starting AI processing pipeline",
            # Key identifiers (flat)
            document_id=document.id,
            phase="pipeline_start",
            # Processing context (grouped)
            processing={"total_segments": len(document.segments), "total_tokens": document.total_tokens}
        )

        total_segments = len(document.segments)

        try:
            # Phase 1: Cleaning
            await self._clean_segments_parallel(document, progress_callback, total_segments)

            # Phase 2: Review
            await self._review_segments_parallel(document, progress_callback, total_segments)

            # Phase 3: Categorization
            await self._categorize_segments(document, progress_callback)

            # Update final status
            if document.processing_status:
                document.processing_status.status = ProcessingStatusEnum.COMPLETED
                document.processing_status.completed_at = datetime.now(UTC)

            if progress_callback:
                progress_callback(1.0, "Complete")

            logger.info(
                "Processing completed successfully",
                # Key identifier (flat)
                phase="pipeline_complete",
                document_id=document.id,
                # Processing results (grouped)
                processing={"total_segments": total_segments}
            )

        except Exception as e:
            logger.error(
                "Processing pipeline failed",
                document_id=document.id,
                phase="pipeline_error",
                error=str(e),
                exc_info=True
            )
            if document.processing_status:
                document.processing_status.status = ProcessingStatusEnum.FAILED
            raise


    async def _clean_segments_parallel(
        self,
        document: TranscriptDocument,
        progress_callback: Callable[[float, str], None] | None,
        total_segments: int,
    ) -> None:
        """Process segments concurrently with max 5 simultaneous API calls."""
        if progress_callback:
            progress_callback(0.0, "Cleaning segments...")

        # Track progress with thread-safe counter
        completed_count = 0
        start_time = time.time()

        async def update_progress():
            """Update progress callback with current state."""
            nonlocal completed_count
            if progress_callback:
                progress = completed_count / (
                    total_segments * 2
                )  # Cleaning is first half
                elapsed = time.time() - start_time
                rate = completed_count / elapsed if elapsed > 0 else 0
                eta_remaining = (
                    (total_segments - completed_count) / rate if rate > 0 else 0
                )
                progress_callback(
                    progress,
                    f"Cleaning {completed_count}/{total_segments} segments (ETA: {eta_remaining:.1f}s)",
                )

        async def clean_single_segment(segment: DocumentSegment, index: int):
            """Clean a single segment with context."""
            nonlocal completed_count

            try:
                logger.debug(
                    "Cleaning segment",
                    segment_id=segment.id,
                    segment_index=index + 1,
                    total_segments=total_segments,
                    phase="cleaning"
                )

                # Prepare context for better cleaning
                context = {}
                if index > 0:
                    prev_content = document.segments[index - 1].content
                    context["previous"] = (
                        prev_content[-100:] if len(prev_content) > 100 else prev_content
                    )
                if index < len(document.segments) - 1:
                    next_content = document.segments[index + 1].content
                    context["following"] = (
                        next_content[:100] if len(next_content) > 100 else next_content
                    )

                # AI CALL - CleaningAgent.clean_segment()
                cleaning_result = await self.cleaning_agent.clean_segment(
                    segment, context
                )
                document.cleaning_results[segment.id] = cleaning_result

                logger.debug(
                    "Segment cleaned successfully",
                    segment_id=segment.id,
                    phase="cleaning_complete"
                )

                # Thread-safe progress update
                completed_count += 1
                await update_progress()

            except Exception as e:
                logger.error(
                    "Error cleaning segment",
                    segment_id=segment.id,
                    phase="cleaning_error",
                    error=str(e),
                    exc_info=True
                )
                completed_count += 1  # Still count as completed to maintain progress
                await update_progress()

        async def throttled_clean_segment(segment: DocumentSegment, index: int):
            """Clean segment with throttled rate limiting."""
            async with self.throttler:
                await clean_single_segment(segment, index)

        # Execute all cleaning tasks concurrently with throttling
        tasks = [
            throttled_clean_segment(segment, i) for i, segment in enumerate(document.segments)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        duration = time.time() - start_time
        logger.info(
            "Completed cleaning phase",
            total_segments=total_segments,
            duration_seconds=duration,
            phase="cleaning_phase_complete"
        )


    async def _review_segments_parallel(
        self,
        document: TranscriptDocument,
        progress_callback: Callable[[float, str], None] | None,
        total_segments: int,
    ) -> None:
        """Review segments concurrently with max 5 simultaneous API calls."""
        if progress_callback:
            progress_callback(0.5, "Reviewing cleaned segments...")

        logger.info(
            "Starting parallel review phase",
            total_segments=total_segments,
            phase="review_phase_start"
        )

        # Track progress with thread-safe counter
        completed_count = 0
        start_time = time.time()

        async def update_progress():
            """Update progress callback with current state."""
            nonlocal completed_count
            if progress_callback:
                progress = 0.5 + (
                    completed_count / (total_segments * 2)
                )  # Review is second half
                elapsed = time.time() - start_time
                rate = completed_count / elapsed if elapsed > 0 else 0
                eta_remaining = (
                    (total_segments - completed_count) / rate if rate > 0 else 0
                )
                progress_callback(
                    progress,
                    f"Reviewing {completed_count}/{total_segments} segments (ETA: {eta_remaining:.1f}s)",
                )

        async def review_single_segment(segment: DocumentSegment, index: int):
            """Review a single segment with context."""
            nonlocal completed_count

            if segment.id not in document.cleaning_results:
                completed_count += 1
                await update_progress()
                return

            try:
                logger.debug(
                    f"Reviewing segment {index+1}/{total_segments} (ID: {segment.id})"
                )

                # Prepare context for better review
                context = {}
                if index > 0:
                    prev_content = document.segments[index - 1].content
                    context["previous"] = prev_content[-50:]
                if index < len(document.segments) - 1:
                    next_content = document.segments[index + 1].content
                    context["following"] = next_content[:50]

                # AI CALL - ReviewAgent.review_cleaning()
                decision = await self.review_agent.review_cleaning(
                    segment, document.cleaning_results[segment.id], context
                )
                document.review_decisions[segment.id] = decision

                logger.debug("Segment reviewed successfully", segment_id=segment.id, phase="review")

                # Thread-safe progress update
                completed_count += 1
                await update_progress()

            except Exception as e:
                logger.error(
                    f"Error reviewing segment {segment.id}: {e}", exc_info=True
                )
                completed_count += 1  # Still count as completed to maintain progress
                await update_progress()

        async def throttled_review_segment(segment: DocumentSegment, index: int):
            """Review segment with throttled rate limiting."""
            async with self.throttler:
                await review_single_segment(segment, index)

        # Execute all review tasks concurrently with throttling
        tasks = [
            throttled_review_segment(segment, i)
            for i, segment in enumerate(document.segments)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            f"Phase 2 complete: Reviewed {len(document.review_decisions)} segments in {time.time() - start_time:.2f}s"
        )

    async def _categorize_segments(
        self,
        document: TranscriptDocument,
        progress_callback: Callable[[float, str], None] | None,
    ) -> None:
        """Categorize segments based on cleaning results and review decisions."""
        if progress_callback:
            progress_callback(0.9, "Categorizing segments...")

        categories = []

        # Categorize each segment based on cleaning results
        for segment in document.segments:
            cleaning_result = document.cleaning_results.get(segment.id)
            review_decision = document.review_decisions.get(segment.id)

            if cleaning_result:
                # Use the available categorize_cleaning_result method
                category = self.categorizer.categorize_cleaning_result(cleaning_result)

                # Adjust category based on review decision if available
                if review_decision:
                    # If review confidence is available, use it to potentially override category
                    review_confidence = review_decision.confidence

                    # Apply review decision confidence to override base category
                    if review_confidence >= 0.95:
                        category.category = SegmentCategoryEnum.AUTO_ACCEPT
                        category.confidence = review_confidence
                        category.categorization_reason = f"Review confidence ({review_confidence:.3f}) suggests auto-accept"
                    elif review_confidence >= 0.85:
                        category.category = SegmentCategoryEnum.QUICK_REVIEW
                        category.confidence = review_confidence
                        category.categorization_reason = f"Review confidence ({review_confidence:.3f}) suggests quick review"
                    elif review_confidence >= 0.70:
                        category.category = SegmentCategoryEnum.DETAILED_REVIEW
                        category.confidence = review_confidence
                        category.categorization_reason = f"Review confidence ({review_confidence:.3f}) suggests detailed review"
                    else:
                        category.category = SegmentCategoryEnum.AI_FLAGGED
                        category.confidence = review_confidence
                        category.categorization_reason = f"Review confidence ({review_confidence:.3f}) flagged for attention"

                    # Update review requirement
                    category.requires_human_review = (
                        category.category != SegmentCategoryEnum.AUTO_ACCEPT
                    )

                categories.append(category)

        if categories:
            logger.info(
                f"Phase 3: Categorized {len(categories)} segments based on cleaning results and review decisions"
            )

            # Store categories by segment_id
            categories_dict = {cat.segment_id: cat for cat in categories}
            document.segment_categories = categories_dict

            # Update processing status counts
            if document.processing_status:
                document.processing_status.processed_segments = len(
                    document.cleaning_results
                )

                # Reset counts
                document.processing_status.auto_accept_count = 0
                document.processing_status.quick_review_count = 0
                document.processing_status.detailed_review_count = 0
                document.processing_status.ai_flagged_count = 0

                # Update category counts based on REAL results
                for category in categories:
                    if category.category == SegmentCategoryEnum.AUTO_ACCEPT:
                        document.processing_status.auto_accept_count += 1
                    elif category.category == SegmentCategoryEnum.QUICK_REVIEW:
                        document.processing_status.quick_review_count += 1
                    elif category.category == SegmentCategoryEnum.DETAILED_REVIEW:
                        document.processing_status.detailed_review_count += 1
                    elif category.category == SegmentCategoryEnum.AI_FLAGGED:
                        document.processing_status.ai_flagged_count += 1

                logger.info(
                    f"Phase 3 complete: Categorized {len(categories)} segments - "
                    f"auto_accept: {document.processing_status.auto_accept_count}, "
                    f"quick_review: {document.processing_status.quick_review_count}, "
                    f"detailed_review: {document.processing_status.detailed_review_count}, "
                    f"ai_flagged: {document.processing_status.ai_flagged_count}"
                )

    def export_transcript(
        self,
        document: TranscriptDocument,
        user_decisions: dict[str, Any] | None = None,
    ) -> str:
        """
        Export the final cleaned transcript incorporating user decisions.

        Args:
            document: The processed transcript document
            user_decisions: Optional user overrides for specific segments

        Returns:
            The final cleaned transcript text
        """
        if not document:
            raise ValueError("No document provided for export")

        try:
            # Generate final content using backend logic
            final_content = document.final_cleaned_content

            # Apply user overrides if provided
            if user_decisions:
                final_parts = []

                for segment in sorted(
                    document.segments, key=lambda s: s.sequence_number
                ):
                    if segment.id in user_decisions:
                        # Use user decision
                        user_decision = user_decisions[segment.id]
                        if user_decision["decision"] in ["accept", "edit"]:
                            final_parts.append(user_decision["final_text"])
                        else:  # reject
                            final_parts.append(segment.content)  # Keep original
                    else:
                        # Use backend decision (already in final_cleaned_content logic)
                        review_decision = document.review_decisions.get(segment.id)
                        cleaning_result = document.cleaning_results.get(segment.id)

                        if (
                            review_decision
                            and review_decision.decision == "accept"
                            and cleaning_result
                        ):
                            final_parts.append(cleaning_result.cleaned_text)
                        elif review_decision and review_decision.decision == "modify":
                            final_parts.append(
                                review_decision.suggested_corrections or segment.content
                            )
                        else:
                            final_parts.append(segment.content)

                final_content = " ".join(final_parts)

            return final_content

        except Exception as e:
            logger.error("Export failed", error=str(e), exc_info=True, phase="export")
            raise

    def get_category_stats(self, categories: list[SegmentCategory]) -> dict[str, int]:
        """Calculate statistics for segment categories.

        Args:
            categories: List of segment categories from processing

        Returns:
            Dict with counts for: auto_accept, quick_review, detailed_review,
            ai_flagged, needs_review
        """
        stats = {
            "auto_accept": 0,
            "quick_review": 0,
            "detailed_review": 0,
            "ai_flagged": 0,
            "needs_review": 0,
        }

        for category in categories:
            if category.category == SegmentCategoryEnum.AUTO_ACCEPT:
                stats["auto_accept"] += 1
            elif category.category == SegmentCategoryEnum.QUICK_REVIEW:
                stats["quick_review"] += 1
                stats["needs_review"] += 1
            elif category.category == SegmentCategoryEnum.DETAILED_REVIEW:
                stats["detailed_review"] += 1
                stats["needs_review"] += 1
            elif category.category == SegmentCategoryEnum.AI_FLAGGED:
                stats["ai_flagged"] += 1
                stats["needs_review"] += 1

        return stats

    def filter_segments(
        self,
        segments: list[DocumentSegment],
        categories: list[SegmentCategory],
        filter_type: str,
    ) -> list[DocumentSegment]:
        """Filter segments by category type.

        Args:
            segments: List of document segments to filter
            categories: List of segment categories
            filter_type: "all", "needs_review", "high_confidence", "ai_flagged"

        Returns:
            Filtered list of segments
        """
        if filter_type == "all":
            return segments

        # Create category lookup
        category_dict = {cat.segment_id: cat for cat in categories}
        filtered = []

        for segment in segments:
            category = category_dict.get(segment.id)
            if not category:
                continue

            if filter_type == "needs_review":
                if category.category in [
                    SegmentCategoryEnum.QUICK_REVIEW,
                    SegmentCategoryEnum.DETAILED_REVIEW,
                    SegmentCategoryEnum.AI_FLAGGED,
                ]:
                    filtered.append(segment)
            elif filter_type == "high_confidence":
                if category.category == SegmentCategoryEnum.AUTO_ACCEPT:
                    filtered.append(segment)
            elif filter_type == "ai_flagged":
                if category.category == SegmentCategoryEnum.AI_FLAGGED:
                    filtered.append(segment)

        return filtered

    @staticmethod
    def _generate_cached_diff(
        original: str, cleaned: str, show_line_numbers: bool
    ) -> str:
        """Generate diff view (caching removed for threading compatibility)."""
        diff_viewer = DiffViewer()
        try:
            # Only support side_by_side mode now
            diff_lines = diff_viewer.generate_side_by_side_diff(original, cleaned)
            return diff_viewer.format_side_by_side_html(diff_lines, show_line_numbers)
        except Exception as e:
            logger.error("Error generating diff", error=str(e), exc_info=True, phase="diff_generation")
            return f"<p>Error generating diff: {str(e)}</p>"

    def generate_segment_diff(
        self,
        original: str,
        cleaned: str,
        show_line_numbers: bool = True,
    ) -> str:
        """Generate HTML diff view for a segment.

        Args:
            original: Original transcript text
            cleaned: Cleaned transcript text
            show_line_numbers: Whether to show line numbers

        Returns:
            HTML string ready for st.markdown(unsafe_allow_html=True)
        """
        # Generate diff view directly
        return self._generate_cached_diff(original, cleaned, show_line_numbers)

    def get_segment_changes_summary(
        self, original: str, cleaned: str
    ) -> dict[str, int | float]:
        """Calculate change statistics for a segment.

        Args:
            original: Original transcript text
            cleaned: Cleaned transcript text

        Returns:
            Dict with: lines_added, lines_removed, lines_changed, similarity_ratio
        """
        try:
            return self.diff_viewer.calculate_change_stats(original, cleaned)
        except Exception as e:
            logger.error("Error calculating change stats", error=str(e), exc_info=True, phase="change_stats")
            return {
                "lines_added": 0,
                "lines_removed": 0,
                "lines_changed": 0,
                "similarity_ratio": 1.0,
            }

    def generate_document_diff(
        self,
        document: TranscriptDocument,
        view_mode: Literal["inline", "side_by_side"] = "side_by_side",
    ) -> str:
        """Generate full document diff view.

        Args:
            document: Processed transcript document
            show_line_numbers: Whether to show line numbers
            view_mode: Type of diff view - "inline" or "side_by_side"

        Returns:
            HTML string ready for st.markdown(unsafe_allow_html=True)
        """
        try:
            return self.document_diff_viewer.generate_document_diff(
                document.segments,
                document.cleaning_results,
                document.review_decisions,
                view_mode,
            )
        except Exception as e:
            logger.error("Error generating document diff", error=str(e), exc_info=True, phase="document_diff")
            return f"<p>Error generating document diff: {str(e)}</p>"

    def get_document_change_summary(
        self, document: TranscriptDocument
    ) -> dict[str, Any]:
        """Get document-level change statistics and summary.

        Args:
            document: Processed transcript document

        Returns:
            Dict with change statistics, types, confidence scores, etc.
        """
        try:
            return self.document_diff_viewer.get_change_summary(
                document.segments, document.cleaning_results, document.review_decisions
            )
        except Exception as e:
            logger.error("Error getting document change summary", error=str(e), exc_info=True, phase="change_summary")
            return {
                "total_changes": 0,
                "segments_modified": 0,
                "change_types": {},
                "confidence_stats": {"high": 0, "medium": 0, "low": 0},
                "change_density": 0.0,
                "avg_confidence": 0.0,
            }

    def get_change_navigation(
        self, document: TranscriptDocument
    ) -> list[dict[str, str]]:
        """Generate navigation list for jumping between changes.

        Args:
            document: Processed transcript document

        Returns:
            List of navigation items for significant changes
        """
        try:
            return self.document_diff_viewer.get_change_navigation(
                document.segments, document.cleaning_results
            )
        except Exception as e:
            logger.error("Error generating change navigation", error=str(e), exc_info=True, phase="change_navigation")
            return []
