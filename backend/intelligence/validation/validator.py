"""Validation service implementing the design document gates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import structlog

from backend.intelligence.models import (
    AggregationAgentPayload,
    IntermediateSummary,
    ValidationIssue,
    ValidationResult,
)


class ValidationService:
    """Runs structured validation checks across the pipeline outputs."""

    def __init__(self) -> None:
        self._logger = structlog.get_logger(__name__)

    def evaluate(
        self,
        summaries: Sequence[IntermediateSummary],
        aggregation_payload: AggregationAgentPayload,
    ) -> ValidationResult:
        """Execute validation gates and calculate confidence adjustments."""
        issues: list[ValidationIssue] = []
        penalty = 0.0

        issues.extend(self._chunk_level_checks(summaries))
        issues.extend(self._aggregation_checks(aggregation_payload))
        issues.extend(self._final_output_checks(aggregation_payload))

        for issue in issues:
            if issue.level == "error":
                penalty += 0.2
            elif issue.level == "warning":
                penalty += 0.05

        passed = not any(issue.level == "error" for issue in issues)
        confidence_adjustment = -min(penalty, 0.6)  # cap penalty impact

        self._logger.info(
            "Validation completed",
            issues=len(issues),
            passed=passed,
            confidence_adjustment=confidence_adjustment,
        )

        return ValidationResult(
            passed=passed,
            issues=issues,
            confidence_adjustment=confidence_adjustment,
        )

    def _chunk_level_checks(
        self,
        summaries: Sequence[IntermediateSummary],
    ) -> list[ValidationIssue]:
        """Chunk-level validation derived from design doc."""
        issues: list[ValidationIssue] = []

        for summary in summaries:
            for action in summary.action_items:
                if not action.owner:
                    issues.append(
                        ValidationIssue(
                            level="warning",
                            message="Action item without clear owner",
                            related_chunks=[summary.chunk_id],
                        )
                    )
            for decision in summary.decisions:
                if not decision.rationale:
                    issues.append(
                        ValidationIssue(
                            level="info",
                            message="Decision missing rationale",
                            related_chunks=[summary.chunk_id],
                        )
                    )
        return issues

    def _aggregation_checks(
        self,
        aggregation_payload: AggregationAgentPayload,
    ) -> list[ValidationIssue]:
        """Aggregation-stage validation."""
        issues: list[ValidationIssue] = []

        for area in aggregation_payload.key_areas:
            if len(area.supporting_chunks) < 1:
                issues.append(
                    ValidationIssue(
                        level="error",
                        message=f"Key area '{area.title}' missing supporting chunks",
                    )
                )
            if not area.decisions:
                issues.append(
                    ValidationIssue(
                        level="warning",
                        message=f"Key area '{area.title}' lacks explicit decisions",
                        related_chunks=area.supporting_chunks,
                    )
                )

        if not aggregation_payload.key_areas:
            issues.append(
                ValidationIssue(
                    level="error",
                    message="Aggregation produced no key areas",
                )
            )

        return issues

    def _final_output_checks(
        self,
        aggregation_payload: AggregationAgentPayload,
    ) -> list[ValidationIssue]:
        """Final output validation before returning intelligence."""
        issues: list[ValidationIssue] = []

        descriptions = [
            item.description.strip().lower()
            for item in aggregation_payload.consolidated_action_items
        ]
        duplicates = [desc for desc, count in Counter(descriptions).items() if count > 1]
        if duplicates:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message=f"Duplicate action items detected: {', '.join(duplicates)}",
                )
            )

        if not aggregation_payload.consolidated_action_items:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message="No action items extracted for the meeting.",
                )
            )

        if not aggregation_payload.timeline_events:
            issues.append(
                ValidationIssue(
                    level="info",
                    message="Timeline events missing; temporal cues may be degraded.",
                )
            )

        return issues
