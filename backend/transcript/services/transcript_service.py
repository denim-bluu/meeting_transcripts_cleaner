"""Unified transcript service for VTT processing with concurrent processing and enterprise error handling."""

import asyncio
from collections.abc import Callable
import time

from asyncio_throttle.throttler import Throttler
import structlog

from backend.config import settings
from backend.transcript.agents.cleaner import CLEANER_USER_PROMPT, cleaning_agent
from backend.transcript.agents.reviewer import REVIEWER_USER_PROMPT, review_agent
from backend.transcript.models import (
    CleaningResult,
    ReviewResult,
    TranscriptProcessingResult,
    VTTChunk,
    VTTProcessingResult,
)
from backend.transcript.services.vtt_processor import VTTProcessor

logger = structlog.get_logger(__name__)


class TranscriptService:
    """Orchestrate the complete VTT processing pipeline with concurrent processing and rate limiting."""

    def __init__(self, api_key: str):
        """
        Initialize service with API key and rate limiting controls.
        """

        self.api_key = api_key
        self.semaphore = asyncio.Semaphore(settings.max_concurrency)
        # Keep an explicit copy of the configured concurrency for worker sizing
        self.max_concurrent = settings.max_concurrency
        self.rate_limit = settings.rate_limit
        # Initialize VTT processor
        self.processor = VTTProcessor()

        # Initialize throttler for rate limiting
        self.throttler = Throttler(rate_limit=self.rate_limit, period=60)

    def process_vtt(self, content: str) -> VTTProcessingResult:
        """
        Parse and chunk VTT file.

        Returns:
        VTTProcessingResult
        """
        start_time = time.time()
        logger.info("Starting VTT document processing")

        entries = self.processor.parse_vtt(content)
        chunks = self.processor.create_chunks(entries)

        speakers: list[str] = list({e.speaker for e in entries})
        duration = max(e.end_time for e in entries) if entries else 0

        processing_time = time.time() - start_time

        logger.info(
            "VTT document processing completed",
            processing_time_ms=int(processing_time * 1000),
            total_entries=len(entries),
            total_chunks=len(chunks),
            unique_speakers=len(speakers),
            duration_seconds=round(duration, 2),
        )

        return VTTProcessingResult(
            entries=entries,
            chunks=chunks,
            speakers=sorted(speakers),
            duration=duration,
        )

    async def _process_chunk_with_concurrency_control(
        self, chunk: VTTChunk, chunk_index: int, prev_text: str = ""
    ) -> tuple[CleaningResult, ReviewResult]:
        """Process a single chunk with concurrency control and rate limiting."""
        async with self.semaphore, self.throttler:
            start_time = time.time()
            chunk_text = chunk.to_transcript_text()

            logger.info(
                "Processing chunk",
                chunk_id=chunk.chunk_id,
                chunk_index=chunk_index,
            )

            try:
                # Clean chunk
                context: str = prev_text[-200:] if prev_text else ""
                context_deps: dict[str, str] = {"prev_text": context}
                user_prompt = CLEANER_USER_PROMPT.format(
                    context=context, chunk_text=chunk_text
                )

                clean_result_response = await cleaning_agent.run(
                    user_prompt, deps=context_deps
                )
                clean_result = clean_result_response.output

                # Review cleaning
                review_prompt = REVIEWER_USER_PROMPT.format(
                    original_text=chunk_text, cleaned_text=clean_result.cleaned_text
                )

                review_result_response = await review_agent.run(review_prompt)
                review_result = review_result_response.output


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
        transcript: VTTProcessingResult,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> TranscriptProcessingResult:
        """
        Run concurrent AI cleaning and review on all chunks using a single in-process
        asyncio.Queue with bounded concurrency (Semaphore) and provider rate limiting.

        Args:
            transcript: Output from process_vtt()
            progress_callback: Called with (progress_pct, status_msg)

        Returns transcript with added cleaned and reviewed data.
        """
        chunks = transcript.chunks
        total_chunks = len(chunks)

        logger.info(
            "Starting concurrent transcript processing (single-queue)",
            total_chunks=total_chunks,
            total_speakers=len(transcript.speakers),
            duration_seconds=transcript.duration,
        )

        # Handle edge case: no chunks to process
        if total_chunks == 0:
            logger.warning("No chunks to process - transcript parsing may have failed")
            return TranscriptProcessingResult(
                transcript=transcript,
                cleaned_chunks=[],
                review_results=[],
            )

        start_time = time.time()

        # Pre-allocate for order preservation
        cleaned_chunks: list[CleaningResult | None] = [None] * total_chunks
        review_results: list[ReviewResult | None] = [None] * total_chunks

        # Worker sizing respects OpenAI concurrency controls via Semaphore
        worker_count = min(
            total_chunks, max(1, getattr(self, "max_concurrent", self.semaphore._value))
        )

        # Single in-process work queue
        queue: asyncio.Queue = asyncio.Queue()

        # In-process queue for optimal performance
        for idx, ch in enumerate(chunks):
            queue.put_nowait((idx, ch))

        # Progress tracking
        completed = 0
        progress_lock = asyncio.Lock()

        async def _maybe_call_progress(progress: float, message: str) -> None:
            """Call progress callback if provided, handling both sync and async."""
            if not progress_callback:
                return
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(progress, message)
            else:
                progress_callback(progress, message)

        await _maybe_call_progress(
            0.0,
            f"Queued {total_chunks} chunks • Workers: {worker_count} • Concurrency limit: {getattr(self, 'max_concurrent', self.semaphore._value)}",
        )

        async def worker(_id: int):
            nonlocal completed
            while True:
                item = await queue.get()
                try:
                    if item is None:
                        # Sentinel - acknowledge and exit
                        return

                    idx, ch = item
                    # Previous context: prefer cleaned previous if available, else raw previous text
                    prev_text = ""
                    if idx > 0:
                        prev_clean = cleaned_chunks[idx - 1]
                        if prev_clean:
                            prev_text = prev_clean.cleaned_text[-200:]
                        else:
                            prev_text = chunks[idx - 1].to_transcript_text()[-200:]

                    try:
                        (
                            clean_res,
                            review_res,
                        ) = await self._process_chunk_with_concurrency_control(
                            ch, idx, prev_text
                        )
                    except Exception as e:
                        logger.error(
                            "Chunk processing failed",
                            chunk_id=ch.chunk_id,
                            chunk_index=idx,
                            error=str(e),
                        )
                        # Fallback to original text on error
                        clean_res = CleaningResult(
                            cleaned_text=ch.to_transcript_text(),
                            confidence=0.0,
                            changes_made=[f"Processing failed: {str(e)}"],
                        )
                        review_res = ReviewResult(
                            quality_score=0.0,
                            issues=[f"Processing error: {str(e)}"],
                            accept=False,
                        )

                    cleaned_chunks[idx] = clean_res
                    review_results[idx] = review_res

                    # Update progress after each chunk
                    async with progress_lock:
                        completed += 1
                        progress = completed / total_chunks
                        elapsed_time = time.time() - start_time
                        chunks_per_sec = (
                            completed / elapsed_time if elapsed_time > 0 else 0
                        )
                        remaining_chunks = total_chunks - completed
                        eta = (
                            remaining_chunks / chunks_per_sec
                            if chunks_per_sec > 0
                            else 0
                        )
                        in_queue = max(
                            0, queue.qsize() - worker_count
                        )  # rough estimate of not-yet-picked items
                        status = (
                            f"Processing {completed}/{total_chunks} • in-queue: {in_queue} "
                            f"• concurrency: {worker_count} • {chunks_per_sec:.1f}/sec • ETA: {eta:.1f}s"
                        )
                        await _maybe_call_progress(progress, status)
                finally:
                    # Mark task (including sentinel) as done
                    queue.task_done()

        # Launch workers under structured concurrency
        workers = [asyncio.create_task(worker(i)) for i in range(worker_count)]

        # Wait for all tasks to be processed
        await queue.join()

        # Now signal workers to exit by pushing sentinels
        for _ in range(worker_count):
            queue.put_nowait(None)

        # Ensure workers exit after receiving sentinels
        await asyncio.gather(*workers, return_exceptions=False)

        # Final progress update
        await _maybe_call_progress(1.0, "Finalizing results...")

        # Combine all cleaned text
        final_transcript = "\n\n".join(
            chunk.cleaned_text for chunk in cleaned_chunks if chunk
        )

        logger.info(
            "Transcript processing completed",
            processing_time_seconds=round(time.time() - start_time, 2),
            total_chunks=total_chunks,
        )
        return TranscriptProcessingResult(
            transcript=transcript,
            cleaned_chunks=cleaned_chunks,
            review_results=review_results,
            final_transcript=final_transcript,
        )
