"""Minimal structured output models for meeting intelligence."""

from typing import Any

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """Simple structured action item."""

    description: str = Field(..., min_length=10, description="Action to be taken")
    owner: str | None = Field(None, description="Person responsible")
    due_date: str | None = Field(None, description="Due date if mentioned")


class MeetingIntelligence(BaseModel):
    """
    Hybrid structured output for meeting intelligence.

    Balances structure (for action items) with flexibility (for summary).
    Avoids the timeout issues of complex nested schemas while providing
    type safety for critical data.
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
