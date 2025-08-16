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
