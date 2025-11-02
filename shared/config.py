"""Shared application configuration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileConstraints:
    """File upload constraints."""

    max_size_mb: int = 100
    allowed_extensions: tuple[str, ...] = (".vtt",)

    @property
    def max_size_bytes(self) -> int:
        """Calculate max size in bytes."""
        return self.max_size_mb * 1024 * 1024


FILE_CONSTRAINTS = FileConstraints()


ERROR_MESSAGES = {
    "file_too_large": f"File size exceeds {FILE_CONSTRAINTS.max_size_mb}MB limit.",
    "invalid_file_type": "Only .vtt files are supported.",
    "processing_failed": "Processing failed. Please try again.",
    "missing_transcript": "No transcript available. Upload and process a VTT file first.",
    "intelligence_failed": "Intelligence extraction failed. Please retry.",
}


EXPORT_FORMATS = ("txt", "md", "vtt", "json")

