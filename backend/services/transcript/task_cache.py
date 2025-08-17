"""
Simple task cache service - redirects to core module.

This maintains backward compatibility while using the proper core module.
"""

# Re-export everything from the core module
from backend.core.task_cache import (
    SimpleTaskCache,
    TaskEntry,
    TaskStatus,
    TaskType,
    get_task_cache,
    initialize_cache,
    reset_cache,
)

__all__ = [
    "SimpleTaskCache",
    "TaskEntry",
    "TaskStatus", 
    "TaskType",
    "get_task_cache",
    "initialize_cache",
    "reset_cache",
]


async def cleanup_cache() -> dict[str, int]:
    """Force cleanup of the global cache."""
    cache = get_task_cache()
    return await cache.cleanup()