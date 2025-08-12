"""Pydantic models for agent I/O."""

from pydantic import BaseModel, Field


class CleaningResult(BaseModel):
    """Structured output from transcript cleaning - validates cleaned text, confidence score, and change tracking."""

    cleaned_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    changes_made: list[str]


class ReviewResult(BaseModel):
    """Structured output from quality review - validates quality score, issues list, and acceptance decision."""

    quality_score: float = Field(ge=0.0, le=1.0)
    issues: list[str]
    accept: bool  # True if quality_score >= 0.7
