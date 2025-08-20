"""
Pydantic schemas for API v1 request/response models.

This module defines the formal data contracts for all API endpoints,
providing automatic validation, serialization, and OpenAPI documentation.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Import enums from our cache module to avoid duplication
from backend.models.transcript import TaskStatus, TaskType

# ===============================================================================
# Enums for Controlled Vocabularies
# ===============================================================================


class DetailLevel(str, Enum):
    """Intelligence extraction detail levels."""

    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"
    TECHNICAL_FOCUS = "technical_focus"


# ===============================================================================
# Base Schemas
# ===============================================================================


class BaseResponse(BaseModel):
    """Base response schema with common fields."""

    success: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Error code for programmatic handling")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(None, description="Field that caused the error")


class ErrorResponse(BaseModel):
    """Standardized error response."""

    success: bool = False
    error: ErrorDetail
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str | None = Field(None, description="Request ID for debugging")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ===============================================================================
# Task Management Schemas
# ===============================================================================


class TaskRequest(BaseModel):
    """Base schema for task creation requests."""

    idempotency_key: str | None = Field(
        None, description="Unique key to prevent duplicate processing", max_length=128
    )


class TaskResponse(BaseResponse):
    """Response for task creation."""

    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    message: str = Field(..., description="Human-readable status message")


class TaskStatusResponse(BaseResponse):
    """Detailed task status response."""

    task_id: str = Field(..., description="Unique task identifier")
    type: TaskType = Field(..., description="Type of task")
    status: TaskStatus = Field(..., description="Current task status")
    progress: float = Field(..., ge=0.0, le=1.0, description="Progress (0.0 to 1.0)")
    message: str = Field(..., description="Current status message")
    created_at: datetime = Field(..., description="Task creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    result: dict[str, Any] | None = Field(
        None, description="Task result (if completed)"
    )
    error: ErrorDetail | None = Field(None, description="Error details (if failed)")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ===============================================================================
# Transcript Processing Schemas
# ===============================================================================


class TranscriptProcessRequest(TaskRequest):
    """Request schema for transcript processing."""

    pass  # File is handled separately by FastAPI's UploadFile


class TranscriptMetadata(BaseModel):
    """Metadata about the processed transcript."""

    filename: str = Field(..., description="Original filename")
    file_size_bytes: int = Field(..., gt=0, description="File size in bytes")
    total_chunks: int = Field(..., ge=0, description="Number of transcript chunks")
    total_speakers: int = Field(..., ge=0, description="Number of identified speakers")
    duration_seconds: float | None = Field(None, ge=0, description="Meeting duration")
    processing_time_seconds: float | None = Field(
        None, ge=0, description="Processing time"
    )


class SpeakerInfo(BaseModel):
    """Information about a speaker in the transcript."""

    speaker_id: str = Field(..., description="Speaker identifier")
    display_name: str = Field(..., description="Speaker display name")
    total_speaking_time: float | None = Field(
        None, ge=0, description="Total speaking time in seconds"
    )
    chunk_count: int = Field(..., ge=0, description="Number of chunks by this speaker")


class TranscriptChunk(BaseModel):
    """A cleaned transcript chunk."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    start_time: float = Field(..., ge=0, description="Start time in seconds")
    end_time: float = Field(..., gt=0, description="End time in seconds")
    speaker: str = Field(..., description="Speaker identifier")
    original_text: str = Field(..., description="Original transcript text")
    cleaned_text: str = Field(..., description="AI-cleaned text")
    confidence_score: float | None = Field(
        None, ge=0, le=1, description="Cleaning confidence"
    )


class TranscriptResult(BaseModel):
    """Complete transcript processing result."""

    metadata: TranscriptMetadata
    speakers: list[SpeakerInfo]
    chunks: list[TranscriptChunk]
    processing_stats: dict[str, Any] = Field(default_factory=dict)


# ===============================================================================
# Intelligence Extraction Schemas
# ===============================================================================


class IntelligenceExtractionRequest(TaskRequest):
    """Request schema for intelligence extraction."""

    transcript_id: str = Field(
        ..., description="Task ID of completed transcript processing"
    )
    detail_level: DetailLevel = Field(
        default=DetailLevel.COMPREHENSIVE, description="Level of detail for extraction"
    )
    custom_instructions: str | None = Field(
        None, max_length=1000, description="Custom instructions for AI processing"
    )


class ActionItem(BaseModel):
    """An action item extracted from the meeting."""

    description: str = Field(..., min_length=3, description="Action item description")
    owner: str | None = Field(None, description="Person responsible")
    due_date: str | None = Field(None, description="Due date or timeframe")
    priority: str | None = Field(None, description="Priority level")
    status: str | None = Field(None, description="Current status")


class MeetingIntelligence(BaseModel):
    """Complete meeting intelligence analysis."""

    summary: str = Field(..., min_length=10, description="Meeting summary in markdown")
    action_items: list[ActionItem] = Field(
        default_factory=list, description="Extracted action items"
    )
    key_topics: list[str] = Field(
        default_factory=list, description="Main topics discussed"
    )
    decisions_made: list[str] = Field(
        default_factory=list, description="Decisions reached"
    )
    follow_up_items: list[str] = Field(
        default_factory=list, description="Follow-up items"
    )
    participants: list[str] = Field(
        default_factory=list, description="Meeting participants"
    )
    processing_stats: dict[str, Any] = Field(
        default_factory=dict, description="Processing metadata"
    )


class IntelligenceResult(BaseModel):
    """Intelligence extraction result."""

    intelligence: MeetingIntelligence
    detail_level: DetailLevel
    extraction_time_seconds: float = Field(
        ..., ge=0, description="Time taken for extraction"
    )
    token_usage: dict[str, int] | None = Field(
        None, description="AI token usage statistics"
    )


# ===============================================================================
# Health Check Schemas
# ===============================================================================


class HealthStatus(BaseModel):
    """System health status."""

    status: str = Field(..., description="Overall health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=datetime.now)
    uptime_seconds: float = Field(..., ge=0, description="Service uptime")
    tasks_in_memory: int = Field(..., ge=0, description="Number of tasks in memory")
    dependencies: dict[str, str] = Field(
        default_factory=dict, description="Dependency status"
    )
    models: dict[str, str] = Field(
        default_factory=dict,
        description="Configured LLM models (cleaning, review, insights, synthesis, segment, and reasoning settings)",
    )

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ===============================================================================
# Utility Schemas
# ===============================================================================


class PaginationRequest(BaseModel):
    """Pagination parameters for list endpoints."""

    offset: int = Field(default=0, ge=0, description="Number of items to skip")
    limit: int = Field(
        default=50, ge=1, le=1000, description="Maximum number of items to return"
    )
    sort_by: str | None = Field(None, description="Field to sort by")
    sort_order: str | None = Field(
        None, pattern=r"^(asc|desc)$", description="Sort order"
    )


class PaginatedResponse(BaseResponse):
    """Base paginated response."""

    total: int = Field(..., ge=0, description="Total number of items")
    offset: int = Field(..., ge=0, description="Current offset")
    limit: int = Field(..., ge=1, description="Items per page")
    has_more: bool = Field(..., description="Whether more items are available")


# ===============================================================================
# Validation Helpers
# ===============================================================================


class FileUploadConstraints:
    """Constants for file upload validation."""

    MAX_FILE_SIZE_MB = 100
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {".vtt"}
    ALLOWED_MIME_TYPES = {"text/vtt", "text/plain"}


def validate_file_extension(filename: str) -> bool:
    """Validate file extension."""
    if not filename:
        return False
    return any(
        filename.lower().endswith(ext)
        for ext in FileUploadConstraints.ALLOWED_EXTENSIONS
    )


def validate_file_size(file_size: int) -> bool:
    """Validate file size."""
    return 0 < file_size <= FileUploadConstraints.MAX_FILE_SIZE_BYTES
