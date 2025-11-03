"""Chunk-level processing for the meeting intelligence pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog

from backend.config import settings
from backend.intelligence.agents.chunk import chunk_processing_agent
from backend.intelligence.models import (
    ConversationState,
    IntermediateSummary,
)
from backend.transcript.models import VTTChunk
from shared.types import ProgressCallback
from shared.utils.time_formatters import format_timestamp_vtt

logger = structlog.get_logger(__name__)


class ChunkProcessor:
    """Runs per-chunk analysis to create intermediate summaries."""

    def __init__(self) -> None:
        self._agent = chunk_processing_agent
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def process_chunks(
        self,
        chunks: Sequence[VTTChunk],
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

        await _maybe_call(
            progress_callback, 0.05, f"Preparing to process {total} chunks..."
        )

        async def handle_chunk(index: int) -> None:
            nonlocal processed_count
            chunk = chunks[index]
            summary = await self._invoke_agent(
                chunk,
                state_snapshots[index],
                prior_summary=None,
                previous_context=prior_contexts[index],
            )
            summaries[index] = summary

            async with progress_lock:
                processed_count += 1
                # Map to 5% - 50% range (chunk processing stage)
                progress = 0.05 + (processed_count / total) * 0.45
            await _maybe_call(
                progress_callback,
                progress,
                f"Processing chunks: {processed_count}/{total}",
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
            0.5,
            f"Processed {total} chunks, analyzing patterns...",
        )

        return ordered_summaries, updated_state

    async def _invoke_agent(
        self,
        chunk: VTTChunk,
        state: ConversationState,
        prior_summary: IntermediateSummary | None,
        previous_context: str | None = None,
    ) -> IntermediateSummary:
        """Call the chunk processing agent with contextual data."""
        transcript_text = chunk.to_transcript_text()
        primary_speaker = (
            chunk.entries[0].speaker if chunk.entries else "Unknown Speaker"
        )
        speakers_in_chunk = sorted(
            {entry.speaker for entry in chunk.entries if entry.speaker}
        ) or [primary_speaker]
        speaker_label = ", ".join(speakers_in_chunk)
        time_range = _chunk_time_range(chunk)

        prompt = f"""Analyze this speaker turn and extract structured insights.

Metadata:
- chunk_id: {chunk.chunk_id}
- time_range: {time_range}
- speaker: {speaker_label}

Transcript:
{transcript_text}

{f'Previous chunk context: {previous_context}' if previous_context else ''}
{f'Previous summary: {prior_summary.narrative_summary}' if prior_summary else ''}

Conversation state:
- Last topic: {state.last_topic or 'None'}
- Key decisions: {len(state.key_decisions)} tracked
- Last speaker: {state.last_speaker or 'None'}

Include the metadata (chunk_id, time_range, speaker) in your response. Infer speaker_role from context if clear, otherwise set to None."""

        logger.info(
            "Running chunk agent",
            chunk_id=chunk.chunk_id,
            speakers=speaker_label,
            entry_count=len(chunk.entries),
        )

        async with self._semaphore:
            result = await self._agent.run(prompt)
        return result.output

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
                previous_text[:2000]
                if previous_text and len(previous_text) > 2000
                else previous_text
            )
            previous_text = chunk.to_transcript_text()
        return contexts


def _chunk_time_range(chunk: VTTChunk) -> str:
    """Compute formatted time range for the chunk."""
    if not chunk.entries:
        return "00:00:00.000 - 00:00:00.000"

    start = min(entry.start_time for entry in chunk.entries)
    end = max(entry.end_time for entry in chunk.entries)
    return f"{format_timestamp_vtt(start)} - {format_timestamp_vtt(end)}"


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
