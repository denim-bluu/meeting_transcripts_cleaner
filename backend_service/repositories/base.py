"""
Abstract repository interfaces for the repository pattern.

Defines the contracts for data access that can be implemented
by different storage backends (SQLite, Snowflake, etc.).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from backend_service.api.v1.schemas import TaskStatus, TaskType


class TaskEntity:
    """Task entity representing a background task."""

    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        status: TaskStatus,
        created_at: datetime,
        updated_at: datetime | None = None,
        progress: float = 0.0,
        message: str = "",
        result: dict[str, Any] | None = None,
        error: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at or created_at
        self.progress = progress
        self.message = message
        self.result = result
        self.error = error
        self.error_code = error_code
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "task_id": self.task_id,
            "type": self.task_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "error_code": self.error_code,
            "metadata": self.metadata,
        }


class TaskRepository(ABC):
    """Abstract repository for task persistence."""

    @abstractmethod
    async def create_task(self, task: TaskEntity) -> TaskEntity:
        """Create a new task."""
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> TaskEntity | None:
        """Get a task by ID."""
        pass

    @abstractmethod
    async def update_task(self, task: TaskEntity) -> TaskEntity:
        """Update an existing task."""
        pass

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        pass

    @abstractmethod
    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskEntity]:
        """List tasks with optional filtering."""
        pass

    @abstractmethod
    async def cleanup_old_tasks(self, older_than: datetime) -> int:
        """Clean up tasks older than the specified datetime."""
        pass

    @abstractmethod
    async def get_task_count(self) -> int:
        """Get total number of tasks."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Check repository health."""
        pass


class IdempotencyRepository(ABC):
    """Abstract repository for idempotency key management."""

    @abstractmethod
    async def store_idempotency_key(
        self, key: str, task_id: str, expires_at: datetime
    ) -> bool:
        """Store an idempotency key with associated task ID."""
        pass

    @abstractmethod
    async def get_task_for_key(self, key: str) -> str | None:
        """Get task ID for an idempotency key if it exists and hasn't expired."""
        pass

    @abstractmethod
    async def cleanup_expired_keys(self) -> int:
        """Clean up expired idempotency keys."""
        pass
