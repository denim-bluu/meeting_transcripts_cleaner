"""Intelligence extraction models - structured outputs for meeting insights."""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import ModelRetry


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

    @field_validator("insights")
    @classmethod
    def validate_insights_quality(cls, v: list[str]) -> list[str]:
        """Validate that insights have speaker attribution and sufficient detail."""
        if not v:
            raise ModelRetry(
                "No insights provided. Extract 5-12 important statements from the conversation."
            )

        # Check for average insight length (should be substantial)
        avg_length = sum(len(insight) for insight in v) / len(v) if v else 0
        if avg_length < 25:
            raise ModelRetry(
                "Insights are too brief. Each insight should include WHO said WHAT and WHY it matters. "
                "Example: 'John proposed increasing the budget by 15% for Q3 due to infrastructure costs.'"
            )

        # Check for speaker attribution in at least half the insights
        attributed_count = sum(
            1
            for insight in v
            if any(
                # Look for name patterns or speaker indicators
                word[0].isupper() and len(word) > 2 and word.isalpha()
                for word in insight.split()[:3]  # Check first 3 words for names
            )
        )

        if attributed_count < len(v) // 2:
            raise ModelRetry(
                "Missing speaker attribution. Include WHO said each insight. "
                "Examples: 'Sarah explained...', 'The team agreed...', 'Mike proposed...'"
            )

        return v

    @field_validator("actions")
    @classmethod
    def validate_actions_quality(cls, v: list[str]) -> list[str]:
        """Validate that actions are actually actionable."""
        if not v:
            return v  # Actions are optional

        action_verbs = {
            "will",
            "should",
            "must",
            "need",
            "complete",
            "finish",
            "review",
            "prepare",
            "submit",
            "create",
            "implement",
            "follow",
            "contact",
            "schedule",
            "organize",
            "update",
            "analyze",
            "investigate",
        }

        non_actionable = []
        for action in v:
            action_lower = action.lower()
            if not any(verb in action_lower for verb in action_verbs):
                non_actionable.append(action)

        if non_actionable and len(non_actionable) > len(v) // 2:
            raise ModelRetry(
                f"Actions must be actionable. Include what needs to be done. "
                f"Non-actionable items: {non_actionable[:2]}. "
                f"Use verbs like: will, should, complete, review, prepare, implement."
            )

        return v

    @field_validator("themes")
    @classmethod
    def validate_themes_quality(cls, v: list[str]) -> list[str]:
        """Validate that themes are broad categories, not specific details."""
        if not v:
            raise ModelRetry(
                "No themes provided. Identify 1-3 broad discussion themes."
            )

        # Check that themes are broad (not too specific)
        too_specific = []
        for theme in v:
            # Themes should be 1-3 words and relatively general
            words = theme.split()
            if len(words) > 4 or any(
                # Check for overly specific indicators
                word.lower()
                in [
                    "january",
                    "february",
                    "monday",
                    "tuesday",
                    "specific",
                    "particular",
                ]
                or len(word) > 15  # Very long words might be too specific
                for word in words
            ):
                too_specific.append(theme)

        if too_specific:
            raise ModelRetry(
                f"Themes are too specific: {too_specific}. "
                f"Use broad categories like 'Budget Planning', 'Technical Architecture', 'Project Management'."
            )

        return v


class ActionItem(BaseModel):
    """Simple structured action item."""

    description: str = Field(..., min_length=10, description="Action to be taken")
    owner: str | None = Field(None, description="Person responsible")
    due_date: str | None = Field(None, description="Due date if mentioned")

    @field_validator("description")
    @classmethod
    def validate_description_quality(cls, v: str) -> str:
        """Validate that action item descriptions are actionable and specific."""
        if len(v.strip()) < 10:
            raise ModelRetry(
                "Action item description too short. Provide clear, actionable tasks."
            )

        # Check for action verbs
        action_verbs = {
            "complete",
            "finish",
            "review",
            "prepare",
            "submit",
            "create",
            "implement",
            "follow",
            "contact",
            "schedule",
            "organize",
            "update",
            "analyze",
            "investigate",
            "develop",
            "design",
            "test",
            "deploy",
        }

        v_lower = v.lower()
        if not any(verb in v_lower for verb in action_verbs):
            raise ModelRetry(
                f"Action item must be actionable. Include action verbs like: "
                f"complete, review, prepare, implement, contact, schedule. "
                f"Current: '{v[:50]}...'"
            )

        # Check that it's not too vague
        vague_terms = ["something", "things", "stuff", "everything", "anything"]
        if any(term in v_lower for term in vague_terms):
            raise ModelRetry(
                f"Action item too vague. Be specific about what needs to be done. "
                f"Current: '{v[:50]}...'"
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
        """Validate that summary is comprehensive and well-structured."""
        if len(v.strip()) < 100:
            raise ModelRetry(
                "Summary too brief. Provide a comprehensive summary with executive overview, "
                "key decisions, discussion points, and important quotes."
            )

        # Check for basic markdown structure
        required_sections = ["#", "executive", "decision", "discussion"]
        v_lower = v.lower()
        missing_sections = [
            section for section in required_sections if section not in v_lower
        ]

        if len(missing_sections) > 2:
            raise ModelRetry(
                "Summary missing too many key sections. Include at least 2 of: Executive Summary, Key Decisions, "
                "Discussion by Topic, and Important Quotes. Use proper markdown headers (#)."
            )

        # Check for speaker attribution in summary
        if not any(
            indicator in v_lower
            for indicator in [
                "said",
                "mentioned",
                "explained",
                "proposed",
                "suggested",
                "agreed",
                "noted",
            ]
        ):
            raise ModelRetry(
                "Summary lacks speaker attribution. Include WHO said or proposed key points. "
                "Use phrases like 'John mentioned', 'Sarah explained', 'The team agreed'."
            )

        return v

    @field_validator("action_items")
    @classmethod
    def validate_action_items_quality(cls, v: list[ActionItem]) -> list[ActionItem]:
        """Validate that action items are meaningful and well-distributed."""
        if not v:
            return v  # Action items are optional, but if present should be quality

        # Check for owner distribution (shouldn't all be unassigned)
        assigned_count = sum(1 for item in v if item.owner is not None)
        if len(v) > 3 and assigned_count == 0:
            raise ModelRetry(
                "Multiple action items without owners. Try to identify who is responsible "
                "for each task from the meeting discussion."
            )

        # Check for variety in action types (not all the same verb)
        descriptions = [item.description.lower() for item in v]
        first_words = [desc.split()[0] for desc in descriptions if desc.split()]
        if len(set(first_words)) == 1 and len(v) > 3:
            raise ModelRetry(
                "Action items too similar. Vary the action types: review, prepare, "
                "implement, contact, schedule, etc."
            )

        return v
