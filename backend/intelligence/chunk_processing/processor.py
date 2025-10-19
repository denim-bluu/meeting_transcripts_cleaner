"""Chunk-level processing for the meeting intelligence pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
import json
from typing import Any

import structlog

from backend.intelligence.agents.chunk import chunk_processing_agent
from backend.intelligence.models import (
    ChunkAgentPayload,
    ConversationState,
    IntermediateSummary,
)
from backend.transcript.models import VTTChunk

ProgressCallback = Callable[[float, str], Any] | Callable[[float, str], Awaitable[Any]]


class ChunkProcessor:
    """Runs per-chunk analysis to create intermediate summaries."""

    def __init__(
        self,
        *,
        agent=chunk_processing_agent,
        max_concurrency: int = 3,
    ) -> None:
        self._agent = agent
        self._logger = structlog.get_logger(__name__)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def process_chunks(
        self,
        chunks: Sequence[VTTChunk],
        *,
        initial_state: ConversationState | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[list[IntermediateSummary], ConversationState]:
        """Process chunks sequentially while respecting conversation flow."""
        state = initial_state or ConversationState()
        summaries: list[IntermediateSummary] = []

        total = len(chunks) or 1
        for idx, chunk in enumerate(chunks):
            progress = (idx / total) * 0.4  # leave headroom for aggregation phase
            await _maybe_call(
                progress_callback, progress, f"Chunk processing {idx + 1}/{total}"
            )

            prior_summary = summaries[-1] if summaries else None
            payload = await self._invoke_agent(chunk, state, prior_summary)
            intermediate = self._build_intermediate_summary(chunk, payload)
            summaries.append(intermediate)
            state = self._update_state(state, intermediate)

        await _maybe_call(
            progress_callback,
            0.4,
            "Chunk processing completed",
        )

        return summaries, state

    async def _invoke_agent(
        self,
        chunk: VTTChunk,
        state: ConversationState,
        prior_summary: IntermediateSummary | None,
    ) -> ChunkAgentPayload:
        """Call the chunk processing agent with contextual data."""
        transcript_text = chunk.to_transcript_text()
        speaker = chunk.entries[0].speaker if chunk.entries else "Unknown Speaker"
        speaker_role = self._infer_speaker_role(speaker)

        request_payload = {
            "chunk_id": chunk.chunk_id,
            "time_range": _chunk_time_range(chunk),
            "speaker": speaker,
            "speaker_role": speaker_role,
            "transcript": transcript_text,
            "previous_summary": prior_summary.narrative_summary
            if prior_summary
            else None,
            "conversation_state": state.model_dump(),
        }

        prompt = (
            "You are extracting structured insights from a single speaker turn in a meeting.\n"
            "Return JSON that matches the ChunkAgentPayload schema. "
            "Preserve factual accuracy, and note dependencies on earlier discussion.\n\n"
            f"Context JSON:\n{json.dumps(request_payload, indent=2)}"
        )

        self._logger.debug(
            "Running chunk agent",
            chunk_id=chunk.chunk_id,
            speaker=speaker,
            speaker_role=speaker_role,
            entry_count=len(chunk.entries),
        )

        async with self._semaphore:
            result = await self._agent.run(prompt)
        return result.output

    def _build_intermediate_summary(
        self,
        chunk: VTTChunk,
        payload: ChunkAgentPayload,
    ) -> IntermediateSummary:
        """Populate metadata around the agent payload."""
        speaker = chunk.entries[0].speaker if chunk.entries else "Unknown Speaker"

        return IntermediateSummary(
            chunk_id=chunk.chunk_id,
            time_range=_chunk_time_range(chunk),
            speaker=speaker,
            speaker_role=self._infer_speaker_role(speaker),
            narrative_summary=payload.narrative_summary,
            key_concepts=payload.key_concepts,
            decisions=payload.decisions,
            action_items=payload.action_items,
            conversation_links=payload.conversation_links,
            continuation_flag=payload.continuation_flag,
            insights=payload.insights,
            confidence=payload.confidence,
        )

    def _update_state(
        self,
        state: ConversationState,
        summary: IntermediateSummary,
    ) -> ConversationState:
        """Update conversational state with new insights."""
        new_state = state.model_copy(deep=True)
        new_state.last_speaker = summary.speaker
        if summary.key_concepts:
            new_state.last_topic = summary.key_concepts[0].title

        for decision in summary.decisions:
            new_state.key_decisions[decision.statement] = decision

        unresolved = {item for item in new_state.unresolved_items}
        for action in summary.action_items:
            if action.owner:
                unresolved.discard(action.description)
            else:
                unresolved.add(action.description)

        new_state.unresolved_items = list(unresolved)
        return new_state

    def _infer_speaker_role(self, speaker: str | None) -> str | None:
        """Best-effort inference of speaker authority based on naming heuristics."""
        if not speaker:
            return None

        lower = speaker.lower()
        if "director" in lower:
            return "Director"
        if "manager" in lower:
            return "Manager"
        if "lead" in lower:
            return "Team Lead"
        if "vp" in lower or "vice president" in lower:
            return "Executive"
        if "chief" in lower or "cxo" in lower or "ceo" in lower:
            return "Executive"
        return None


def _chunk_time_range(chunk: VTTChunk) -> str:
    """Compute formatted time range for the chunk."""
    if not chunk.entries:
        return "00:00:00.000 - 00:00:00.000"

    start = min(entry.start_time for entry in chunk.entries)
    end = max(entry.end_time for entry in chunk.entries)
    return f"{_format_timestamp(start)} - {_format_timestamp(end)}"


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


async def _maybe_call(
    callback: ProgressCallback | None,
    progress: float,
    message: str,
) -> None:
    """Call progress callback if supplied."""
    if not callback:
        return

    if asyncio.iscoroutinefunction(callback):
        await callback(progress, message)
    else:
        callback(progress, message)
