"""Semantic aggregation for meeting intelligence pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog

from backend.intelligence.agents.aggregation import aggregation_agent
from backend.intelligence.models import (
    AggregationAgentPayload,
    AggregationArtifacts,
    ConversationState,
    IntermediateSummary,
)
from shared.types import ProgressCallback

logger = structlog.get_logger(__name__)

class SemanticAggregator:
    """Aggregates intermediate chunk summaries into final meeting intelligence."""

    def __init__(self) -> None:
        self._agent = aggregation_agent
        self._semaphore = asyncio.Semaphore(1)  # sequential to maintain ordering

    async def aggregate(
        self,
        summaries: Sequence[IntermediateSummary],
        conversation_state: ConversationState,
        progress_callback: ProgressCallback | None = None,
    ) -> AggregationAgentPayload:
        """Perform semantic aggregation using the configured agent."""
        if not summaries:
            raise ValueError("No intermediate summaries provided for aggregation.")

        await _maybe_call(progress_callback, 0.52, "Preparing aggregation context...")

        # Format summaries naturally for the agent
        summaries_text = "\n\n".join(
            f"Chunk {s.chunk_id} ({s.time_range}) - {s.speaker}:\n{s.narrative_summary}"
            for s in summaries
        )

        conversation_context = f"""Conversation state:
- Last topic: {conversation_state.last_topic or 'None'}
- Key decisions: {len(conversation_state.key_decisions)} tracked
- Last speaker: {conversation_state.last_speaker or 'None'}
"""

        prompt = f"""Synthesize meeting intelligence from {len(summaries)} chunk summaries.

{summaries_text}

{conversation_context}

Create narrative sections, identify key areas, consolidate action items, build a timeline, and flag any unresolved topics or contradictions."""

        logger.info(
            "Running aggregation agent",
            summary_count=len(summaries),
            first_chunk=summaries[0].chunk_id,
            last_chunk=summaries[-1].chunk_id,
        )

        await _maybe_call(progress_callback, 0.55, "Aggregating insights...")

        async with self._semaphore:
            result = await self._agent.run(prompt)

        await _maybe_call(
            progress_callback, 0.75, "Organizing key areas and action items..."
        )
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
