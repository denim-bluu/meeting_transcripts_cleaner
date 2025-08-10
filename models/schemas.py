"""
Pydantic models for structured output in the dual-agent transcript cleaning system.

These models define the data structures used throughout the pipeline for:
- Document processing and segmentation
- Cleaning agent output
- Review agent decisions
- Confidence-based categorization
- Overall processing status
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ProcessingStatusEnum(str, Enum):
    """Enumeration of processing statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SegmentCategoryEnum(str, Enum):
    """Enumeration of segment categories based on confidence."""

    AUTO_ACCEPT = "auto_accept"  # >95% confidence
    QUICK_REVIEW = "quick_review"  # 85-95% confidence
    DETAILED_REVIEW = "detailed_review"  # 70-85% confidence
    AI_FLAGGED = "ai_flagged"  # <70% confidence


class ReviewDecisionEnum(str, Enum):
    """Enumeration of review decisions."""

    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"


class DocumentSegment(BaseModel):
    """A segment of the original document for processing."""

    id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique segment identifier"
    )
    content: str = Field(description="Original segment text content")
    token_count: int = Field(gt=0, description="Number of tokens in the segment")
    start_index: int = Field(
        ge=0, description="Character start position in original document"
    )
    end_index: int = Field(
        gt=0, description="Character end position in original document"
    )
    sequence_number: int = Field(ge=1, description="Order of segment in document")

    @field_validator("end_index")
    @classmethod
    def validate_end_after_start(cls, v: int, info) -> int:
        """Ensure end_index is greater than start_index."""
        if "start_index" in info.data and v <= info.data["start_index"]:
            raise ValueError("end_index must be greater than start_index")
        return v


class CleaningResult(BaseModel):
    """Structured output from the cleaning agent."""

    segment_id: str = Field(description="ID of the segment being cleaned")
    cleaned_text: str = Field(description="The cleaned transcript text")
    changes_made: list[str] = Field(
        default_factory=list, description="List of specific changes applied to the text"
    )
    processing_time_ms: float | None = Field(
        None, ge=0, description="Time taken to process this segment in milliseconds"
    )
    model_used: str | None = Field(None, description="AI model used for cleaning")

    @field_validator("changes_made")
    @classmethod
    def validate_changes_made(cls, v: list[str]) -> list[str]:
        """Ensure all change descriptions are non-empty strings."""
        return [change.strip() for change in v if change.strip()]


class ReviewDecision(BaseModel):
    """Structured output from the review agent."""

    segment_id: str = Field(description="ID of the segment being reviewed")
    decision: ReviewDecisionEnum = Field(description="Review decision")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the review decision (0.0-1.0)"
    )
    preservation_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Score for meaning preservation assessment (0.0-1.0)",
    )
    issues_found: list[str] = Field(
        default_factory=list,
        description="Specific issues identified in the cleaned text",
    )
    suggested_corrections: str | None = Field(
        None, description="Suggested corrections if decision is 'modify'"
    )
    reasoning: str = Field(description="Detailed reasoning for the decision")
    processing_time_ms: float | None = Field(
        None, ge=0, description="Time taken to review this segment in milliseconds"
    )
    model_used: str | None = Field(None, description="AI model used for review")

    @field_validator("issues_found")
    @classmethod
    def validate_issues_found(cls, v: list[str]) -> list[str]:
        """Ensure all issue descriptions are non-empty strings."""
        return [issue.strip() for issue in v if issue.strip()]

    @model_validator(mode="after")
    def validate_modify_decision(self) -> "ReviewDecision":
        """Ensure suggested_corrections is provided when decision is 'modify'."""
        if (
            self.decision == ReviewDecisionEnum.MODIFY
            and not self.suggested_corrections
        ):
            raise ValueError(
                "suggested_corrections must be provided when decision is 'modify'"
            )
        return self


class SegmentCategory(BaseModel):
    """Categorization result based on confidence scores."""

    segment_id: str = Field(description="ID of the categorized segment")
    category: SegmentCategoryEnum = Field(description="Category based on confidence")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence score for this segment"
    )
    categorization_reason: str = Field(
        description="Explanation of why this category was assigned"
    )
    requires_human_review: bool = Field(
        description="Whether this segment requires human review"
    )
    priority_level: int = Field(
        ge=1, le=5, description="Priority level for review (1=highest, 5=lowest)"
    )


class ProcessingStatus(BaseModel):
    """Overall processing status for a document."""

    document_id: str = Field(description="Unique document identifier")
    status: ProcessingStatusEnum = Field(description="Current processing status")
    total_segments: int = Field(ge=0, description="Total number of segments")
    processed_segments: int = Field(ge=0, description="Number of processed segments")
    failed_segments: int = Field(ge=0, description="Number of failed segments")

    # Category breakdowns
    auto_accept_count: int = Field(ge=0, description="Segments auto-accepted")
    quick_review_count: int = Field(ge=0, description="Segments needing quick review")
    detailed_review_count: int = Field(
        ge=0, description="Segments needing detailed review"
    )
    ai_flagged_count: int = Field(ge=0, description="Segments flagged by AI")

    # Timing information
    started_at: datetime = Field(description="Processing start timestamp")
    completed_at: datetime | None = Field(
        None, description="Processing completion timestamp"
    )
    estimated_completion: datetime | None = Field(
        None, description="Estimated completion time"
    )

    # Error tracking
    errors: list[str] = Field(default_factory=list, description="Processing errors")
    warnings: list[str] = Field(default_factory=list, description="Processing warnings")

    @field_validator("processed_segments", "failed_segments")
    @classmethod
    def validate_segment_counts(cls, v: int, info) -> int:
        """Ensure processed and failed segments don't exceed total."""
        if "total_segments" in info.data and v > info.data["total_segments"]:
            raise ValueError("Count cannot exceed total_segments")
        return v

    @model_validator(mode="after")
    def validate_segment_accounting(self) -> "ProcessingStatus":
        """Ensure segment counts add up correctly."""
        category_total = (
            self.auto_accept_count
            + self.quick_review_count
            + self.detailed_review_count
            + self.ai_flagged_count
        )

        if category_total > self.processed_segments:
            raise ValueError("Category counts cannot exceed processed segments")

        if self.processed_segments + self.failed_segments > self.total_segments:
            raise ValueError("Processed + failed cannot exceed total segments")

        return self

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_segments == 0:
            return 0.0
        return (
            (self.processed_segments + self.failed_segments) / self.total_segments * 100
        )

    @property
    def success_rate(self) -> float:
        """Calculate success rate (excluding failed segments)."""
        total_attempted = self.processed_segments + self.failed_segments
        if total_attempted == 0:
            return 0.0
        return self.processed_segments / total_attempted * 100


class TranscriptDocument(BaseModel):
    """Complete transcript document with all processing information."""

    id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique document identifier"
    )
    filename: str = Field(description="Original filename")
    original_content: str = Field(description="Original document content")
    file_size_bytes: int = Field(gt=0, description="File size in bytes")
    content_type: str = Field(description="MIME type of the file")

    # Processing results
    segments: list[DocumentSegment] = Field(
        default_factory=list, description="Document segments for processing"
    )
    cleaning_results: dict[str, CleaningResult] = Field(
        default_factory=dict, description="Cleaning results keyed by segment_id"
    )
    review_decisions: dict[str, ReviewDecision] = Field(
        default_factory=dict, description="Review decisions keyed by segment_id"
    )
    segment_categories: dict[str, SegmentCategory] = Field(
        default_factory=dict, description="Segment categories keyed by segment_id"
    )

    # Metadata
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the document was uploaded (UTC)",
    )
    processing_status: ProcessingStatus | None = Field(None)

    # Configuration used
    max_tokens_per_segment: int = Field(default=500, gt=0)
    cleaning_model: str | None = Field(None)
    review_model: str | None = Field(None)

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens across all segments."""
        return sum(segment.token_count for segment in self.segments)

    @property
    def final_cleaned_content(self) -> str:
        """Reconstruct the final cleaned content from all segments."""
        if not self.segments:
            return self.original_content

        # Sort segments by sequence number
        sorted_segments = sorted(self.segments, key=lambda s: s.sequence_number)
        final_parts = []

        for segment in sorted_segments:
            cleaning_result = self.cleaning_results.get(segment.id)
            review_decision = self.review_decisions.get(segment.id)

            # Use the final approved version
            if review_decision:
                if review_decision.decision == ReviewDecisionEnum.ACCEPT:
                    final_parts.append(
                        cleaning_result.cleaned_text
                        if cleaning_result
                        else segment.content
                    )
                elif review_decision.decision == ReviewDecisionEnum.MODIFY:
                    final_parts.append(
                        review_decision.suggested_corrections or segment.content
                    )
                else:  # REJECT
                    final_parts.append(segment.content)  # Keep original
            elif cleaning_result:
                final_parts.append(cleaning_result.cleaned_text)
            else:
                final_parts.append(segment.content)  # Fallback to original

        return " ".join(final_parts)

    @property
    def processing_summary(self) -> dict[str, int | float | str]:
        """Generate a summary of processing results."""
        total_segments = len(self.segments)
        processed = len(self.cleaning_results)
        reviewed = len(self.review_decisions)

        if total_segments == 0:
            return {"status": "no_segments", "total": 0}

        # Calculate average confidence from review decisions
        avg_confidence = 0.0
        if self.review_decisions:
            avg_confidence = sum(
                decision.confidence for decision in self.review_decisions.values()
            ) / len(self.review_decisions)

        return {
            "total_segments": total_segments,
            "processed_segments": processed,
            "reviewed_segments": reviewed,
            "completion_rate": (processed / total_segments * 100)
            if total_segments > 0
            else 0,
            "review_rate": (reviewed / processed * 100) if processed > 0 else 0,
            "average_confidence": round(avg_confidence, 3),
            "total_tokens": self.total_tokens,
        }
