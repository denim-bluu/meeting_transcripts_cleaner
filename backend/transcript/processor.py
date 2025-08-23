"""Transcript processing orchestration using composition."""

from collections.abc import Callable

import structlog
from tasks.protocols import TaskRepository

from .protocols import (
    TranscriptCleaner,
    TranscriptParser,
    TranscriptReviewer,
)

logger = structlog.get_logger(__name__)


class TranscriptProcessor:
    """Orchestrates complete transcript processing pipeline using composition."""

    def __init__(
        self,
        parser: TranscriptParser,
        cleaner: TranscriptCleaner,
        reviewer: TranscriptReviewer,
        task_repo: TaskRepository,
    ):
        self._parser = parser
        self._cleaner = cleaner
        self._reviewer = reviewer
        self._task_repo = task_repo

    def process_vtt(self, content: str) -> dict:
        """Parse and chunk VTT file - same interface as TranscriptService.process_vtt()"""
        entries = self._parser.parse_vtt(content)
        chunks = self._parser.create_chunks(entries)

        speakers = list({e.speaker for e in entries})
        duration = max(e.end_time for e in entries) if entries else 0

        return {
            "entries": entries,
            "chunks": chunks,
            "speakers": speakers,
            "duration": duration,
        }

    async def clean_transcript(
        self, transcript: dict, progress_callback: Callable | None = None
    ) -> dict:
        """Complete transcript processing - same interface as TranscriptService.clean_transcript()"""
        # Extract data from transcript dict (output of process_vtt)
        entries = transcript["entries"]
        chunks = transcript["chunks"]
        speakers = transcript["speakers"]
        duration = transcript["duration"]

        # Step 2: Clean chunks (migrate concurrent processing logic from TranscriptService)
        cleaned_chunks = []
        review_results = []

        for i, chunk in enumerate(chunks):
            prev_text = ""
            if i > 0 and cleaned_chunks[i - 1]:
                prev_text = cleaned_chunks[i - 1].cleaned_text[-200:]

            clean_result = await self._cleaner.clean_chunk(chunk, prev_text)
            review_result = await self._reviewer.review_chunk(
                chunk, clean_result.cleaned_text
            )

            cleaned_chunks.append(clean_result)
            review_results.append(review_result)

            if progress_callback:
                progress_callback(
                    (i + 1) / len(chunks), f"Processed chunk {i + 1}/{len(chunks)}"
                )

        # Step 3: Build final transcript
        final_transcript = "\n".join([result.cleaned_text for result in cleaned_chunks])

        return {
            "entries": entries,
            "chunks": chunks,
            "speakers": speakers,
            "duration": duration,
            "cleaned_chunks": cleaned_chunks,
            "review_results": review_results,
            "final_transcript": final_transcript,
            "processing_stats": {
                "total_chunks": len(chunks),
                "avg_confidence": sum(r.confidence for r in cleaned_chunks)
                / len(cleaned_chunks)
                if cleaned_chunks
                else 0,
            },
        }
