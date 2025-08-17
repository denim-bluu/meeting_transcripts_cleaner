"""
API v1 endpoints for Meeting Transcript Cleaner.

This module contains all the FastAPI route handlers with proper Pydantic schema
validation, error handling, and OpenAPI documentation.
"""

from datetime import datetime, timedelta
import os
from typing import Any
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
import structlog

from backend_service.api.v1.schemas import (
    ErrorDetail,
    ErrorResponse,
    FileUploadConstraints,
    HealthStatus,
    IntelligenceExtractionRequest,
    TaskResponse,
    TaskStatusResponse,
    validate_file_extension,
    validate_file_size,
)
from backend_service.core.task_cache import (
    TaskEntry,
    TaskStatus,
    TaskType,
    get_task_cache,
)

logger = structlog.get_logger(__name__)

# Create API router
router = APIRouter(prefix="/api/v1", tags=["v1"])


# ===============================================================================
# Utility Functions
# ===============================================================================


async def cleanup_old_tasks() -> None:
    """Force cleanup of expired cache entries."""
    cache = get_task_cache()
    stats = await cache.cleanup()
    
    if stats["expired_tasks"] > 0 or stats["expired_idempotency_keys"] > 0:
        logger.info(
            "Cache cleanup completed",
            **stats
        )


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    field: str | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Create standardized error response."""
    error_response = ErrorResponse(
        error=ErrorDetail(code=error_code, message=message, field=field),
        request_id=request_id,
    )
    return JSONResponse(status_code=status_code, content=error_response.dict())


def validate_upload_file(file: UploadFile) -> None:
    """Validate uploaded file meets requirements."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File name is required"
        )

    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension. Allowed: {FileUploadConstraints.ALLOWED_EXTENSIONS}",
        )

    # Note: file.size is not available until read, so we check during processing


async def get_task_or_404(task_id: str) -> TaskEntry:
    """Get task by ID or raise 404."""
    cache = get_task_cache()
    task = await cache.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or expired"
        )
    return task


async def handle_idempotency(idempotency_key: str | None) -> str | None:
    """Handle idempotency key, return existing task_id if key exists."""
    if not idempotency_key:
        return None

    cache = get_task_cache()
    existing_task_id = await cache.get_task_for_idempotency_key(idempotency_key)

    if existing_task_id:
        logger.info(
            "Idempotent request detected",
            idempotency_key=idempotency_key,
            existing_task_id=existing_task_id,
        )

    return existing_task_id


# ===============================================================================
# Health Check Endpoints
# ===============================================================================


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """
    Health check endpoint for load balancers and monitoring.

    Returns current service status, uptime, and dependency health.
    """
    # Calculate uptime (simplified - in production would track actual start time)
    uptime_seconds = 300.0  # Placeholder

    # Check dependencies
    dependencies = {}

    # Check OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    dependencies["openai"] = "configured" if api_key else "missing"

    # Check cache health
    cache = get_task_cache()
    cache_health = await cache.health_check()
    dependencies["cache"] = cache_health.get("cache", "unknown")

    # Get task count from cache
    task_count = await cache.get_task_count()

    # Determine overall status
    overall_status = (
        "healthy"
        if all(status in ["configured", "healthy"] for status in dependencies.values())
        else "degraded"
    )

    return HealthStatus(
        status=overall_status,
        service="meeting-transcript-api",
        version="1.0.0",
        uptime_seconds=uptime_seconds,
        tasks_in_memory=task_count,
        dependencies=dependencies,
    )


# ===============================================================================
# Transcript Processing Endpoints
# ===============================================================================


@router.post("/transcript/process", response_model=TaskResponse)
async def process_transcript(
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
            detail=f"File too large. Maximum size: {FileUploadConstraints.MAX_FILE_SIZE_MB}MB",
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
    )

    # Process in background
    background_tasks.add_task(run_transcript_processing, task_id, content_str)

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        message="VTT file received, processing started",
    )


# ===============================================================================
# Intelligence Extraction Endpoints
# ===============================================================================


@router.post("/intelligence/extract", response_model=TaskResponse)
async def extract_intelligence(
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
    )

    # Extract intelligence in background
    background_tasks.add_task(
        run_intelligence_extraction,
        task_id,
        transcript_task.result,
        request.detail_level.value,
        request.custom_instructions,
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        message=f"Intelligence extraction started with {request.detail_level.value} detail level",
    )


# ===============================================================================
# Debug Endpoints
# ===============================================================================


@router.get("/debug/tasks")
async def debug_list_tasks(
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Debug endpoint to list tasks with filtering.

    - **status**: Filter by task status
    - **task_type**: Filter by task type
    - **limit**: Maximum number of tasks to return
    """
    cache = get_task_cache()

    # Convert string filters to proper enums
    status_filter = TaskStatus(status) if status and status != "All" else None
    type_filter = TaskType(task_type) if task_type and task_type != "All" else None

    # Get tasks from cache
    tasks = await cache.list_tasks(
        status=status_filter, task_type=type_filter, limit=limit
    )

    # Convert to serializable format
    task_data = [task.to_dict() for task in tasks]
    
    # Add convenience field
    for data in task_data:
        data["has_result"] = bool(data.get("result"))

    return {
        "tasks": task_data,
        "total_count": len(task_data),
        "filters_applied": {
            "status": status,
            "task_type": task_type,
            "limit": limit,
        },
    }


# ===============================================================================
# Task Management Endpoints
# ===============================================================================


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get current task status and results.

    Poll this endpoint to check progress and retrieve results when completed.
    Tasks are automatically cleaned up after 1 hour.

    - **task_id**: Unique task identifier
    - **Returns**: Current status, progress, and results (if completed)
    """
    # Clean up old tasks before checking
    await cleanup_old_tasks()

    task = await get_task_or_404(task_id)

    return TaskStatusResponse(
        task_id=task_id,
        type=task.task_type,
        status=task.status,
        progress=task.progress,
        message=task.message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result,
        error=ErrorDetail(
            code=task.error_code or "unknown", message=task.error or "", field=None
        )
        if task.status == TaskStatus.FAILED
        else None,
    )


@router.delete("/task/{task_id}")
async def cancel_task(task_id: str) -> dict[str, str]:
    """
    Cancel a running task.

    Note: This only removes the task from cache and stops result polling.
    Background processing cannot be interrupted once started.

    - **task_id**: Task ID to cancel
    """
    task = await get_task_or_404(task_id)

    # Remove from cache
    cache = get_task_cache()
    deleted = await cache.delete_task(task_id)

    if deleted:
        logger.info("Task cancelled/removed", task_id=task_id)
        return {"message": "Task cancelled successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel task",
        )


# ===============================================================================
# Helper Functions
# ===============================================================================


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
            result[key] = value.model_dump()
        elif isinstance(value, list) and value and hasattr(value[0], "model_dump"):
            # List of Pydantic models
            result[key] = [item.model_dump() for item in value]
        else:
            # Already serializable
            result[key] = value

    return result


# ===============================================================================
# Background Task Implementations
# ===============================================================================


async def run_transcript_processing(task_id: str, content: str) -> None:
    """Background task for VTT processing using existing TranscriptService."""
    cache = get_task_cache()

    try:
        # Import here to avoid startup overhead
        from backend_service.services.transcript_service import TranscriptService

        # Get API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise Exception("OPENAI_API_KEY not configured")

        # Initialize service
        service = TranscriptService(api_key)

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
            """Sync progress callback - just log for now."""
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
        transcript = service.process_vtt(content)

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
    detail_level: str,
    custom_instructions: str | None = None,
) -> None:
    """Background task for intelligence extraction using existing orchestrator."""
    cache = get_task_cache()

    try:
        if not transcript_data:
            raise Exception("No transcript data provided")

        # Import here to avoid startup overhead
        from backend_service.services.orchestration.intelligence_orchestrator import (
            IntelligenceOrchestrator,
        )

        # Initialize orchestrator
        orchestrator = IntelligenceOrchestrator(model="o3-mini")

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
        from backend_service.models.transcript import VTTChunk, VTTEntry

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
