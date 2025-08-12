"""Simple VTT data models for transcript processing."""

from dataclasses import dataclass


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
        """Format entries as 'Speaker: text' for AI processing."""
        lines = []
        for entry in self.entries:
            lines.append(f"{entry.speaker}: {entry.text}")
        return "\n".join(lines)
