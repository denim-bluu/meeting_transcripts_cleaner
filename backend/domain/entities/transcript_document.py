"""Domain entity for transcript document."""

from dataclasses import dataclass

from domain.value_objects.duration import Duration
from models.transcript import VTTEntry


@dataclass
class TranscriptDocument:
    """Domain entity representing a complete transcript document."""

    entries: list[VTTEntry]
    speakers: list[str]
    duration: Duration

    def calculate_quality_metrics(self) -> dict:
        """Calculate transcript quality indicators."""
        total_text = sum(len(entry.text) for entry in self.entries)
        avg_entry_length = total_text / len(self.entries) if self.entries else 0

        return {
            "total_entries": len(self.entries),
            "unique_speakers": len(self.speakers),
            "total_text_length": total_text,
            "avg_entry_length": avg_entry_length,
            "duration_minutes": self.duration.to_minutes(),
        }
