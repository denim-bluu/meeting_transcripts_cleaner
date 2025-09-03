"""Transcript processing endpoints."""

from datetime import datetime
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
import structlog

from backend.api.v1.schemas import (
    FileUploadConstraints,
    TaskResponse,
    validate_file_extension,
    validate_file_size,
)
from backend.config import settings
from backend.tasks.cache import TaskEntry, TaskStatus, TaskType, get_task_cache

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/transcript", tags=["transcript"])


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


@router.post("/process", response_model=TaskResponse)
async def process_transcript(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="VTT transcript file to process"),
) -> TaskResponse:
    """Upload and process VTT transcript file.

    Logic:
    1. Validate file extension and size
    2. Create new task with unique ID
    3. Store task in cache
    4. Start background processing
    5. Return task ID for polling

    Expected behavior:
    - Each upload gets unique task_id (no idempotency)
    - Returns immediately with task_id
    - Processing happens in background
    """
    # Validate file
    validate_upload_file(file)

    # Read and validate content
    try:
        content = await file.read()
        content_str = content.decode("utf-8")
    except UnicodeDecodeError as err:
        logger.error("File encoding error", filename=file.filename, error=str(err))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid VTT file encoding. Please ensure file is UTF-8 encoded.",
        ) from err

    # Validate size
    if not validate_file_size(len(content)):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {FileUploadConstraints.MAX_FILE_SIZE_MB}MB",
        )

    # Create new task (no idempotency check)
    task_id = str(uuid.uuid4())

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

    # Store task
    cache = get_task_cache()
    await cache.store_task(task)

    logger.info(
        "VTT processing task started",
        task_id=task_id,
        filename=file.filename,
        content_size=len(content_str),
    )

    # Process in background
    from backend.api.v1.background_tasks import run_transcript_processing

    background_tasks.add_task(run_transcript_processing, task_id, content_str)

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        message="VTT file received, processing started",
    )
