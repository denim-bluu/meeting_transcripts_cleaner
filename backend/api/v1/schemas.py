"""Pydantic schemas for API v1 - Simple DTOs only."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Import from domain layer
from backend.tasks.models import TaskStatus, TaskType


class DetailLevel(str, Enum):
    """Intelligence extraction detail levels."""

    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"
    TECHNICAL_FOCUS = "technical_focus"


class ErrorDetail(BaseModel):
    """Error information."""

    code: str
    message: str
    field: str | None = None


class TaskResponse(BaseModel):
    """Task creation response."""

    task_id: str
    status: TaskStatus
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response."""

    task_id: str
    type: TaskType
    status: TaskStatus
    progress: float = Field(ge=0.0, le=1.0)
    message: str
    created_at: datetime
    updated_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: ErrorDetail | None = None


class HealthStatus(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.now)
    uptime_seconds: float
    tasks_in_memory: int
    dependencies: dict[str, str] = {}
    models: dict[str, str] = {}


class IntelligenceExtractionRequest(BaseModel):
    """Intelligence extraction request."""

    transcript_id: str
    detail_level: DetailLevel = DetailLevel.COMPREHENSIVE
    custom_instructions: str | None = Field(None, max_length=1000)


# File validation constants (move to domain)
class FileUploadConstraints:
    MAX_FILE_SIZE_MB = 100
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {".vtt"}


def validate_file_extension(filename: str) -> bool:
    """Validate file extension."""
    return any(
        filename.lower().endswith(ext)
        for ext in FileUploadConstraints.ALLOWED_EXTENSIONS
    )


def validate_file_size(file_size: int) -> bool:
    """Validate file size."""
    return 0 < file_size <= FileUploadConstraints.MAX_FILE_SIZE_BYTES
