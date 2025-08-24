"""
Debug and analytics router for system monitoring and troubleshooting.

Responsibilities:
- List tasks with optional filtering by status and task_type
- Provide detailed cache statistics and health metrics
- Support manual cache cleanup operations
- Return analytics data compatible with frontend Database tab
- Include pagination and operational metadata for debugging

Expected Behavior:
- GET /api/v1/debug/tasks returns paginated task list with filters
- Supports status filter (pending, processing, completed, failed)
- Supports task_type filter (transcript_processing, intelligence_extraction)
- Includes cache statistics (total tasks, breakdown by status/type)
- GET /api/v1/debug/cache/stats returns detailed cache health information
- POST /api/v1/debug/cache/cleanup forces expired task removal
- GET /api/v1/debug/analytics returns metrics for Database tab visualization
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
import structlog

from backend.tasks.cache import get_task_cache
from backend.tasks.models import TaskStatus, TaskType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/tasks")
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


@router.get("/cache/stats")
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


@router.post("/cache/cleanup")
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


@router.get("/analytics")
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
        1 for task in all_tasks if (now - task.created_at).total_seconds() < 3600
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
