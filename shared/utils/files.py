"""File handling utilities."""

from __future__ import annotations

from datetime import datetime
import re

from shared.config import FILE_CONSTRAINTS


def validate_file_metadata(filename: str, size_bytes: int) -> tuple[bool, str]:
    """Validate filename and size against allowed constraints."""

    if not filename:
        return False, "No file selected."

    extension = f".{filename.split('.')[-1].lower()}" if "." in filename else ""
    if extension not in FILE_CONSTRAINTS.allowed_extensions:
        return False, "Invalid file type. Only .vtt files are supported."

    if size_bytes > FILE_CONSTRAINTS.max_size_bytes:
        return False, f"File too large. Maximum size is {FILE_CONSTRAINTS.max_size_mb}MB."

    return True, ""


def format_file_size(size_bytes: int) -> str:
    """Return a display-friendly file size."""

    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filenames."""

    sanitized = re.sub(r'[<>:"/\\|?*]', "", filename)
    sanitized = sanitized.replace(" ", "_")
    if len(sanitized) > 64:
        name, ext = sanitized.rsplit(".", 1) if "." in sanitized else (sanitized, "")
        name = name[:60]
        sanitized = f"{name}.{ext}" if ext else name
    return sanitized


def generate_download_filename(original: str, suffix: str, extension: str) -> str:
    """Generate a download filename with timestamp and suffix."""
    base = original.rsplit(".", 1)[0] if "." in original else original
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base}_{suffix}_{timestamp}.{extension}"
    return sanitize_filename(filename)

