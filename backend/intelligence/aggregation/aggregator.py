"""Semantic aggregation for meeting intelligence pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import json
from typing import Any

import structlog

from backend.intelligence.agents.aggregation import aggregation_agent
from backend.intelligence.models import (
    AggregationAgentPayload,
    AggregationArtifacts,
    ConversationState,
    IntermediateSummary,
)
from shared.types import ProgressCallback


class SemanticAggregator:
    """Aggregates intermediate chunk summaries into final meeting intelligence."""

    def __init__(self, *, agent=aggregation_agent) -> None:
        self._agent = agent
        self._logger = structlog.get_logger(__name__)
        self._semaphore = asyncio.Semaphore(1)  # sequential to maintain ordering

    async def aggregate(
        self,
        summaries: Sequence[IntermediateSummary],
        *,
        conversation_state: ConversationState,
        progress_callback: ProgressCallback | None = None,
    ) -> AggregationAgentPayload:
        """Perform semantic aggregation using the configured agent."""
        if not summaries:
            raise ValueError("No intermediate summaries provided for aggregation.")

        await _maybe_call(progress_callback, 0.45, "Aggregation: preparing context")

        payload = {
            "conversation_state": conversation_state.model_dump(),
            "intermediate_summaries": [
                _serialize_summary(summary) for summary in summaries
            ],
        }
        prompt = (
            "You are the aggregation stage for a meeting intelligence system.\n"
            "Use the provided intermediate summaries (already speaker-aware and temporally ordered) "
            "to produce meeting-level insights, following the AggregationAgentPayload schema.\n\n"
            f"Context JSON:\n{json.dumps(payload, indent=2)}"
        )

        self._logger.info(
            "Running aggregation agent",
            summary_count=len(summaries),
            first_chunk=summaries[0].chunk_id,
            last_chunk=summaries[-1].chunk_id,
        )

        async with self._semaphore:
            result = await self._agent.run(prompt)

        await _maybe_call(progress_callback, 0.7, "Aggregation completed")
        return result.output

    def build_artifacts(
        self, agent_payload: AggregationAgentPayload
    ) -> AggregationArtifacts:
        """Convert agent payload into aggregation artifacts object."""
        return AggregationArtifacts(
            timeline_events=agent_payload.timeline_events,
            unresolved_topics=agent_payload.unresolved_topics,
            validation_notes=agent_payload.validation_notes,
        )


def _serialize_summary(summary: IntermediateSummary) -> dict[str, Any]:
    """Serialize an IntermediateSummary for prompt usage."""
    return summary.model_dump(exclude_none=True)


async def _maybe_call(
    callback: ProgressCallback | None,
    progress: float,
    message: str,
) -> None:
    """Call progress callback if available."""
    if not callback:
        return

    if asyncio.iscoroutinefunction(callback):
        await callback(progress, message)
    else:
        callback(progress, message)
