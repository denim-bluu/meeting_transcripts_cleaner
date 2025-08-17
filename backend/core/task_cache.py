"""
Simple in-memory task cache with TTL and automatic cleanup.

This replaces the complex repository pattern with a lightweight caching solution
suitable for containerized deployments where state should be ephemeral.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Types of background tasks."""

    TRANSCRIPT_PROCESSING = "transcript_processing"
    INTELLIGENCE_EXTRACTION = "intelligence_extraction"


@dataclass
class TaskEntry:
    """
    Simplified task entry for in-memory storage.

    Attributes:
        task_id: Unique identifier
        task_type: Type of task being executed
        status: Current execution status
        created_at: When the task was created
        updated_at: When the task was last updated
        progress: Completion percentage (0.0 to 1.0)
        message: Human-readable status message
        result: Task result data (if completed)
        error: Error message (if failed)
        error_code: Machine-readable error code
        metadata: Additional task metadata
        expires_at: When this task expires from cache
    """

    task_id: str
    task_type: TaskType
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert task entry to dictionary for API responses."""
        return {
            "task_id": self.task_id,
            "type": self.task_type.value,
            "task_type": self.task_type.value,  # Added for frontend compatibility
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "error_code": self.error_code,
            "metadata": self.metadata,
            "expires_at": self.expires_at,
        }


class SimpleTaskCache:
    """
    Thread-safe in-memory cache for task management with automatic TTL cleanup.

    This cache is designed for containerized deployments where:
    - Tasks are short-lived (minutes to hours)
    - Horizontal scaling is handled by container orchestration
    - Persistence across restarts is not required

    Example:
        >>> cache = SimpleTaskCache(default_ttl_hours=2)
        >>>
        >>> # Store a task
        >>> task = TaskEntry(
        ...     task_id="abc123",
        ...     task_type=TaskType.TRANSCRIPT_PROCESSING,
        ...     status=TaskStatus.PROCESSING,
        ...     created_at=datetime.now(),
        ...     updated_at=datetime.now()
        ... )
        >>> await cache.store_task(task)
        >>>
        >>> # Retrieve the task
        >>> retrieved = await cache.get_task("abc123")
        >>> print(retrieved.status)  # TaskStatus.PROCESSING
        >>>
        >>> # Update task progress
        >>> retrieved.progress = 0.5
        >>> retrieved.message = "Halfway complete"
        >>> await cache.update_task(retrieved)
    """

    def __init__(self, default_ttl_hours: int = 1, cleanup_interval_minutes: int = 10):
        """
        Initialize the cache.

        Args:
            default_ttl_hours: Default time-to-live for tasks in hours
            cleanup_interval_minutes: How often to run cleanup in minutes
        """
        self._tasks: dict[str, TaskEntry] = {}
        self._idempotency_keys: dict[str, str] = {}  # key -> task_id
        self._idempotency_expires: dict[str, datetime] = {}  # key -> expire_time
        self._lock = asyncio.Lock()
        self.default_ttl = timedelta(hours=default_ttl_hours)
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self._last_cleanup = datetime.now()

        logger.info(
            "SimpleTaskCache initialized",
            default_ttl_hours=default_ttl_hours,
            cleanup_interval_minutes=cleanup_interval_minutes,
        )

    async def store_task(self, task: TaskEntry) -> TaskEntry:
        """
        Store a task in the cache.

        Args:
            task: Task to store

        Returns:
            The stored task entry

        Raises:
            ValueError: If task_id already exists
        """
        async with self._lock:
            if task.task_id in self._tasks:
                raise ValueError(f"Task {task.task_id} already exists")

            # Set expiration if not provided
            if task.expires_at is None:
                task.expires_at = datetime.now() + self.default_ttl

            self._tasks[task.task_id] = task

            logger.debug(
                "Task stored in cache",
                task_id=task.task_id,
                task_type=task.task_type.value,
                expires_at=task.expires_at,
            )

            # Opportunistic cleanup
            await self._cleanup_if_needed()

            return task

    async def get_task(self, task_id: str) -> TaskEntry | None:
        """
        Retrieve a task from the cache.

        Args:
            task_id: Unique task identifier

        Returns:
            Task entry if found and not expired, None otherwise
        """
        async with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                return None

            # Check if expired
            if task.expires_at and datetime.now() > task.expires_at:
                logger.debug("Task expired, removing from cache", task_id=task_id)
                del self._tasks[task_id]
                return None

            return task

    async def update_task(self, task: TaskEntry) -> TaskEntry:
        """
        Update an existing task in the cache.

        Args:
            task: Updated task entry

        Returns:
            The updated task entry

        Raises:
            ValueError: If task doesn't exist
        """
        async with self._lock:
            if task.task_id not in self._tasks:
                raise ValueError(f"Task {task.task_id} not found")

            task.updated_at = datetime.now()
            self._tasks[task.task_id] = task

            logger.debug(
                "Task updated in cache",
                task_id=task.task_id,
                status=task.status.value,
                progress=task.progress,
            )

            return task

    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task from the cache.

        Args:
            task_id: Task to delete

        Returns:
            True if task was deleted, False if not found
        """
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.debug("Task deleted from cache", task_id=task_id)
                return True
            return False

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        limit: int = 100,
    ) -> list[TaskEntry]:
        """
        List tasks with optional filtering.

        Args:
            status: Filter by task status
            task_type: Filter by task type
            limit: Maximum number of tasks to return

        Returns:
            List of matching tasks, sorted by creation time (newest first)
        """
        async with self._lock:
            # Clean up expired tasks first
            await self._cleanup_expired_tasks()

            tasks = list(self._tasks.values())

            # Apply filters
            if status:
                tasks = [t for t in tasks if t.status == status]
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]

            # Sort by creation time (newest first) and limit
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            return tasks[:limit]

    async def get_task_count(self) -> int:
        """Get total number of active tasks."""
        async with self._lock:
            await self._cleanup_expired_tasks()
            return len(self._tasks)

    async def store_idempotency_key(
        self, key: str, task_id: str, expires_at: datetime
    ) -> bool:
        """
        Store an idempotency key mapping.

        Args:
            key: Idempotency key
            task_id: Associated task ID
            expires_at: When this mapping expires

        Returns:
            True if stored, False if key already exists
        """
        async with self._lock:
            if key in self._idempotency_keys:
                return False

            self._idempotency_keys[key] = task_id
            self._idempotency_expires[key] = expires_at

            logger.debug(
                "Idempotency key stored",
                key=key,
                task_id=task_id,
                expires_at=expires_at,
            )

            return True

    async def get_task_for_idempotency_key(self, key: str) -> str | None:
        """
        Get task ID for an idempotency key if not expired.

        Args:
            key: Idempotency key

        Returns:
            Task ID if key exists and not expired, None otherwise
        """
        async with self._lock:
            if key not in self._idempotency_keys:
                return None

            # Check if expired
            expires_at = self._idempotency_expires.get(key)
            if expires_at and datetime.now() > expires_at:
                logger.debug("Idempotency key expired, removing", key=key)
                del self._idempotency_keys[key]
                del self._idempotency_expires[key]
                return None

            return self._idempotency_keys[key]

    async def cleanup(self) -> dict[str, int]:
        """
        Force cleanup of expired entries.

        Returns:
            Dictionary with cleanup statistics
        """
        async with self._lock:
            return await self._cleanup_expired_tasks()

    async def health_check(self) -> dict[str, Any]:
        """
        Get cache health information.

        Returns:
            Dictionary with cache statistics and health info
        """
        async with self._lock:
            await self._cleanup_expired_tasks()

            now = datetime.now()
            total_tasks = len(self._tasks)
            status_counts = {}

            for task in self._tasks.values():
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "cache": "healthy",
                "total_tasks": total_tasks,
                "total_idempotency_keys": len(self._idempotency_keys),
                "status_breakdown": status_counts,
                "last_cleanup": self._last_cleanup.isoformat(),
                "memory_usage": "lightweight",  # In-memory cache
                "expires_within_1h": sum(
                    1
                    for task in self._tasks.values()
                    if task.expires_at and task.expires_at <= now + timedelta(hours=1)
                ),
            }

    async def _cleanup_if_needed(self) -> None:
        """Run cleanup if enough time has passed since last cleanup."""
        if datetime.now() - self._last_cleanup > self.cleanup_interval:
            await self._cleanup_expired_tasks()

    async def _cleanup_expired_tasks(self) -> dict[str, int]:
        """
        Clean up expired tasks and idempotency keys.

        Returns:
            Cleanup statistics
        """
        now = datetime.now()

        # Clean up expired tasks
        expired_tasks = [
            task_id
            for task_id, task in self._tasks.items()
            if task.expires_at and task.expires_at <= now
        ]

        for task_id in expired_tasks:
            del self._tasks[task_id]

        # Clean up expired idempotency keys
        expired_keys = [
            key
            for key, expires_at in self._idempotency_expires.items()
            if expires_at <= now
        ]

        for key in expired_keys:
            del self._idempotency_keys[key]
            del self._idempotency_expires[key]

        self._last_cleanup = now

        if expired_tasks or expired_keys:
            logger.info(
                "Cache cleanup completed",
                expired_tasks=len(expired_tasks),
                expired_idempotency_keys=len(expired_keys),
                remaining_tasks=len(self._tasks),
                remaining_keys=len(self._idempotency_keys),
            )

        return {
            "expired_tasks": len(expired_tasks),
            "expired_idempotency_keys": len(expired_keys),
            "remaining_tasks": len(self._tasks),
            "remaining_idempotency_keys": len(self._idempotency_keys),
        }


# Global cache instance (initialized once at startup)
_task_cache: SimpleTaskCache | None = None


def get_task_cache() -> SimpleTaskCache:
    """
    Get the global task cache instance.

    Returns:
        The global task cache instance

    Raises:
        RuntimeError: If cache not initialized
    """
    if _task_cache is None:
        raise RuntimeError("Task cache not initialized. Call initialize_cache() first.")
    return _task_cache


def initialize_cache(ttl_hours: int = 1, cleanup_interval_minutes: int = 10) -> None:
    """
    Initialize the global task cache.

    Args:
        ttl_hours: Default TTL for tasks in hours
        cleanup_interval_minutes: Cleanup interval in minutes
    """
    global _task_cache
    _task_cache = SimpleTaskCache(
        default_ttl_hours=ttl_hours, cleanup_interval_minutes=cleanup_interval_minutes
    )
    logger.info("Global task cache initialized")


def reset_cache() -> None:
    """Reset the global cache (for testing)."""
    global _task_cache
    _task_cache = None
