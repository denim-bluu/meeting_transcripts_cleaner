"""Duration value object with formatting."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Duration:
    """Duration in seconds with formatting methods."""

    seconds: float

    def to_minutes(self) -> float:
        return self.seconds / 60

    def to_formatted_string(self) -> str:
        minutes = int(self.seconds // 60)
        seconds = int(self.seconds % 60)
        return f"{minutes}:{seconds:02d}"
