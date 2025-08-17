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

from backend.api.v1.schemas import (
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
from backend.core.task_cache import TaskEntry, TaskStatus, TaskType, get_task_cache

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
        logger.info("Cache cleanup completed", **stats)


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
    Debug endpoint to list tasks with filtering and enhanced operational visibility.

    - **status**: Filter by task status (pending, processing, completed, failed, cancelled)
    - **task_type**: Filter by task type (transcript_processing, intelligence_extraction)
    - **limit**: Maximum number of tasks to return (default: 100, max: 500)
    """
    cache = get_task_cache()

    # Validate and cap limit
    limit = min(max(1, limit), 500)

    # Convert string filters to proper enums with validation
    status_filter = None
    if status and status.lower() not in ["all", "none"]:
        try:
            status_filter = TaskStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid values: {[s.value for s in TaskStatus]}",
            )

    type_filter = None
    if task_type and task_type.lower() not in ["all", "none"]:
        try:
            type_filter = TaskType(task_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task_type '{task_type}'. Valid values: {[t.value for t in TaskType]}",
            )

    # Get tasks from cache
    tasks = await cache.list_tasks(
        status=status_filter, task_type=type_filter, limit=limit
    )

    # Get cache statistics
    cache_health = await cache.health_check()

    # Convert to serializable format with enhanced data
    task_data = []
    for task in tasks:
        task_dict = task.to_dict()

        # Add convenience fields
        task_dict["has_result"] = bool(task_dict.get("result"))
        task_dict["has_error"] = bool(task_dict.get("error"))
        task_dict["duration_seconds"] = (
            (task_dict["updated_at"] - task_dict["created_at"]).total_seconds()
            if task_dict["updated_at"] and task_dict["created_at"]
            else 0
        )

        # Add time until expiration
        if task_dict.get("expires_at"):
            expires_at = task_dict["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            time_to_expiry = (expires_at - datetime.now()).total_seconds()
            task_dict["expires_in_seconds"] = max(0, time_to_expiry)
        else:
            task_dict["expires_in_seconds"] = None

        task_data.append(task_dict)

    return {
        "tasks": task_data,
        "total_count": len(task_data),
        "cache_statistics": {
            "total_tasks_in_cache": cache_health.get("total_tasks", 0),
            "total_idempotency_keys": cache_health.get("total_idempotency_keys", 0),
            "status_breakdown": cache_health.get("status_breakdown", {}),
            "expires_within_1h": cache_health.get("expires_within_1h", 0),
            "last_cleanup": cache_health.get("last_cleanup"),
        },
        "filters_applied": {
            "status": status,
            "task_type": task_type,
            "limit": limit,
        },
        "available_filters": {
            "status": [s.value for s in TaskStatus],
            "task_type": [t.value for t in TaskType],
        },
    }


@router.get("/debug/cache/stats")
async def debug_cache_stats() -> dict[str, Any]:
    """
    Debug endpoint for detailed cache statistics and health information.

    Provides comprehensive cache metrics for monitoring and troubleshooting.
    """
    cache = get_task_cache()

    # Get detailed health check
    health_info = await cache.health_check()

    # Get task count by status and type
    all_tasks = await cache.list_tasks(limit=1000)  # Get a large sample

    # Calculate detailed statistics
    stats_by_type = {}
    stats_by_status = {}
    recent_tasks = 0
    old_tasks = 0
    now = datetime.now()

    for task in all_tasks:
        # Type statistics
        task_type = task.task_type.value
        if task_type not in stats_by_type:
            stats_by_type[task_type] = {"count": 0, "avg_progress": 0.0}
        stats_by_type[task_type]["count"] += 1
        stats_by_type[task_type]["avg_progress"] += task.progress

        # Status statistics
        task_status = task.status.value
        if task_status not in stats_by_status:
            stats_by_status[task_status] = {"count": 0, "avg_duration": 0.0}
        stats_by_status[task_status]["count"] += 1

        # Duration calculation
        if task.updated_at and task.created_at:
            duration = (task.updated_at - task.created_at).total_seconds()
            stats_by_status[task_status]["avg_duration"] += duration

        # Age analysis
        age_hours = (now - task.created_at).total_seconds() / 3600
        if age_hours < 1:
            recent_tasks += 1
        else:
            old_tasks += 1

    # Calculate averages
    for type_stats in stats_by_type.values():
        if type_stats["count"] > 0:
            type_stats["avg_progress"] /= type_stats["count"]

    for status_stats in stats_by_status.values():
        if status_stats["count"] > 0:
            status_stats["avg_duration"] /= status_stats["count"]

    return {
        "cache_health": health_info,
        "detailed_statistics": {
            "by_type": stats_by_type,
            "by_status": stats_by_status,
            "age_distribution": {
                "recent_tasks_under_1h": recent_tasks,
                "older_tasks_over_1h": old_tasks,
            },
        },
        "performance_metrics": {
            "total_tasks_sampled": len(all_tasks),
            "cache_memory_usage": "lightweight",  # In-memory cache
        },
        "timestamp": now.isoformat(),
    }


@router.post("/debug/cache/cleanup")
async def debug_force_cleanup() -> dict[str, Any]:
    """
    Debug endpoint to force cache cleanup and return cleanup statistics.

    Useful for testing and manual maintenance of the cache.
    """
    cache = get_task_cache()

    # Force cleanup
    cleanup_stats = await cache.cleanup()

    logger.info("Manual cache cleanup triggered via debug endpoint", **cleanup_stats)

    return {
        "message": "Cache cleanup completed",
        "cleanup_statistics": cleanup_stats,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/debug/analytics")
async def debug_analytics() -> dict[str, Any]:
    """
    Debug endpoint providing analytics data for the Database tab.
    
    Provides database/cache analytics that were previously from a database system.
    Now adapted for the in-memory cache system.
    """
    cache = get_task_cache()
    
    # Get cache health and task statistics
    health_info = await cache.health_check()
    all_tasks = await cache.list_tasks(limit=1000)
    
    # Calculate analytics similar to what a database would provide
    total_tasks = len(all_tasks)
    
    # Status distribution
    status_distribution = {}
    for task in all_tasks:
        status = task.status.value
        status_distribution[status] = status_distribution.get(status, 0) + 1
    
    # Type distribution
    type_distribution = {}
    for task in all_tasks:
        task_type = task.task_type.value
        type_distribution[task_type] = type_distribution.get(task_type, 0) + 1
    
    # Calculate completion rate
    completed_tasks = status_distribution.get("completed", 0)
    failed_tasks = status_distribution.get("failed", 0)
    total_finished = completed_tasks + failed_tasks
    success_rate = (completed_tasks / total_finished * 100) if total_finished > 0 else 0
    
    # Average task duration
    total_duration = 0
    duration_count = 0
    for task in all_tasks:
        if task.updated_at and task.created_at:
            total_duration += (task.updated_at - task.created_at).total_seconds()
            duration_count += 1
    
    avg_duration = total_duration / duration_count if duration_count > 0 else 0
    
    # Recent activity (last hour)
    now = datetime.now()
    recent_tasks = sum(
        1 for task in all_tasks 
        if (now - task.created_at).total_seconds() < 3600
    )
    
    return {
        "cache_analytics": {
            "total_tasks": total_tasks,
            "total_idempotency_keys": health_info.get("total_idempotency_keys", 0),
            "cache_health": health_info.get("cache", "unknown"),
            "last_cleanup": health_info.get("last_cleanup", "never"),
        },
        "task_distribution": {
            "by_status": status_distribution,
            "by_type": type_distribution,
        },
        "performance_metrics": {
            "success_rate_percent": round(success_rate, 2),
            "average_duration_seconds": round(avg_duration, 2),
            "recent_tasks_last_hour": recent_tasks,
            "tasks_expiring_soon": health_info.get("expires_within_1h", 0),
        },
        "system_info": {
            "storage_type": "in_memory_cache",
            "persistence": "ephemeral",
            "cleanup_interval": "automatic",
            "ttl_default_hours": 1,
        },
        "timestamp": now.isoformat(),
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


# ===============================================================================
# Background Task Implementations
# ===============================================================================


async def run_transcript_processing(task_id: str, content: str) -> None:
    """Background task for VTT processing using existing TranscriptService."""
    cache = get_task_cache()

    try:
        # Import here to avoid startup overhead
        from backend.services.transcript.transcript_service import TranscriptService

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
        from backend.services.orchestration.intelligence_orchestrator import (
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
        from backend.models.transcript import VTTChunk, VTTEntry

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
