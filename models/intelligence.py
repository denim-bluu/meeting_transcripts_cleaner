"""Intelligence extraction models - structured outputs for meeting insights."""

from typing import Any

from pydantic import BaseModel, Field


class ChunkInsights(BaseModel):
    """Universal extraction model for any meeting type - max 5 fields to avoid timeouts."""

    insights: list[str] = Field(
        ...,
        min_length=5,
        max_length=12,
        description="Important statements with speaker attribution and context",
    )
    importance: int = Field(
        ...,
        ge=1,
        le=10,
        description="Importance rating based on decisions, commitments, strategic value",
    )
    themes: list[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="Broad themes discussed, not micro-topics",
    )
    actions: list[str] = Field(
        default_factory=list, description="Action items with owner if mentioned"
    )


class ActionItem(BaseModel):
    """Simple structured action item."""

    description: str = Field(..., min_length=10, description="Action to be taken")
    owner: str | None = Field(None, description="Person responsible")
    due_date: str | None = Field(None, description="Due date if mentioned")


class MeetingIntelligence(BaseModel):
    """
    Final intelligence output - hybrid structured approach.

    Balances structure (for action items) with flexibility (for summary).
    Only 3 top-level fields to avoid timeout issues.
    """

    summary: str = Field(
        ..., description="Markdown formatted meeting summary with topic headers"
    )
    action_items: list[ActionItem] = Field(
        default_factory=list, description="Structured action items"
    )
    processing_stats: dict[str, Any] = Field(
        default_factory=dict, description="Processing metadata"
    )
