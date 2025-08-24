"""
Intelligence extraction router for meeting analysis and insight generation.

Responsibilities:
- Validate intelligence extraction requests with transcript_id references
- Check that referenced transcript tasks are COMPLETED before processing
- Support multiple detail levels (standard, comprehensive, technical_focus)
- Handle custom_instructions for specialized analysis requirements
- Create background tasks for concurrent insight extraction and synthesis

Expected Behavior:
- POST /api/v1/intelligence/extract accepts IntelligenceExtractionRequest body
- Returns 400 Bad Request if transcript_id not found or not completed
- Returns TaskResponse with task_id and PROCESSING status on success
- Background task extracts insights concurrently then synthesizes final intelligence
- Supports idempotency keys to prevent duplicate extraction
- Progress updates show extraction and synthesis phases separately
"""

from datetime import datetime, timedelta
import os
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
import structlog

from backend.api.v1.dependencies import get_task_or_404, handle_idempotency
from backend.api.v1.schemas import IntelligenceExtractionRequest, TaskResponse
from backend.shared.config import settings
from backend.tasks.cache import get_task_cache
from backend.tasks.models import TaskEntry, TaskStatus, TaskType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.post("/extract", response_model=TaskResponse)
async def extract_intelligence(
    http_request: Request,
    request: IntelligenceExtractionRequest,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    """
    Extract meeting intelligence from processed transcript.

    Analyzes a completed transcript to extract:
    - Meeting summary
    - Action items
    - Key decisions
    - Follow-up items

    - **transcript_id**: Task ID from completed transcript processing
    - **detail_level**: Level of detail for extraction
    - **custom_instructions**: Optional custom AI instructions
    """
    # Check for idempotent request
    existing_task_id = await handle_idempotency(request.idempotency_key)
    if existing_task_id:
        existing_task = await get_task_or_404(existing_task_id)
        return TaskResponse(
            task_id=existing_task_id,
            status=existing_task.status,
            message=f"Idempotent request - returning existing task (status: {existing_task.status.value})",
        )

    # Validate transcript exists and is completed
    transcript_task = await get_task_or_404(request.transcript_id)

    if transcript_task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transcript processing not completed. Current status: {transcript_task.status.value}",
        )

    task_id = str(uuid.uuid4())

    # Create task entry
    task = TaskEntry(
        task_id=task_id,
        task_type=TaskType.INTELLIGENCE_EXTRACTION,
        status=TaskStatus.PROCESSING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        progress=0.0,
        message=f"Starting intelligence extraction with {request.detail_level} detail level...",
        metadata={
            "detail_level": request.detail_level.value,
            "transcript_id": request.transcript_id,
            "custom_instructions": request.custom_instructions,
            "models": {
                "insights_model": settings.insights_model,
                "synthesis_model": settings.synthesis_model,
                "segment_model": settings.segment_model,
                "synthesis_reasoning_effort": settings.synthesis_reasoning_effort,
                "synthesis_reasoning_summary": settings.synthesis_reasoning_summary,
            },
        },
    )

    # Store task in cache
    cache = get_task_cache()
    await cache.store_task(task)

    # Store idempotency key if provided
    if request.idempotency_key:
        expires_at = datetime.now() + timedelta(days=1)  # 24-hour expiry
        await cache.store_idempotency_key(request.idempotency_key, task_id, expires_at)

    logger.info(
        "Intelligence extraction task started",
        task_id=task_id,
        transcript_id=request.transcript_id,
        detail_level=request.detail_level.value,
        idempotent=bool(request.idempotency_key),
        insights_model=settings.insights_model,
        synthesis_model=settings.synthesis_model,
        segment_model=settings.segment_model,
        synthesis_reasoning_effort=settings.synthesis_reasoning_effort,
        synthesis_reasoning_summary=settings.synthesis_reasoning_summary,
    )

    # Extract intelligence in background
    background_tasks.add_task(
        run_intelligence_extraction,
        task_id,
        transcript_task.result,
        request.detail_level.value,
        request.custom_instructions,
        http_request.app,
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        message=f"Intelligence extraction started with {request.detail_level.value} detail level",
    )


async def run_intelligence_extraction(
    task_id: str,
    transcript_data: dict[str, Any] | None,
    detail_level: str,
    custom_instructions: str | None = None,
    app=None,
) -> None:
    """Background task for intelligence extraction using existing orchestrator."""
    from backend.tasks.cache import get_task_cache

    cache = get_task_cache()

    try:
        if not transcript_data:
            raise Exception("No transcript data provided")

        # Use pre-initialized processor from app state, with fallback
        processor = getattr(app.state, "intelligence_processor", None) if app else None
        if not processor:
            # Fallback: create processor on-demand
            logger.warning(
                "Using fallback processor creation - services not initialized at startup"
            )

            # Ensure cache is initialized for fallback creation
            from backend.tasks.cache import initialize_cache

            try:
                cache  # Test if cache exists
            except:
                # Initialize cache if not already done
                from backend.shared.config import settings

                initialize_cache(
                    ttl_hours=settings.task_ttl_hours,
                    cleanup_interval_minutes=settings.cleanup_interval_minutes,
                )
                cache = get_task_cache()

            from backend.integrations.factories import create_intelligence_processor

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise Exception("OPENAI_API_KEY not configured")
            processor = create_intelligence_processor(api_key)

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
        from transcript.models import VTTChunk, VTTEntry

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
        intelligence = await processor.process_meeting(
            vtt_chunks,
            detail_level=detail_level,
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
                "detail_level": detail_level,
            }
            await cache.update_task(task)

        logger.info(
            "Intelligence extraction completed",
            task_id=task_id,
            action_items=len(intelligence.action_items),
            detail_level=detail_level,
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
