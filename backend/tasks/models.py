"""Task management models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


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