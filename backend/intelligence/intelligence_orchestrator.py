"""Meeting intelligence orchestrator implementing the structured pipeline."""

from __future__ import annotations

import asyncio
import time

import structlog

from backend.config import settings
from backend.intelligence.aggregation import SemanticAggregator
from backend.intelligence.chunk_processing import ChunkProcessor
from backend.intelligence.models import (
    AggregationAgentPayload,
    AggregationArtifacts,
    IntermediateSummary,
    MeetingIntelligence,
    ValidationResult,
)
from backend.intelligence.validation import ValidationService
from backend.transcript.models import VTTChunk
from shared.types import ProgressCallback

logger = structlog.get_logger(__name__)


class IntelligenceOrchestrator:
    """Orchestrates the multi-stage meeting intelligence pipeline."""

    def __init__(self) -> None:
        self._chunk_processor = ChunkProcessor()
        self._chunk_concurrency = settings.max_concurrency
        self._aggregator = SemanticAggregator()
        self._validator = ValidationService()
        logger.info(
            "IntelligenceOrchestrator initialized",
            chunk_model=settings.chunk_model,
            aggregation_model=settings.aggregation_model,
            chunk_processor_concurrency=self._chunk_concurrency,
        )

    async def process_meeting(
        self,
        chunks: list[VTTChunk],
    ) -> MeetingIntelligence:
        """Run the structured multi-stage pipeline to generate meeting intelligence."""
        start_time = time.time()
        total_chunks = len(chunks)
        logger.info(
            "Structured intelligence pipeline starting",
            vtt_chunks=total_chunks,
        )

        # Stage 1: Chunk processing (0% - 50%)
        stage1_start = time.time()
        summaries, conversation_state = await self._chunk_processor.process_chunks(
            chunks,
        )
        stage1_time = int((time.time() - stage1_start) * 1000)
        logger.info(
            "Chunk processing completed",
            summary_count=len(summaries),
            stage_time_ms=stage1_time,
        )

        # Stage 2: Aggregation (50% - 80%)
        stage2_start = time.time()
        aggregation_payload = await self._aggregator.aggregate(
            summaries,
            conversation_state=conversation_state,
        )
        stage2_time = int((time.time() - stage2_start) * 1000)
        logger.info(
            "Aggregation completed",
            key_area_count=len(aggregation_payload.key_areas),
            timeline_event_count=len(aggregation_payload.timeline_events),
            stage_time_ms=stage2_time,
        )

        aggregation_artifacts = self._aggregator.build_artifacts(aggregation_payload)

        # Stage 3: Validation (80% - 90%)
        stage3_start = time.time()
        validation_result = self._validator.evaluate(summaries, aggregation_payload)
        stage3_time = int((time.time() - stage3_start) * 1000)
        logger.info(
            "Validation completed",
            issues=len(validation_result.issues),
            passed=validation_result.passed,
            stage_time_ms=stage3_time,
        )

        intelligence = self._build_meeting_intelligence(
            aggregation_payload=aggregation_payload,
            aggregation_artifacts=aggregation_artifacts,
            validation_result=validation_result,
            summaries=summaries,
        )

        total_time = int((time.time() - start_time) * 1000)

        logger.info(
            "Structured pipeline completed",
            total_time_ms=total_time,
            confidence=intelligence.confidence,
            action_items=len(intelligence.action_items),
        )

        return intelligence

    def _build_meeting_intelligence(
        self,
        aggregation_payload: AggregationAgentPayload,
        aggregation_artifacts: AggregationArtifacts,
        validation_result: ValidationResult,
        summaries: list[IntermediateSummary],
    ) -> MeetingIntelligence:
        """Compose final MeetingIntelligence object."""
        base_confidence = aggregation_payload.confidence or 0.6
        adjusted_confidence = max(
            0.0, min(1.0, base_confidence + validation_result.confidence_adjustment)
        )

        intelligence = MeetingIntelligence(
            summary=self._compose_summary_markdown(
                aggregation_payload.sections,
                aggregation_payload.key_areas,
                summaries,
            ),
            action_items=aggregation_payload.consolidated_action_items,
            key_areas=aggregation_payload.key_areas,
            aggregation_artifacts=aggregation_artifacts,
            confidence=adjusted_confidence,
        )

        return intelligence

    def _compose_summary_markdown(
        self,
        sections: list[AggregationAgentPayload.NarrativeSection],
        key_areas,
        summaries: list[IntermediateSummary],
    ) -> str:
        """Deterministically render meeting summary from structured sections."""
        chunk_lookup: dict[int, tuple[str, str]] = {
            summary.chunk_id: (summary.speaker, summary.time_range)
            for summary in summaries
        }
        lines: list[str] = []
        for section in sections:
            lines.append(f"### **{section.title.strip()}**")
            lines.append(section.overview.strip())
            lines.append("")
            for bullet in section.bullet_points:
                lines.append(f"- {bullet.strip()}")
            if section.related_chunks:
                references: list[str] = []
                for cid in section.related_chunks:
                    meta = chunk_lookup.get(cid)
                    if meta:
                        speaker, time_range = meta
                        references.append(f"{speaker} ({time_range})")
                    else:
                        references.append(f"Chunk {cid}")
                if references:
                    lines.append(f"_Related: {', '.join(references)}_")
            lines.append("")

        if key_areas:
            lines.append("### **Key Area Highlights**")
            for area in key_areas:
                summary_line = area.summary.strip()
                lines.append(f"- **{area.title.strip()}** — {summary_line}")
            lines.append("")

        return "\n".join(line for line in lines if line).strip()


async def _maybe_call(callback, progress: float, message: str) -> None:
    """Invoke progress callback if provided."""
    if not callback:
        return
    if asyncio.iscoroutinefunction(callback):
        await callback(progress, message)
    else:
        callback(progress, message)
