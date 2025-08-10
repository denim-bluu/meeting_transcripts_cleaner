"""
Confidence Categorizer for progressive review categorization.

This module categorizes segments based on confidence scores to enable
progressive review with different levels of human oversight.
"""

from typing import Any

import structlog

from config import get_confidence_thresholds
from models.schemas import (
    CleaningResult,
    SegmentCategory,
    SegmentCategoryEnum,
)
from utils.config_manager import get_merged_confidence_thresholds

logger = structlog.get_logger(__name__)


class ConfidenceCategorizer:
    """Categorizes segments based on confidence scores for progressive review."""

    def __init__(self) -> None:
        """Initialize the categorizer with confidence thresholds."""
        # Use merged config that includes session overrides
        try:
            confidence_thresholds = get_merged_confidence_thresholds()
        except Exception:
            # Fallback to base config if overrides fail
            confidence_thresholds = get_confidence_thresholds()

        self.auto_accept_threshold = confidence_thresholds.auto_accept_threshold
        self.quick_review_threshold = confidence_thresholds.quick_review_threshold
        self.detailed_review_threshold = confidence_thresholds.detailed_review_threshold

        logger.info(
            "Confidence categorizer initialized",
            # Key identifier (flat)
            phase="categorizer_init",
            # Thresholds configuration (grouped)
            thresholds={
                "auto_accept_threshold": self.auto_accept_threshold,
                "quick_review_threshold": self.quick_review_threshold,
                "detailed_review_threshold": self.detailed_review_threshold
            }
        )

    def categorize_cleaning_result(
        self,
        cleaning_result: CleaningResult,
        additional_factors: dict[str, Any] | None = None,
    ) -> SegmentCategory:
        """
        Categorize a single cleaning result with conservative default confidence.
        This is a simplified version for basic categorization without review decision.

        Args:
            cleaning_result: The cleaning result to categorize
            additional_factors: Optional additional factors (unused in simplified version)

        Returns:
            SegmentCategory with conservative category assignment
        """
        # Use conservative default confidence for quick review
        default_confidence = 0.8
        segment_id = cleaning_result.segment_id

        # Get base category based on default confidence
        category, reason = self._get_base_category(default_confidence)

        # Conservative approach - demote to quick review if many changes
        if len(cleaning_result.changes_made) > 3:
            category = SegmentCategoryEnum.QUICK_REVIEW
            reason = f"Conservative categorization due to {len(cleaning_result.changes_made)} changes"

        # Determine review requirement
        requires_review = category != SegmentCategoryEnum.AUTO_ACCEPT
        priority = self._get_base_priority(category)

        logger.debug(
            "Categorized segment",
            # Key identifier (flat)
            segment_id=segment_id,
            phase="categorization",
            # Categorization results (grouped)
            categorization={
                "category": category.value,
                "default_confidence": default_confidence
            }
        )

        return SegmentCategory(
            segment_id=segment_id,
            category=category,
            confidence=default_confidence,
            categorization_reason=reason,
            requires_human_review=requires_review,
            priority_level=priority,
        )

    def _get_base_category(self, confidence: float) -> tuple[SegmentCategoryEnum, str]:
        """
        Get base category based purely on confidence threshold.

        Args:
            confidence: Confidence score

        Returns:
            Tuple of (category, reason)
        """
        if confidence > self.auto_accept_threshold:
            return (
                SegmentCategoryEnum.AUTO_ACCEPT,
                f"High confidence ({confidence:.3f}) exceeds auto-accept threshold ({self.auto_accept_threshold:.2f})",
            )

        elif confidence >= self.quick_review_threshold:
            return (
                SegmentCategoryEnum.QUICK_REVIEW,
                f"Medium confidence ({confidence:.3f}) requires quick review",
            )

        elif confidence >= self.detailed_review_threshold:
            return (
                SegmentCategoryEnum.DETAILED_REVIEW,
                f"Lower confidence ({confidence:.3f}) requires detailed review",
            )

        else:
            return (
                SegmentCategoryEnum.AI_FLAGGED,
                f"Low confidence ({confidence:.3f}) flagged for special attention",
            )

    def _get_base_priority(self, category: SegmentCategoryEnum) -> int:
        """
        Get base priority level for a category.

        Args:
            category: The segment category

        Returns:
            Priority level (1=highest, 5=lowest)
        """
        priority_map = {
            SegmentCategoryEnum.AI_FLAGGED: 1,  # Highest priority
            SegmentCategoryEnum.DETAILED_REVIEW: 2,  # High priority
            SegmentCategoryEnum.QUICK_REVIEW: 3,  # Medium priority
            SegmentCategoryEnum.AUTO_ACCEPT: 5,  # Lowest priority (no review needed)
        }
        return priority_map.get(category, 3)
