"""Application constants and configuration values (Streamlit-only)."""

from typing import Any


# Session State Keys
class STATE_KEYS:
    CURRENT_TASK_ID = "current_task_id"
    TRANSCRIPT_DATA = "transcript_data"
    INTELLIGENCE_DATA = "intelligence_data"
    PROCESSING_STATUS = "processing_status"


# Default Values
DEFAULT_VALUES: dict[str, Any] = {
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


# Export Formats
EXPORT_FORMATS = ["txt", "md", "json"]

# Error Messages
ERROR_MESSAGES = {
    "file_too_large": f"File size exceeds {FILE_CONSTRAINTS.MAX_SIZE_MB}MB limit.",
    "invalid_file_type": f"Only {', '.join(FILE_CONSTRAINTS.ALLOWED_EXTENSIONS)} files are supported.",
    "processing_failed": "Processing failed. Please try again or contact support.",
}
