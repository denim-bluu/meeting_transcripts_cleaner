"""Application constants and configuration values."""

from typing import Any


# API Configuration
class API_ENDPOINTS:
    HEALTH = "/api/v1/health"
    TRANSCRIPT_PROCESS = "/api/v1/transcript/process"
    INTELLIGENCE_EXTRACT = "/api/v1/intelligence/extract"
    TASK_STATUS = "/api/v1/task/{task_id}"


class TIMEOUTS:
    HEALTH_CHECK = 5
    FILE_UPLOAD = 30
    STATUS_CHECK = 10
    INTELLIGENCE_START = 15


class HTTP_STATUS:
    OK = 200
    BAD_REQUEST = 400
    NOT_FOUND = 404
    SERVER_ERROR = 500


# Task Management
class TASK_STATUS:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class POLLING_CONFIG:
    INTERVAL_SECONDS = 2
    MAX_WAIT_SECONDS = 300
    UI_UPDATE_INTERVAL = 1


# Session State Keys
class STATE_KEYS:
    BACKEND_HEALTHY = "backend_healthy"
    CURRENT_TASK_ID = "current_task_id"
    TRANSCRIPT_DATA = "transcript_data"
    INTELLIGENCE_DATA = "intelligence_data"
    PROCESSING_STATUS = "processing_status"


# Default Values
DEFAULT_VALUES: dict[str, Any] = {
    STATE_KEYS.BACKEND_HEALTHY: False,
    STATE_KEYS.CURRENT_TASK_ID: None,
    STATE_KEYS.TRANSCRIPT_DATA: None,
    STATE_KEYS.INTELLIGENCE_DATA: None,
    STATE_KEYS.PROCESSING_STATUS: "idle",
}


# File Processing
class FILE_CONSTRAINTS:
    MAX_SIZE_MB = 100
    ALLOWED_EXTENSIONS = [".vtt"]
    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024


# UI Configuration
class UI_CONFIG:
    PAGE_TITLE = "Meeting Minutes Cleaner"
    SIDEBAR_WIDTH = 300
    MAIN_COLUMN_WIDTH = 700
    PROGRESS_UPDATE_INTERVAL = 0.5


# Detail Levels
DETAIL_LEVELS = {
    "standard": "Standard - Key decisions and action items",
    "comprehensive": "Comprehensive - Detailed discussion and context",
    "technical_focus": "Technical Focus - Maximum technical detail preservation",
}

# Export Formats
EXPORT_FORMATS = ["txt", "md", "json"]

# Error Messages
ERROR_MESSAGES = {
    "backend_unavailable": "Backend service is not available. Please check the server status.",
    "file_too_large": f"File size exceeds {FILE_CONSTRAINTS.MAX_SIZE_MB}MB limit.",
    "invalid_file_type": f"Only {', '.join(FILE_CONSTRAINTS.ALLOWED_EXTENSIONS)} files are supported.",
    "task_not_found": "Task not found or expired. Please try uploading again.",
    "processing_failed": "Processing failed. Please try again or contact support.",
}
