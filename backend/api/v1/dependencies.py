"""
Shared dependencies and utilities for all API routers to promote DRY principles.

Responsibilities:
- Provide common error response formatting with consistent structure
- Handle file upload validation (extension, size, encoding)
- Manage task retrieval with automatic 404 handling
- Process idempotency keys with cache lookups and expiration
- Perform automatic cleanup of expired tasks during operations

Expected Behavior:
- cleanup_old_tasks() calls cache.cleanup() to remove expired entries automatically
- create_error_response() returns JSONResponse with ErrorResponse schema structure
- validate_upload_file() raises HTTPException for invalid files (400 Bad Request)
- get_task_or_404() returns TaskEntry or raises HTTPException with 404 Not Found
- handle_idempotency() returns existing task_id if key found, None if new/expired
- All functions follow FastAPI dependency injection patterns
"""

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
import structlog

from backend.api.v1.schemas import (
    ErrorDetail,
    ErrorResponse,
    FileUploadConstraints,
    validate_file_extension,
)
from backend.tasks.cache import get_task_cache
from backend.tasks.models import TaskEntry

logger = structlog.get_logger(__name__)


async def cleanup_old_tasks() -> None:
    """Force cleanup of expired cache entries during task operations."""
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
    """
    Create standardized error response following API schema.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        error_code: Machine-readable error code for client handling
        message: Human-readable error message
        field: Optional field name for validation errors
        request_id: Optional request ID for debugging

    Returns:
        JSONResponse with ErrorResponse schema structure
    """
    error_response = ErrorResponse(
        error=ErrorDetail(code=error_code, message=message, field=field),
        request_id=request_id,
    )
    return JSONResponse(status_code=status_code, content=error_response.dict())


def validate_upload_file(file: UploadFile) -> None:
    """
    Validate uploaded file meets requirements before processing.

    Args:
        file: FastAPI UploadFile object

    Raises:
        HTTPException: 400 Bad Request if file invalid
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File name is required"
        )

    # Check file extension (.vtt only)
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension. Allowed: {FileUploadConstraints.ALLOWED_EXTENSIONS}",
        )


async def get_task_or_404(task_id: str) -> TaskEntry:
    """
    Get task by ID or raise 404 if not found/expired.

    Args:
        task_id: Unique task identifier

    Returns:
        TaskEntry if found and not expired

    Raises:
        HTTPException: 404 Not Found if task missing or expired
    """
    cache = get_task_cache()
    task = await cache.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or expired"
        )
    return task


async def handle_idempotency(idempotency_key: str | None) -> str | None:
    """
    Handle idempotency key, return existing task_id if key exists.

    Args:
        idempotency_key: Optional idempotency key from client

    Returns:
        Existing task_id if key found and not expired, None if new request
    """
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
