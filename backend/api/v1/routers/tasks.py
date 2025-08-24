"""
Task management router for status polling and task lifecycle control.

Responsibilities:
- Retrieve current task status, progress, and results by task_id
- Clean up expired tasks automatically during status checks
- Allow task cancellation (removes from cache, cannot stop background processing)
- Return detailed error information for failed tasks
- Handle task expiration and 404 responses for missing/expired tasks

Expected Behavior:
- GET /api/v1/task/{task_id} returns TaskStatusResponse with current status
- Returns 404 Not Found for missing or expired tasks
- Shows progress (0.0 to 1.0), current message, created/updated timestamps
- Includes result data when status is COMPLETED
- Includes error details when status is FAILED
- DELETE /api/v1/task/{task_id} removes task from cache immediately
- DELETE returns 404 if task not found, 200 with success message if removed
"""

from fastapi import APIRouter, HTTPException, status
import structlog

from backend.api.v1.dependencies import cleanup_old_tasks, get_task_or_404
from backend.api.v1.schemas import ErrorDetail, TaskStatusResponse
from backend.tasks.cache import get_task_cache
from backend.tasks.models import TaskStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/task", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
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


@router.delete("/{task_id}")
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
