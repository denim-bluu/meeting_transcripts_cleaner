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
        """Process chunks concurrently with deterministic ordering of results."""
        total = len(chunks)
        if total == 0:
            await _maybe_call(
                progress_callback,
                0.4,
                "Chunk processing completed",
            )
            return [], initial_state or ConversationState()

        base_state = initial_state or ConversationState()
        state_snapshots = self._prepare_state_snapshots(base_state, chunks)
        prior_contexts = self._prepare_prior_contexts(chunks)

        summaries: list[IntermediateSummary | None] = [None] * total
        processed_count = 0
        progress_lock = asyncio.Lock()

        async def handle_chunk(index: int) -> None:
            nonlocal processed_count
            chunk = chunks[index]
            payload = await self._invoke_agent(
                chunk,
                state_snapshots[index],
                prior_summary=None,
                previous_context=prior_contexts[index],
            )
            intermediate = self._build_intermediate_summary(chunk, payload)
            summaries[index] = intermediate

            async with progress_lock:
                processed_count += 1
                progress = (processed_count / total) * 0.4
            await _maybe_call(
                progress_callback,
                progress,
                f"Chunk processing {processed_count}/{total}",
            )

        tasks = [asyncio.create_task(handle_chunk(idx)) for idx in range(total)]
        await asyncio.gather(*tasks)

        ordered_summaries: list[IntermediateSummary] = []
        updated_state = base_state
        for summary in summaries:
            if summary is None:
                raise RuntimeError("Missing chunk summary after processing.")
            ordered_summaries.append(summary)
            updated_state = self._update_state(updated_state, summary)

        await _maybe_call(
            progress_callback,
            0.4,
            "Chunk processing completed",
        )

        return ordered_summaries, updated_state

    async def _invoke_agent(
        self,
        chunk: VTTChunk,
        state: ConversationState,
        prior_summary: IntermediateSummary | None,
        *,
        previous_context: str | None = None,
    ) -> ChunkAgentPayload:
        """Call the chunk processing agent with contextual data."""
        transcript_text = chunk.to_transcript_text()
        primary_speaker = chunk.entries[0].speaker if chunk.entries else "Unknown Speaker"
        speakers_in_chunk = sorted({entry.speaker for entry in chunk.entries if entry.speaker}) or [primary_speaker]
        speaker_label = ", ".join(speakers_in_chunk)
        speaker_role = None
        for name in speakers_in_chunk:
            inferred = self._infer_speaker_role(name)
            if inferred:
                speaker_role = inferred
                break

        request_payload = {
            "chunk_id": chunk.chunk_id,
            "time_range": _chunk_time_range(chunk),
            "speaker": speaker_label,
            "speaker_role": speaker_role,
            "transcript": transcript_text,
            "previous_summary": prior_summary.narrative_summary
            if prior_summary
            else None,
            "previous_chunk_transcript": previous_context,
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
            speakers=speaker_label,
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
        speakers_in_chunk = sorted({entry.speaker for entry in chunk.entries if entry.speaker})
        speaker = ", ".join(speakers_in_chunk) if speakers_in_chunk else "Unknown Speaker"
        speaker_role = None
        for name in speakers_in_chunk:
            inferred = self._infer_speaker_role(name)
            if inferred:
                speaker_role = inferred
                break

        return IntermediateSummary(
            chunk_id=chunk.chunk_id,
            time_range=_chunk_time_range(chunk),
            speaker=speaker,
            speaker_role=speaker_role,
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

        unresolved = set(new_state.unresolved_items)
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

    def _prepare_state_snapshots(
        self,
        base_state: ConversationState,
        chunks: Sequence[VTTChunk],
    ) -> list[ConversationState]:
        """Create lightweight snapshots to preserve speaker continuity across concurrent tasks."""
        snapshots: list[ConversationState] = []
        last_speaker = base_state.last_speaker
        last_topic = base_state.last_topic
        key_decisions = dict(base_state.key_decisions)
        unresolved = list(base_state.unresolved_items)

        for chunk in chunks:
            snapshot = ConversationState(
                last_topic=last_topic,
                key_decisions=dict(key_decisions),
                unresolved_items=list(unresolved),
                last_speaker=last_speaker,
            )
            snapshots.append(snapshot)
            if chunk.entries:
                last_speaker = chunk.entries[-1].speaker

        return snapshots

    def _prepare_prior_contexts(
        self,
        chunks: Sequence[VTTChunk],
    ) -> list[str | None]:
        """Collect prior chunk transcript windows for contextual continuity."""
        contexts: list[str | None] = []
        previous_text: str | None = None
        for chunk in chunks:
            contexts.append(
                previous_text[:2000] if previous_text and len(previous_text) > 2000 else previous_text
            )
            previous_text = chunk.to_transcript_text()
        return contexts


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
