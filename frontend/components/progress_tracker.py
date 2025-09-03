"""Task progress tracking UI component."""

from collections.abc import Callable
from typing import Any

from services.task_service import TaskService
import streamlit as st
from utils.constants import TASK_STATUS


class ProgressTracker:
    """Reusable progress tracking component."""

    def __init__(self, task_service: TaskService):
        self.task_service = task_service

    def track_task(
        self,
        task_id: str,
        title: str = "Processing...",
        success_callback: Callable | None = None,
        error_callback: Callable | None = None,
    ) -> bool:
        """Track task progress with live updates.

        Logic:
        1. Create progress UI containers
        2. Start task polling with UI updates
        3. Handle success/error states with callbacks
        4. Return final success status
        """
        st.subheader(title)

        # Create UI containers
        status_container = st.empty()
        progress_container = st.empty()
        message_container = st.empty()

        # Default callbacks if not provided
        def default_success(data):
            st.success("✅ Task completed successfully!")

        def default_error(error_msg):
            st.error(f"❌ {error_msg}")

        success_fn = success_callback or default_success
        error_fn = error_callback or default_error

        # Track progress
        return self.task_service.poll_task_with_ui(
            task_id=task_id,
            status_placeholder=status_container,
            progress_placeholder=progress_container,
            success_callback=success_fn,
            error_callback=error_fn,
        )


def render_simple_progress(
    current_step: int, total_steps: int, step_name: str, show_percentage: bool = True
) -> None:
    """Render simple step-based progress.

    Logic:
    1. Calculate progress percentage
    2. Display progress bar and step information
    3. Show current step name and progress
    """
    progress = current_step / total_steps if total_steps > 0 else 0

    col1, col2 = st.columns([3, 1])

    with col1:
        st.progress(progress)
        st.caption(f"Step {current_step}/{total_steps}: {step_name}")

    with col2:
        if show_percentage:
            st.metric("Progress", f"{progress * 100:.0f}%")


def render_task_summary(task_data: dict[str, Any]) -> None:
    """Render completed task summary.

    Logic:
    1. Extract key information from task data
    2. Display task metadata and results
    3. Show timing and status information
    """
    st.subheader("Task Summary")

    col1, col2, col3 = st.columns(3)

    with col1:
        status = task_data.get("status", "unknown")
        status_emoji = "✅" if status == TASK_STATUS.COMPLETED else "❌"
        st.metric("Status", f"{status_emoji} {status.title()}")

    with col2:
        progress = task_data.get("progress", 0)
        st.metric("Progress", f"{progress * 100:.0f}%")

    with col3:
        created_at = task_data.get("created_at", "")
        if created_at:
            st.metric("Created", created_at.split("T")[0])  # Show date only

    # Show message if available
    message = task_data.get("message")
    if message:
        st.info(f"**Message:** {message}")
