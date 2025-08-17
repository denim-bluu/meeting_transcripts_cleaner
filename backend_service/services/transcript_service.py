"""Unified transcript service for VTT processing with concurrent processing and enterprise error handling."""

import asyncio
from collections.abc import Callable
import time

from asyncio_throttle.throttler import Throttler
import structlog

from backend_service.core.vtt_processor import VTTProcessor
from backend_service.models.agents import CleaningResult, ReviewResult
from backend_service.models.transcript import VTTChunk
from backend_service.services.orchestration import IntelligenceOrchestrator
from backend_service.services.transcript.cleaning_service import (
    TranscriptCleaningService,
)
from backend_service.services.transcript.review_service import TranscriptReviewService

logger = structlog.get_logger(__name__)


class TranscriptService:
    """Orchestrate the complete VTT processing pipeline with concurrent processing and rate limiting."""

    def __init__(self, api_key: str, max_concurrent: int = 10, rate_limit: int = 50):
        """
        Initialize service with API key and rate limiting controls.

        Args:
            api_key: OpenAI API key for AI processing
            max_concurrent: Maximum concurrent API calls (default: 10 for o3-mini stability)
            rate_limit: Maximum requests per minute (default: 300 for Tier 2-3 usage)
        """
        self.api_key = api_key
        self.client = None
        self.transcript_cleaner = None
        self.transcript_reviewer = None
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Initialize VTT processor
        self.processor = VTTProcessor()

        # Initialize throttler for rate limiting
        self.throttler = Throttler(rate_limit=rate_limit, period=60)

        # Initialize services using pure agents
        self.cleaner = TranscriptCleaningService(model="o3-mini")
        self.reviewer = TranscriptReviewService(model="o3-mini")
        self._intelligence_orchestrator = IntelligenceOrchestrator(model="o3-mini")

    def process_vtt(self, content: str) -> dict:
        """
        Parse and chunk VTT file.

        Returns:
        {
            "entries": List[VTTEntry],  # All 1308 entries
            "chunks": List[VTTChunk],   # ~40 chunks
            "speakers": List[str],      # Unique speakers
            "duration": float           # Total seconds
        }
        """
        start_time = time.time()
        logger.info(
            "Starting VTT document processing",
            content_size_bytes=len(content.encode("utf-8")),
            content_lines=content.count("\n"),
            content_preview=content[:200].replace("\n", " ") + "..."
            if len(content) > 200
            else content,
        )

        entries = self.processor.parse_vtt(content)
        chunks = self.processor.create_chunks(entries)

        speakers = list({e.speaker for e in entries})
        duration = max(e.end_time for e in entries) if entries else 0

        processing_time = time.time() - start_time

        # Calculate additional analytics
        total_text_length = sum(len(entry.text) for entry in entries)
        avg_text_per_entry = total_text_length / len(entries) if entries else 0

        logger.info(
            "VTT document processing completed",
            processing_time_ms=int(processing_time * 1000),
            total_entries=len(entries),
            total_chunks=len(chunks),
            unique_speakers=len(speakers),
            speakers=sorted(speakers),
            duration_seconds=round(duration, 2),
            total_text_chars=total_text_length,
            avg_text_per_entry=round(avg_text_per_entry, 1),
            entries_per_minute=round(len(entries) / (duration / 60), 1)
            if duration > 0
            else 0,
            avg_chunk_size=round(
                sum(chunk.token_count for chunk in chunks) / len(chunks), 1
            )
            if chunks
            else 0,
        )

        return {
            "entries": entries,
            "chunks": chunks,
            "speakers": sorted(speakers),
            "duration": duration,
        }

    async def _process_chunk_with_concurrency_control(
        self, chunk: VTTChunk, chunk_index: int, prev_text: str = ""
    ) -> tuple[CleaningResult, ReviewResult]:
        """Process a single chunk with concurrency control and rate limiting. Retries are handled by Pydantic AI agents."""
        async with self.semaphore, self.throttler:
            start_time = time.time()
            chunk_speakers = list({entry.speaker for entry in chunk.entries})

            logger.info(
                "Processing chunk with concurrency control",
                chunk_id=chunk.chunk_id,
                chunk_index=chunk_index,
                token_count=chunk.token_count,
                entries_count=len(chunk.entries),
                unique_speakers=len(chunk_speakers),
                speakers=chunk_speakers,
                has_previous_context=len(prev_text) > 0,
                semaphore_available=self.semaphore._value,
                throttler_active=True,
            )

            try:
                # Clean chunk
                clean_result = await self.cleaner.clean_chunk(chunk, prev_text)

                # Review cleaning
                review_result = await self.reviewer.review_chunk(
                    chunk, clean_result.cleaned_text
                )

                processing_time = time.time() - start_time
                logger.info(
                    "Chunk processed successfully",
                    chunk_id=chunk.chunk_id,
                    processing_time_ms=int(processing_time * 1000),
                    confidence=clean_result.confidence,
                    quality_score=review_result.quality_score,
                    accepted=review_result.accept,
                )

                return clean_result, review_result

            except Exception as e:
                logger.error(
                    "Chunk processing failed",
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk_index,
                    error=str(e),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
                raise

    async def clean_transcript(
        self,
        transcript: dict,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict:
        """
        Run concurrent AI cleaning and review on all chunks with enterprise-grade error handling.

        Args:
            transcript: Output from process_vtt()
            progress_callback: Called with (progress_pct, status_msg)

        Returns transcript with added cleaned and reviewed data.
        """
        chunks = transcript["chunks"]
        total_chunks = len(chunks)

        logger.info(
            "Starting concurrent transcript processing",
            total_chunks=total_chunks,
            total_speakers=len(transcript["speakers"]),
            duration_seconds=transcript["duration"],
        )

        # Handle edge case: no chunks to process
        if total_chunks == 0:
            logger.warning("No chunks to process - transcript parsing may have failed")
            transcript["cleaned_chunks"] = []
            transcript["review_results"] = []
            return transcript

        start_time = time.time()

        # Process chunks concurrently in batches to maintain context flow
        batch_size = min(10, total_chunks)  # Reduced for o3-mini stability
        cleaned_chunks: list[CleaningResult | None] = [
            None
        ] * total_chunks  # Pre-allocate for order preservation
        review_results: list[ReviewResult | None] = [None] * total_chunks

        # Track progress
        completed_chunks = 0

        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]
            current_batch = batch_start // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = completed_chunks / total_chunks
                # Calculate active requests more accurately
                active_requests = len(
                    batch_chunks
                )  # All chunks in current batch are active
                status = f"Batch {current_batch}/{total_batches} • {len(batch_chunks)} chunks • {active_requests} active • Concurrency: {batch_size}"
                progress_callback(progress, status)
            # Create tasks for concurrent processing
            tasks: list[
                tuple[int, asyncio.Task[tuple[CleaningResult, ReviewResult]]]
            ] = []

            for i, chunk in enumerate(batch_chunks):
                chunk_index: int = batch_start + i

                # Get previous chunk context (sequential for quality)
                prev_text: str = ""
                prev_chunk: CleaningResult | None = (
                    cleaned_chunks[chunk_index - 1] if chunk_index > 0 else None
                )
                if prev_chunk is not None:
                    prev_text = prev_chunk.cleaned_text[-200:]  # Last 200 chars

                # Explicitly create an asyncio.Task so we can add type hints
                task: asyncio.Task[tuple[CleaningResult, ReviewResult]] = (
                    asyncio.create_task(
                        self._process_chunk_with_concurrency_control(
                            chunk, chunk_index, prev_text
                        )
                    )
                )

                tasks.append((chunk_index, task))

            # Execute batch concurrently using asyncio.gather
            logger.debug(
                f"Executing batch {batch_start // batch_size + 1} with {len(tasks)} chunks"
            )

            # Extract just the tasks for concurrent execution
            task_list = [task for _, task in tasks]

            try:
                # Execute all tasks in this batch concurrently
                batch_results = await asyncio.gather(*task_list, return_exceptions=True)

                # Process results and handle any exceptions
                batch_completed_count = 0
                for i, (chunk_index, _) in enumerate(tasks):
                    result = batch_results[i]

                    if isinstance(result, Exception):
                        logger.error(
                            "Batch processing failed for chunk",
                            chunk_index=chunk_index,
                            error=str(result),
                        )

                        # Fallback to original text
                        cleaned_chunks[chunk_index] = CleaningResult(
                            cleaned_text=chunks[chunk_index].to_transcript_text(),
                            confidence=0.0,
                            changes_made=[f"Processing failed: {str(result)}"],
                        )
                        review_results[chunk_index] = ReviewResult(
                            quality_score=0.0,
                            issues=[f"Processing error: {str(result)}"],
                            accept=False,
                        )
                    else:
                        clean_result, review_result = result  # type: ignore
                        cleaned_chunks[chunk_index] = clean_result
                        review_results[chunk_index] = review_result

                    batch_completed_count += 1

                    # Update progress more frequently - after each chunk in the batch
                    if (
                        progress_callback and batch_completed_count % 1 == 0
                    ):  # Update after every chunk
                        current_total_completed = batch_start + batch_completed_count
                        progress = current_total_completed / total_chunks
                        active_remaining = len(batch_chunks) - batch_completed_count

                        elapsed_time = time.time() - start_time
                        chunks_per_sec = (
                            current_total_completed / elapsed_time
                            if elapsed_time > 0
                            else 0
                        )

                        status = f"Batch {current_batch}/{total_batches} • {batch_completed_count}/{len(batch_chunks)} done • {active_remaining} active • {chunks_per_sec:.1f}/sec"
                        progress_callback(progress, status)

            except Exception as e:
                logger.error(
                    "Batch execution failed",
                    batch_start=batch_start,
                    batch_end=batch_end,
                    error=str(e),
                )
                # Fallback for entire batch

                for chunk_index, _ in tasks:
                    cleaned_chunks[chunk_index] = CleaningResult(
                        cleaned_text=chunks[chunk_index].to_transcript_text(),
                        confidence=0.0,
                        changes_made=[f"Batch processing failed: {str(e)}"],
                    )
                    review_results[chunk_index] = ReviewResult(
                        quality_score=0.0,
                        issues=[f"Batch error: {str(e)}"],
                        accept=False,
                    )

            # Update progress after batch completion
            completed_chunks = batch_end
            if progress_callback:
                progress = completed_chunks / total_chunks
                elapsed_time = time.time() - start_time
                chunks_per_sec = (
                    completed_chunks / elapsed_time if elapsed_time > 0 else 0
                )
                remaining_chunks = total_chunks - completed_chunks
                eta = remaining_chunks / chunks_per_sec if chunks_per_sec > 0 else 0

                status = f"Completed batch {current_batch}/{total_batches} • {completed_chunks}/{total_chunks} chunks • {chunks_per_sec:.1f}/sec • ETA: {eta:.1f}s"
                progress_callback(progress, status)

        # Final progress update
        if progress_callback:
            progress_callback(1.0, "Finalizing results...")

        # Combine all cleaned text
        final_transcript = "\n\n".join(
            chunk.cleaned_text for chunk in cleaned_chunks if chunk
        )

        processing_time = time.time() - start_time

        # Log final statistics
        accepted_count = sum(1 for r in review_results if r and r.accept)
        avg_quality = (
            sum(r.quality_score for r in review_results if r) / len(review_results)
            if review_results
            else 0.0
        )

        logger.info(
            "Transcript processing completed",
            processing_time_seconds=round(processing_time, 2),
            chunks_per_second=round(total_chunks / processing_time, 2)
            if processing_time > 0
            else 0.0,
            accepted_chunks=accepted_count,
            acceptance_rate=f"{accepted_count / total_chunks * 100:.1f}%"
            if total_chunks > 0
            else "0.0%",
            average_quality_score=round(avg_quality, 3),
        )

        # Update transcript with results
        transcript["cleaned_chunks"] = cleaned_chunks
        transcript["review_results"] = review_results
        transcript["final_transcript"] = final_transcript
        transcript["processing_stats"] = {
            "processing_time_seconds": processing_time,
            "chunks_per_second": total_chunks / processing_time,
            "accepted_chunks": accepted_count,
            "average_quality_score": avg_quality,
        }

        return transcript

    def export(self, transcript: dict, format: str) -> str:
        """
        Export cleaned transcript in requested format.

        Formats:
        - "vtt": WEBVTT with cleaned text, preserving timestamps
        - "txt": Simple text with "Speaker: text" format
        - "json": Complete data structure

        For VTT: Reconstruct using original timestamps but cleaned text
        For TXT: Simple concatenation of cleaned chunks
        For JSON: Return full transcript dict as JSON string
        """
        if format == "vtt":
            # Reconstruct VTT with original or cleaned text
            lines = ["WEBVTT", ""]

            # Use original entries for now (cleaned mapping is complex)
            if "entries" in transcript:
                for entry in transcript["entries"]:
                    # Format VTT cue
                    start_str = self._format_timestamp(entry.start_time)
                    end_str = self._format_timestamp(entry.end_time)

                    lines.append(entry.cue_id)
                    lines.append(f"{start_str} --> {end_str}")
                    lines.append(f"<v {entry.speaker}>{entry.text}</v>")
                    lines.append("")

            return "\n".join(lines)

        elif format == "txt":
            # Use final transcript if available, otherwise create from chunks
            if "final_transcript" in transcript:
                return transcript["final_transcript"]
            elif "chunks" in transcript:
                return "\n\n".join(
                    chunk.to_transcript_text() for chunk in transcript["chunks"]
                )
            else:
                return ""

        elif format == "json":
            import json

            # Convert the transcript dict to JSON, handling Pydantic models
            serializable_transcript = {}
            for key, value in transcript.items():
                if hasattr(value, "model_dump"):
                    # Pydantic model
                    serializable_transcript[key] = value.model_dump()
                elif (
                    isinstance(value, list)
                    and value
                    and hasattr(value[0], "model_dump")
                ):
                    # List of Pydantic models
                    serializable_transcript[key] = [item.model_dump() for item in value]
                else:
                    serializable_transcript[key] = value
            return json.dumps(serializable_transcript, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as VTT timestamp (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    async def extract_intelligence(
        self, transcript: dict, detail_level: str = "comprehensive"
    ) -> dict:
        """
        Extract intelligence from cleaned transcript using industry-standard approach.
        Call after clean_transcript completes.

        Args:
            transcript: transcript dict with 'cleaned_chunks' or 'chunks' key
            detail_level: "standard", "comprehensive", "technical_focus", or "premium"

        Output: transcript dict with added 'intelligence' key
        """
        logger.info(
            "Starting intelligence extraction",
            chunks_available=len(transcript.get("chunks", [])),
            has_cleaned_chunks="cleaned_chunks" in transcript,
        )

        # Use cleaned chunks if available, otherwise use original chunks
        chunks_to_process = transcript.get("chunks", [])
        if not chunks_to_process:
            raise ValueError("No chunks available for intelligence extraction")

        result = await self._intelligence_orchestrator.process_meeting(
            chunks_to_process, detail_level=detail_level, progress_callback=None
        )
        transcript["intelligence"] = result

        logger.info(
            "Intelligence extraction completed",
            action_items_count=len(result.action_items),
            summary_length=len(result.summary),
            processing_time_ms=result.processing_stats.get("time_ms", 0),
        )

        return transcript
