"""Intelligence extraction models - structured outputs for meeting insights."""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import ModelRetry


class ActionItem(BaseModel):
    """Simple structured action item."""

    description: str = Field(..., min_length=3, description="Action to be taken")
    owner: str | None = Field(None, description="Person responsible")
    due_date: str | None = Field(None, description="Due date if mentioned")

    @field_validator("description")
    @classmethod
    def validate_description_quality(cls, v: str) -> str:
        """Minimal validation - just check it's not empty."""
        if len(v.strip()) < 3:
            raise ModelRetry("Action item description cannot be empty.")

        return v


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

    @field_validator("summary")
    @classmethod
    def validate_summary_quality(cls, v: str) -> str:
        """Minimal validation - only check if summary exists and isn't empty."""
        if len(v.strip()) < 10:  # Very minimal requirement
            raise ModelRetry("Summary cannot be empty. Provide any meaningful content.")

        return v

    @field_validator("action_items")
    @classmethod
    def validate_action_items_quality(cls, v: list[ActionItem]) -> list[ActionItem]:
        """Minimal validation - accept any action items."""
        return v  # Action items are optional and any format is acceptable
