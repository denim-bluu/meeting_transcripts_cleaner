"""Common utility functions."""

from datetime import datetime
import re
from typing import Any

from utils.constants import FILE_CONSTRAINTS


def validate_file(file) -> tuple[bool, str]:
    """Validate uploaded file.

    Logic:
    1. Check file exists and has name
    2. Validate file extension
    3. Check file size constraints
    4. Return validation result and error message
    """
    if not file or not file.name:
        return False, "No file selected"

    # Check extension
    file_ext = f".{file.name.split('.')[-1].lower()}"
    if file_ext not in FILE_CONSTRAINTS.ALLOWED_EXTENSIONS:
        return (
            False,
            f"Invalid file type. Allowed: {', '.join(FILE_CONSTRAINTS.ALLOWED_EXTENSIONS)}",
        )

    # Check size
    if hasattr(file, "size") and file.size > FILE_CONSTRAINTS.MAX_SIZE_BYTES:
        return False, f"File too large. Maximum: {FILE_CONSTRAINTS.MAX_SIZE_MB}MB"

    return True, ""


def format_file_size(bytes_size: int) -> str:
    """Format file size for display.

    Logic:
    1. Convert bytes to appropriate unit (B, KB, MB)
    2. Return formatted string with unit
    """
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"


def format_duration(seconds: float) -> str:
    """Format duration for display.

    Logic:
    1. Convert seconds to minutes and seconds
    2. Return formatted time string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.1f}s"


def extract_metrics_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """Extract common metrics from processing result.

    Logic:
    1. Parse result for common metrics fields
    2. Calculate derived metrics if needed
    3. Return standardized metrics dictionary
    """
    if not result:
        return {}

    metrics = {}

    # Extract basic metrics
    if "processing_stats" in result:
        stats = result["processing_stats"]
        metrics.update(
            {
                "processing_time": stats.get("total_time_seconds", 0),
                "original_lines": stats.get("original_line_count", 0),
                "cleaned_lines": stats.get("cleaned_line_count", 0),
                "improvements_made": stats.get("total_improvements", 0),
            }
        )

    # Calculate improvement percentage
    if "original_lines" in metrics and "improvements_made" in metrics:
        original = metrics["original_lines"]
        improvements = metrics["improvements_made"]
        if original > 0:
            metrics["improvement_percentage"] = (improvements / original) * 100

    return metrics


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for downloads.

    Logic:
    1. Remove invalid characters
    2. Replace spaces with underscores
    3. Ensure reasonable length
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "", filename)
    # Replace spaces with underscores
    sanitized = sanitized.replace(" ", "_")
    # Limit length
    if len(sanitized) > 50:
        name, ext = sanitized.rsplit(".", 1) if "." in sanitized else (sanitized, "")
        sanitized = f"{name[:46]}.{ext}" if ext else name[:50]

    return sanitized


def generate_download_filename(original_name: str, suffix: str, extension: str) -> str:
    """Generate download filename with timestamp.

    Logic:
    1. Extract base name from original filename
    2. Add suffix and timestamp
    3. Ensure valid filename format
    """
    base_name = (
        original_name.rsplit(".", 1)[0] if "." in original_name else original_name
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{suffix}_{timestamp}.{extension}"
    return sanitize_filename(filename)
