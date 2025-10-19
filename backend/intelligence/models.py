"""Intelligence extraction models and shared schemas for meeting insights."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import ModelRetry


class LinkType(str, Enum):
    """Types of cross-chunk conversation references."""

    FOLLOW_UP = "follow_up"
    CONTRAST = "contrast"
    SUPPORT = "support"
    CLARIFICATION = "clarification"
    CALLBACK = "callback"


class Concept(BaseModel):
    """Key concept introduced or elaborated in a chunk."""

    title: str = Field(..., min_length=3)
    detail: str | None = Field(
        None, description="Supporting explanation or elaboration, if provided"
    )
    importance: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Relative importance within the chunk (0-1 scale)",
    )


class Decision(BaseModel):
    """Structured decision statement with rationale."""

    statement: str = Field(..., min_length=5)
    rationale: str | None = Field(None)
    decided_by: str | None = Field(
        None, description="Speaker or role responsible for the decision"
    )
    status: Literal["approved", "rejected", "pending"] | None = Field(
        None, description="Decision outcome if explicitly stated"
    )
    affected_areas: list[str] = Field(default_factory=list)
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence the decision was confirmed"
    )

    @field_validator("statement")
    @classmethod
    def validate_statement(cls, value: str) -> str:
        if len(value.strip()) < 5:
            raise ModelRetry("Decision statement cannot be empty.")
        return value


class ConversationLink(BaseModel):
    """Reference to prior or subsequent discussion."""

    referenced_chunk_id: int | None = Field(
        None, description="Chunk id being referenced (if known)"
    )
    reference_text: str = Field(..., min_length=3)
    link_type: LinkType = Field(
        LinkType.FOLLOW_UP,
        description="Relationship between current and referenced chunk",
    )


class ActionItem(BaseModel):
    """Structured action item with ownership and timing context."""

    description: str = Field(..., min_length=3, description="Action to be taken")
    owner: str | None = Field(None, description="Person responsible")
    due_date: str | None = Field(None, description="Due date if mentioned")
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence the action item was clearly committed",
    )

    @field_validator("description")
    @classmethod
    def validate_description_quality(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ModelRetry("Action item description cannot be empty.")
        return value


class ChunkProcessingInsight(BaseModel):
    """Lightweight summary text for quick human traceability."""

    headline: str = Field(..., min_length=5)
    details: str = Field(..., min_length=5)


class ChunkAgentPayload(BaseModel):
    """Schema expected from the chunk processing agent."""

    narrative_summary: str = Field(
        ..., min_length=10, description="Narrative summary for the chunk"
    )
    key_concepts: list[Concept] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    conversation_links: list[ConversationLink] = Field(default_factory=list)
    continuation_flag: bool = Field(False)
    insights: list[ChunkProcessingInsight] = Field(default_factory=list)
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Agent-rated confidence in the extracted data",
    )


class IntermediateSummary(BaseModel):
    """Chunk-level structured output prior to aggregation."""

    chunk_id: int = Field(..., ge=0)
    time_range: str = Field(..., description="Original time span from the transcript")
    speaker: str = Field(..., min_length=1)
    speaker_role: str | None = Field(None, description="Derived authority role label")
    narrative_summary: str = Field(
        ..., description="Short natural language summary of the chunk"
    )
    key_concepts: list[Concept] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    conversation_links: list[ConversationLink] = Field(default_factory=list)
    continuation_flag: bool = Field(
        False, description="True if the chunk likely continues from a prior chunk"
    )
    insights: list[ChunkProcessingInsight] = Field(default_factory=list)
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score from chunk agent"
    )


class KeyArea(BaseModel):
    """Aggregated thematic cluster spanning multiple chunks."""

    title: str = Field(..., min_length=3)
    summary: str = Field(..., description="Narrative describing how the theme evolved")
    bullet_points: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    supporting_chunks: list[int] = Field(default_factory=list)
    temporal_span: str | None = Field(
        None, description="Time span in the meeting covering the cluster"
    )
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence that the cluster is coherent and complete",
    )


class AggregationArtifacts(BaseModel):
    """Additional structures produced during aggregation."""

    timeline_events: list[str] = Field(default_factory=list)
    unresolved_topics: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    """Represents a validation finding."""

    level: Literal["error", "warning", "info"] = Field("info")
    message: str = Field(..., min_length=5)
    related_chunks: list[int] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Outcome from automated validation checks."""

    passed: bool = Field(True)
    issues: list[ValidationIssue] = Field(default_factory=list)
    confidence_adjustment: float = Field(
        0.0,
        ge=-1.0,
        le=1.0,
        description="Adjustment applied to pipeline confidence (negative reduces)",
    )


class AggregationAgentPayload(BaseModel):
    """Schema expected from the aggregation agent."""

    summary_markdown: str = Field(..., min_length=20)
    key_areas: list[KeyArea] = Field(default_factory=list)
    consolidated_action_items: list[ActionItem] = Field(default_factory=list)
    timeline_events: list[str] = Field(default_factory=list)
    unresolved_topics: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence rating for the aggregated output",
    )


class ConversationState(BaseModel):
    """State container passed between chunk processors to maintain context."""

    last_topic: str | None = None
    key_decisions: dict[str, Decision] = Field(default_factory=dict)
    unresolved_items: list[str] = Field(default_factory=list)
    last_speaker: str | None = None


class MeetingIntelligence(BaseModel):
    """
    Final intelligence output - hybrid structured approach.

    Maintains backward compatibility with existing summary/action items while
    exposing richer structured artifacts for the new pipeline.
    """

    summary: str = Field(
        ..., description="Markdown formatted meeting summary with topic headers"
    )
    action_items: list[ActionItem] = Field(
        default_factory=list, description="Structured action items"
    )
    key_areas: list[KeyArea] = Field(
        default_factory=list,
        description="Aggregated thematic clusters produced during synthesis",
    )
    aggregation_artifacts: AggregationArtifacts | None = Field(
        None, description="Supplementary aggregation details and validation notes"
    )
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Overall confidence for downstream display"
    )
    processing_stats: dict[str, Any] = Field(
        default_factory=dict, description="Processing metadata"
    )

    @field_validator("summary")
    @classmethod
    def validate_summary_quality(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ModelRetry("Summary cannot be empty. Provide any meaningful content.")
        return value

    @field_validator("action_items")
    @classmethod
    def validate_action_items_quality(cls, value: list[ActionItem]) -> list[ActionItem]:
        return value
