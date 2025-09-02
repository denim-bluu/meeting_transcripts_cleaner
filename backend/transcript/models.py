"""Transcript processing models - VTT parsing, cleaning, and review."""

from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass
class VTTEntry:
    """Single VTT cue exactly as it appears in the file."""

    cue_id: str  # e.g., "d700e97e-1c7f-4753-9597-54e5e43b4642/18-0"
    start_time: float  # seconds from 00:00:00.000
    end_time: float  # seconds from 00:00:00.000
    speaker: str  # e.g., "Joon Kang"
    text: str  # e.g., "OK. Yeah."


@dataclass
class VTTChunk:
    """Group of VTT entries chunked by token count for AI processing."""

    chunk_id: int  # Sequential: 0, 1, 2...
    entries: list[VTTEntry]
    token_count: int  # Approximate tokens (len(text) / 4)

    def to_transcript_text(self) -> str:
        """Format entries as 'Speaker: text' for AI processing.
        Example:
            Joon Kang: OK. Yeah.
        """
        lines = []
        for entry in self.entries:
            lines.append(f"{entry.speaker}: {entry.text}")
        return "\n".join(lines)


class CleaningResult(BaseModel):
    """Structured output from transcript cleaning."""

    cleaned_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    changes_made: list[str]


class ReviewResult(BaseModel):
    """Structured output from quality review."""

    quality_score: float = Field(ge=0.0, le=1.0)
    issues: list[str]
    accept: bool  # True if quality_score >= 0.7


