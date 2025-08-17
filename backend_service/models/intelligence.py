"""Intelligence extraction models - structured outputs for meeting insights."""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import ModelRetry


class ChunkInsights(BaseModel):
    """Universal extraction model for any meeting type - max 5 fields to avoid timeouts."""

    insights: list[str] = Field(
        ...,
        min_length=1,  # Dramatically reduced from 5 to 1
        max_length=25,  # Keep max for performance
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

    @field_validator("insights")
    @classmethod
    def validate_insights_quality(cls, v: list[str]) -> list[str]:
        """Minimal validation - just check insights exist."""
        if not v:
            raise ModelRetry(
                "No insights provided. Extract important statements from the conversation."
            )
        
        return v

    @field_validator("actions")
    @classmethod
    def validate_actions_quality(cls, v: list[str]) -> list[str]:
        """Minimal validation - accept any actions."""
        return v  # Actions are optional and any format is acceptable

    @field_validator("themes")
    @classmethod
    def validate_themes_quality(cls, v: list[str]) -> list[str]:
        """Minimal validation - just check themes exist."""
        if not v:
            raise ModelRetry(
                "No themes provided. Identify discussion themes."
            )
        
        return v


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
            raise ModelRetry(
                "Action item description cannot be empty."
            )
        
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
            raise ModelRetry(
                "Summary cannot be empty. Provide any meaningful content."
            )
        
        return v

    @field_validator("action_items")
    @classmethod
    def validate_action_items_quality(cls, v: list[ActionItem]) -> list[ActionItem]:
        """Minimal validation - accept any action items."""
        return v  # Action items are optional and any format is acceptable
