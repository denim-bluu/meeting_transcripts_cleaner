"""Background task implementations."""

import asyncio
import os
from typing import Any

import structlog

from backend.tasks.cache import TaskStatus, get_task_cache

logger = structlog.get_logger(__name__)


async def _serialize_transcript_result(transcript: dict) -> dict:
    """Convert transcript result with dataclass objects to JSON-serializable format."""
    from dataclasses import asdict

    result = {}

    for key, value in transcript.items():
        if hasattr(value, "__dataclass_fields__"):
            # Single dataclass object
            result[key] = asdict(value)
        elif (
            isinstance(value, list)
            and value
            and hasattr(value[0], "__dataclass_fields__")
        ):
            # List of dataclass objects
            result[key] = [asdict(item) for item in value]
        elif hasattr(value, "model_dump"):
            # Pydantic model
            result[key] = value.model_dump()  # type: ignore
        elif isinstance(value, list) and value and hasattr(value[0], "model_dump"):
            # List of Pydantic models
            result[key] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in value
            ]  # type: ignore
        else:
            # Already serializable
            result[key] = value

    return result


async def run_transcript_processing(task_id: str, content: str) -> None:
    """Background task for VTT processing using existing TranscriptService."""
    cache = get_task_cache()

    try:
        # Import here to avoid startup overhead
        from backend.config import settings
        from backend.transcript.services.transcript_service import TranscriptService

        # Get API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise Exception("OPENAI_API_KEY not configured")

        # Initialize service
        service = TranscriptService(
            api_key,
            max_concurrent=settings.max_concurrent_tasks,
            rate_limit=settings.rate_limit_per_minute,
        )

        # Progress callback that updates task in cache
        async def update_progress_async(progress: float, message: str) -> None:
            """Async progress callback that updates task in cache."""
            try:
                task = await cache.get_task(task_id)
                if task:
                    task.progress = progress
                    task.message = message
                    await cache.update_task(task)
                    logger.debug(
                        "Progress update",
                        task_id=task_id,
                        progress=progress,
                        message=message,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to update progress", task_id=task_id, error=str(e)
                )

        # Since TranscriptService expects a sync callback, we'll handle progress differently
        def update_progress_sync(progress: float, message: str) -> None:
            """Sync progress callback - schedule async cache update and log."""
            try:
                asyncio.create_task(update_progress_async(progress, message))
            except Exception as e:
                logger.warning(
                    "Failed to schedule progress update", task_id=task_id, error=str(e)
                )
            logger.info(
                "Processing progress",
                task_id=task_id,
                progress=progress,
                message=message,
            )

        # Update task: parsing VTT
        task = await cache.get_task(task_id)
        if task:
            task.message = "Parsing VTT file..."
            await cache.update_task(task)

        # Process VTT
        transcript = await asyncio.to_thread(service.process_vtt, content)

        # Update task: starting AI cleaning
        task = await cache.get_task(task_id)
        if task:
            task.progress = 0.2
            task.message = f"VTT parsed: {len(transcript['chunks'])} chunks, starting AI cleaning..."
            await cache.update_task(task)

        # Clean transcript with concurrent processing
        await update_progress_async(
            0.3, f"Starting AI cleaning of {len(transcript['chunks'])} chunks..."
        )
        cleaned = await service.clean_transcript(
            transcript, progress_callback=update_progress_sync
        )
        await update_progress_async(0.9, "AI cleaning completed, finalizing results...")

        # Update task: completed
        task = await cache.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            task.message = "Transcript processing completed"

            # Convert result to JSON-serializable format
            task.result = await _serialize_transcript_result(cleaned)
            await cache.update_task(task)

        logger.info(
            "Transcript processing completed",
            task_id=task_id,
            chunks=len(cleaned["chunks"]),
            speakers=len(cleaned["speakers"]),
        )

    except Exception as e:
        logger.error("Transcript processing failed", task_id=task_id, error=str(e))

        # Update task: failed
        task = await cache.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.error_code = "processing_failed"
            task.message = f"Processing failed: {str(e)}"
            await cache.update_task(task)


async def run_intelligence_extraction(
    task_id: str,
    transcript_data: dict[str, Any] | None,
) -> None:
    """Background task for intelligence extraction using existing orchestrator."""
    cache = get_task_cache()

    try:
        if not transcript_data:
            raise Exception("No transcript data provided")

        # Import here to avoid startup overhead
        from backend.intelligence.intelligence_orchestrator import (
            IntelligenceOrchestrator,
        )

        # Initialize orchestrator
        orchestrator = IntelligenceOrchestrator()

        # Progress callback that updates task in cache
        async def update_progress(progress: float, message: str) -> None:
            task = await cache.get_task(task_id)
            if task:
                task.progress = progress
                task.message = message
                await cache.update_task(task)
                logger.debug(
                    "Intelligence progress", task_id=task_id, progress=progress
                )

        # Deserialize chunks back to VTTChunk objects
        from backend.transcript.models import VTTChunk, VTTEntry

        vtt_chunks = []
        for chunk_data in transcript_data["chunks"]:
            # Deserialize VTTEntry objects within each chunk
            entries = []
            for entry_data in chunk_data["entries"]:
                entry = VTTEntry(
                    cue_id=entry_data["cue_id"],
                    start_time=entry_data["start_time"],
                    end_time=entry_data["end_time"],
                    speaker=entry_data["speaker"],
                    text=entry_data["text"],
                )
                entries.append(entry)

            # Create VTTChunk with deserialized entries
            chunk = VTTChunk(
                chunk_id=chunk_data["chunk_id"],
                entries=entries,
                token_count=chunk_data["token_count"],
            )
            vtt_chunks.append(chunk)

        # Extract intelligence with proper VTTChunk objects
        intelligence = await orchestrator.process_meeting(
            vtt_chunks,
            progress_callback=update_progress,
        )

        # Update task: completed
        task = await cache.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            task.message = "Intelligence extraction completed"
            task.result = {
                "intelligence": intelligence.model_dump(),
                "summary": intelligence.summary,
                "action_items": [
                    item.model_dump() for item in intelligence.action_items
                ],
                "processing_stats": intelligence.processing_stats,
            }
            await cache.update_task(task)

        logger.info(
            "Intelligence extraction completed",
            task_id=task_id,
            action_items=len(intelligence.action_items),
        )

    except Exception as e:
        logger.error("Intelligence extraction failed", task_id=task_id, error=str(e))

        # Update task: failed
        task = await cache.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.error_code = "extraction_failed"
            task.message = f"Intelligence extraction failed: {str(e)}"
            await cache.update_task(task)
