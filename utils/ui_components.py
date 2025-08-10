"""
Shared UI components for the Meeting Transcript Cleaner application.

This module provides reusable UI components that maintain consistent styling
and behavior across the application without inline CSS.
"""

from collections.abc import Sequence
from typing import Any

import streamlit as st


def render_metrics_row(metrics: Sequence[tuple[str, Any, str | None]]) -> None:
    """Display a row of metrics with optional delta values."""
    if not metrics:
        return

    cols = st.columns(len(metrics))
    for i, (label, value, delta) in enumerate(metrics):
        with cols[i]:
            st.metric(label, value, delta=delta)


def render_progress_status(
    progress: float, status: str, eta: float, tokens_per_sec: float
) -> None:
    """Display real-time progress with ETA and throughput metrics."""
    st.progress(progress)
    st.write(f"**{status}**")

    metrics = [
        ("Progress", f"{progress:.1%}", None),
        ("ETA", f"{eta:.1f}s", None),
        ("Tokens/sec", f"{tokens_per_sec:.0f}", None),
    ]
    render_metrics_row(metrics)


def render_document_preview(segments: Any, max_segments: int = 3) -> None:
    """Display preview of document segments with truncation."""
    if not segments:
        st.info("No segments to preview")
        return

    for _i, segment in enumerate(segments[:max_segments]):
        with st.expander(
            f"Segment {segment.sequence_number} ({segment.token_count} tokens)",
            expanded=False,
        ):
            preview_text = segment.content[:200]
            if len(segment.content) > 200:
                preview_text += "..."
            st.text(preview_text)

    if len(segments) > max_segments:
        st.info(f"Showing first {max_segments} of {len(segments)} segments")
