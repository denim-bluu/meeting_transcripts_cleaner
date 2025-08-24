"""
Transcript processing router for VTT file upload and AI-powered cleaning.

Responsibilities:
- Validate VTT file uploads (extension .vtt, max 100MB, UTF-8 encoding)
- Handle idempotency keys to prevent duplicate processing
- Create background tasks for transcript processing with progress tracking
- Store tasks in cache with metadata (filename, file_size, models used)
- Return task IDs for client polling

Expected Behavior:
- POST /api/v1/transcript/process accepts UploadFile and optional idempotency_key header
- Returns TaskResponse with task_id and PROCESSING status on success
- Returns 400 Bad Request for invalid files (wrong extension, encoding, size)
- Returns 413 Request Entity Too Large for files > 100MB
- Idempotent requests return existing task_id if key already processed
- Background task updates progress from 0.0 to 1.0 with descriptive messages
"""

import asyncio
from datetime import datetime, timedelta
import os
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
import structlog

from backend.api.v1.dependencies import (
    get_task_or_404,
    handle_idempotency,
    validate_upload_file,
)
from backend.api.v1.schemas import TaskResponse, validate_file_size
from backend.shared.config import settings
from backend.tasks.cache import get_task_cache
from backend.tasks.models import TaskEntry, TaskStatus, TaskType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/transcript", tags=["transcript"])


@router.post("/process", response_model=TaskResponse)
async def process_transcript(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="VTT transcript file to process"),
    idempotency_key: str | None = Header(
        None, description="Idempotency key to prevent duplicate processing"
    ),
) -> TaskResponse:
    """
    Upload and process VTT transcript file.

    This endpoint accepts a VTT file, validates it, and starts background processing
    to clean and structure the transcript using AI. Returns a task ID for polling progress.

    - **file**: VTT file (max 100MB)
    - **idempotency_key**: Optional header to prevent duplicate processing
    - **Returns**: Task ID for status polling
    """
    # Check for idempotent request
    existing_task_id = await handle_idempotency(idempotency_key)
    if existing_task_id:
        existing_task = await get_task_or_404(existing_task_id)
        return TaskResponse(
            task_id=existing_task_id,
            status=existing_task.status,
            message=f"Idempotent request - returning existing task (status: {existing_task.status.value})",
        )

    # Validate file
    validate_upload_file(file)

    try:
        content = await file.read()
        content_str = content.decode("utf-8")
    except UnicodeDecodeError as err:
        logger.error("File encoding error", filename=file.filename, error=str(err))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid VTT file encoding. Please ensure file is UTF-8 encoded.",
        ) from err

    # Validate file size
    if not validate_file_size(len(content)):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {validate_file_size.__defaults__[0]}MB",
        )

    task_id = str(uuid.uuid4())

    # Create task entry
    task = TaskEntry(
        task_id=task_id,
        task_type=TaskType.TRANSCRIPT_PROCESSING,
        status=TaskStatus.PROCESSING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        progress=0.0,
        message="Starting VTT processing...",
        metadata={
            "filename": file.filename,
            "file_size_bytes": len(content),
            "models": {
                "cleaning_model": settings.cleaning_model,
                "review_model": settings.review_model,
            },
        },
    )

    # Store task in cache
    cache = get_task_cache()
    await cache.store_task(task)

    # Store idempotency key if provided
    if idempotency_key:
        expires_at = datetime.now() + timedelta(days=1)  # 24-hour expiry
        await cache.store_idempotency_key(idempotency_key, task_id, expires_at)

    logger.info(
        "VTT processing task started",
        task_id=task_id,
        filename=file.filename,
        content_size=len(content_str),
        idempotent=bool(idempotency_key),
        cleaning_model=settings.cleaning_model,
        review_model=settings.review_model,
    )

    # Process in background
    background_tasks.add_task(
        run_transcript_processing, task_id, content_str, request.app
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        message="VTT file received, processing started",
    )


async def run_transcript_processing(task_id: str, content: str, app) -> None:
    """Background task for VTT processing using refactored TranscriptProcessor."""
    from backend.tasks.cache import get_task_cache

    cache = get_task_cache()

    try:
        # Use pre-initialized processor from app state, with fallback
        processor = getattr(app.state, "transcript_processor", None)
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

            from backend.integrations.factories import create_transcript_processor

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise Exception("OPENAI_API_KEY not configured")
            processor = create_transcript_processor(api_key)

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

        # Since TranscriptProcessor expects a sync callback, we'll handle progress differently
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
        transcript = await asyncio.to_thread(processor.process_vtt, content)

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
        cleaned = await processor.clean_transcript(
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
