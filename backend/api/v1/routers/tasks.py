"""Task management endpoints."""

from fastapi import APIRouter, HTTPException, status
import structlog

from backend.api.v1.schemas import ErrorDetail, TaskStatusResponse
from backend.tasks.cache import get_task_cache, TaskEntry, TaskStatus

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/task", tags=["tasks"])

async def get_task_or_404(task_id: str) -> TaskEntry:
    """Get task by ID or raise 404."""
    cache = get_task_cache()
    task = await cache.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or expired"
        )
    return task

async def cleanup_old_tasks() -> None:
    """Force cleanup of expired cache entries."""
    cache = get_task_cache()
    stats = await cache.cleanup()

    if stats["expired_tasks"] > 0:
        logger.info("Cache cleanup completed", **stats)

@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Get current task status and results.

    Logic:
    1. Clean up expired tasks
    2. Get task from cache
    3. Return status and results

    Expected behavior:
    - Returns 404 if task not found or expired
    - Returns current status, progress, and results
    """
    # Clean up old tasks
    await cleanup_old_tasks()

    # Get task
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
            code=task.error_code or "unknown",
            message=task.error or "",
            field=None
        ) if task.status == TaskStatus.FAILED else None,
    )

@router.delete("/{task_id}")
async def cancel_task(task_id: str) -> dict[str, str]:
    """Cancel a running task.

    Logic:
    1. Get task from cache
    2. Delete from cache
    3. Return success message

    Expected behavior:
    - Removes task from cache
    - Background processing cannot be interrupted
    """
    # Check task exists
    await get_task_or_404(task_id)

    # Delete from cache
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
