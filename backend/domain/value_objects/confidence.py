"""Confidence value object with validation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Confidence:
    """Confidence score between 0.0 and 1.0."""

    value: float

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.value}"
            )
