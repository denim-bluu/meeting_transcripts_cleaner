"""
Shared validation utilities for the dual-agent transcript cleaning system.

This module contains validation functions that are used by both the CleaningAgent
and ReviewAgent to ensure consistent validation logic and reduce code duplication.
"""

import structlog

from models.schemas import CleaningResult, DocumentSegment, ReviewDecision

logger = structlog.get_logger(__name__)


def validate_cleaning_result(
    original_segment: DocumentSegment, result: CleaningResult
) -> None:
    """
    Validate that the cleaning result is reasonable.

    Args:
        original_segment: Original segment that was cleaned
        result: Cleaning result to validate

    Raises:
        ValueError: If the result fails validation
    """
    # Check that cleaned text exists and isn't empty
    if not result.cleaned_text or not result.cleaned_text.strip():
        raise ValueError("Cleaned text is empty")

    # Validate that changes_made is populated if there are significant changes
    if (
        len(result.cleaned_text.strip()) != len(original_segment.content.strip())
        and not result.changes_made
    ):
        logger.warning(
            "Significant text changes without documented changes",
            segment_id=original_segment.id,
            phase="validation",
            warning_type="undocumented_changes",
        )

    # Check that cleaned text isn't dramatically different in length
    original_len = len(original_segment.content)
    cleaned_len = len(result.cleaned_text)

    # Allow up to 50% change in length
    if not validate_segment_lengths(original_len, cleaned_len, 0.5):
        logger.warning(
            "Significant length change detected",
            segment_id=original_segment.id,
            original_length=original_len,
            cleaned_length=cleaned_len,
            length_ratio=cleaned_len / original_len if original_len > 0 else 0,
            phase="validation",
            warning_type="length_change",
        )

    # Check segment ID matches
    if result.segment_id != original_segment.id:
        raise ValueError(
            f"Segment ID mismatch: {result.segment_id} vs {original_segment.id}"
        )


def validate_review_decision(
    original_segment: DocumentSegment,
    cleaning_result: CleaningResult,
    decision: ReviewDecision,
) -> None:
    """
    Validate that the review decision is reasonable.

    Args:
        original_segment: Original segment
        cleaning_result: Cleaning result that was reviewed
        decision: Review decision to validate

    Raises:
        ValueError: If the decision fails validation
    """
    # Check confidence score is in valid range
    if not (0.0 <= decision.confidence <= 1.0):
        raise ValueError(f"Invalid confidence score: {decision.confidence}")

    # Check preservation score is in valid range
    if not (0.0 <= decision.preservation_score <= 1.0):
        raise ValueError(f"Invalid preservation score: {decision.preservation_score}")

    # Ensure segment ID matches (fix if AI returned wrong ID)
    if decision.segment_id != original_segment.id:
        logger.warning(
            "AI returned wrong segment_id, correcting",
            ai_returned_id=decision.segment_id,
            correct_id=original_segment.id,
            phase="validation",
            warning_type="incorrect_segment_id",
        )
        decision.segment_id = original_segment.id

    # Check that reasoning exists
    if not decision.reasoning or not decision.reasoning.strip():
        raise ValueError("Review decision must include reasoning")

    # Check that modify decisions include suggested corrections
    if decision.decision == "modify" and not decision.suggested_corrections:
        raise ValueError("Modify decisions must include suggested_corrections")

    # Validate suggested corrections are different from original
    if (
        decision.decision == "modify"
        and decision.suggested_corrections
        and decision.suggested_corrections.strip()
        == cleaning_result.cleaned_text.strip()
    ):
        logger.warning(
            "Modify decision has identical corrections to cleaned text",
            segment_id=original_segment.id,
            phase="validation",
            warning_type="redundant_corrections",
        )


def validate_segment_lengths(
    original_len: int, cleaned_len: int, threshold: float = 0.5
) -> bool:
    """
    Check if text length change is within acceptable bounds.

    Args:
        original_len: Length of original text
        cleaned_len: Length of cleaned text
        threshold: Minimum ratio threshold (default 0.5 = 50% change allowed)

    Returns:
        True if length change is within acceptable bounds, False otherwise
    """
    if original_len == 0:
        return cleaned_len == 0  # Both should be empty

    length_ratio = cleaned_len / original_len
    return threshold <= length_ratio <= (1.0 / threshold)


def validate_segment_id_match(expected_id: str, actual_id: str) -> None:
    """
    Validate that segment IDs match as expected.

    Args:
        expected_id: Expected segment ID
        actual_id: Actual segment ID from AI response

    Raises:
        ValueError: If segment IDs don't match
    """
    if expected_id != actual_id:
        raise ValueError(
            f"Segment ID mismatch: expected {expected_id}, got {actual_id}"
        )
