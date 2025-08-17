"""
Services layer for VTT transcript processing.

This module provides business logic services that separate the core AI processing
from the UI layer, enabling better maintainability and testability.
"""

from .transcript.transcript_service import TranscriptService

__all__ = ["TranscriptService"]
