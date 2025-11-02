"""Unified transcript service for VTT processing with concurrent processing and enterprise error handling."""

import asyncio
from collections.abc import Callable
import time

from asyncio_throttle.throttler import Throttler
import structlog

from backend.config import settings
from backend.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
from backend.transcript.agents.cleaner import cleaning_agent
from backend.transcript.agents.reviewer import review_agent
from backend.transcript.models import CleaningResult, ReviewResult, VTTChunk
from backend.transcript.services.vtt_processor import VTTProcessor

logger = structlog.get_logger(__name__)


class TranscriptService:
    """Orchestrate the complete VTT processing pipeline with concurrent processing and rate limiting."""

    def __init__(
        self,
        api_key: str,
        max_concurrent: int | None = None,
        rate_limit: int | None = None,
        intelligence_max_concurrency: int | None = None,
    ):
        """
        Initialize service with API key and rate limiting controls.

        Args:
            api_key: OpenAI API key for AI processing
            max_concurrent: Maximum concurrent API calls (defaults to settings.transcript_max_concurrency)
            rate_limit: Maximum requests per minute (defaults to settings.transcript_rate_limit_per_minute)
            intelligence_max_concurrency: Concurrency for intelligence stage (defaults to settings.intelligence_max_concurrency)
        """
        if max_concurrent is None:
            max_concurrent = settings.transcript_max_concurrency
        if rate_limit is None:
            rate_limit = settings.transcript_rate_limit_per_minute
        if intelligence_max_concurrency is None:
            intelligence_max_concurrency = settings.intelligence_max_concurrency

        self.api_key = api_key
        self.client = None
        self.transcript_cleaner = None
        self.transcript_reviewer = None
        self.semaphore = asyncio.Semaphore(max_concurrent)
        # Keep an explicit copy of the configured concurrency for worker sizing
        self.max_concurrent = max_concurrent
        self.rate_limit = rate_limit

        # Initialize VTT processor
        self.processor = VTTProcessor()

        # Initialize throttler for rate limiting
        self.throttler = Throttler(rate_limit=rate_limit, period=60)

        # Initialize intelligence orchestrator
        self._intelligence_orchestrator = IntelligenceOrchestrator(
            chunk_max_concurrency=intelligence_max_concurrency
        )

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
        """Process a single chunk with concurrency control and rate limiting."""
        async with self.semaphore, self.throttler:
            start_time = time.time()
            chunk_speakers = list({entry.speaker for entry in chunk.entries})
            chunk_text = chunk.to_transcript_text()

            logger.info(
                "Processing chunk",
                chunk_id=chunk.chunk_id,
                chunk_index=chunk_index,
                token_count=chunk.token_count,
                entries_count=len(chunk.entries),
                unique_speakers=len(chunk_speakers),
                speakers=chunk_speakers,
                has_previous_context=len(prev_text) > 0,
            )

            try:
                # Clean chunk
                context = prev_text[-200:] if prev_text else ""
                context_deps = {"prev_text": context}
                user_prompt = f"""Previous context for flow: ...{context}

Current chunk to clean:
{chunk_text}

Return JSON with cleaned_text, confidence, and changes_made."""

                clean_result_response = await cleaning_agent.run(
                    user_prompt, deps=context_deps
                )
                clean_result = clean_result_response.output

                # Review cleaning
                review_prompt = f"""Original transcript:
{chunk_text}

Cleaned version:
{clean_result.cleaned_text}

Evaluate the cleaning quality and return JSON with quality_score, issues, and accept."""

                review_result_response = await review_agent.run(review_prompt)
                review_result = review_result_response.output

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
        Run concurrent AI cleaning and review on all chunks using a single in-process
        asyncio.Queue with bounded concurrency (Semaphore) and provider rate limiting.

        Args:
            transcript: Output from process_vtt()
            progress_callback: Called with (progress_pct, status_msg)

        Returns transcript with added cleaned and reviewed data.
        """
        chunks = transcript["chunks"]
        total_chunks = len(chunks)

        logger.info(
            "Starting concurrent transcript processing (single-queue)",
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

        if progress_callback:
            progress_callback(
                0.0,
                f"Queued {total_chunks} chunks • Workers: {worker_count} • Concurrency limit: {getattr(self, 'max_concurrent', self.semaphore._value)}",
            )

        async def worker(worker_id: int):
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
                        if progress_callback:
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
                            progress_callback(progress, status)
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
            "chunks_per_second": (total_chunks / processing_time)
            if processing_time > 0
            else 0.0,
            "accepted_chunks": accepted_count,
            "average_quality_score": avg_quality,
        }

        return transcript

    async def extract_intelligence(self, transcript: dict) -> dict:
        """
        Extract intelligence from cleaned transcript using comprehensive approach.
        Call after clean_transcript completes.

        Args:
            transcript: transcript dict with 'cleaned_chunks' or 'chunks' key

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
            chunks_to_process, progress_callback=None
        )
        transcript["intelligence"] = result

        logger.info(
            "Intelligence extraction completed",
            action_items_count=len(result.action_items),
            summary_length=len(result.summary),
            processing_time_ms=result.processing_stats.get("time_ms", 0),
        )

        return transcript
