"""Meeting Intelligence Extraction - Refactored with clean architecture."""

from components.export_handlers import ExportHandler
from components.health_check import require_healthy_backend
from components.progress_tracker import ProgressTracker
from services.backend_service import BackendService
from services.state_service import StateService
from services.task_service import TaskService
import streamlit as st
from utils.constants import STATE_KEYS

# Page configuration
st.set_page_config(page_title="Meeting Intelligence", page_icon="🧠", layout="wide")


def initialize_services():
    """Initialize required services."""
    backend = BackendService()
    task_service = TaskService(backend)
    progress_tracker = ProgressTracker(task_service)
    return backend, task_service, progress_tracker


def initialize_page_state():
    """Initialize page-specific session state."""
    required_state = {
        STATE_KEYS.TRANSCRIPT_DATA: None,
        STATE_KEYS.INTELLIGENCE_DATA: None,
        STATE_KEYS.CURRENT_TASK_ID: None,
        "intelligence_extracted": False,
        "transcript_task_id": None,
    }
    StateService.initialize_page_state(required_state)


def render_action_items(action_items: list[dict]):
    """Render action items with status indicators and details.

    Logic:
    1. Show summary metrics for action items
    2. Display each action item with status indicators
    3. Provide expandable details for each item
    """
    if not action_items:
        st.info("🎯 No action items identified in this meeting.")
        return

    st.subheader(f"🎯 Action Items ({len(action_items)})")

    # Show summary stats
    has_owner = sum(1 for item in action_items if item.get("owner"))
    has_due_date = sum(1 for item in action_items if item.get("due_date"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Items", len(action_items))
    with col2:
        owner_pct = f"{has_owner/len(action_items)*100:.0f}%" if action_items else "0%"
        st.metric("With Owner", has_owner, delta=owner_pct)
    with col3:
        due_pct = f"{has_due_date/len(action_items)*100:.0f}%" if action_items else "0%"
        st.metric("With Due Date", has_due_date, delta=due_pct)

    st.divider()

    # Render each action item
    for i, item in enumerate(action_items, 1):
        # Determine status icon based on completeness
        if item.get("owner") and item.get("due_date"):
            status_icon = "✅"
            status_text = "Complete"
        elif item.get("owner") or item.get("due_date"):
            status_icon = "🟡"
            status_text = "Partial"
        else:
            status_icon = "🔴"
            status_text = "Needs Details"

        description = item.get("description", "No description")
        preview = description[:80] + "..." if len(description) > 80 else description

        # Create expandable action item
        with st.expander(f"{status_icon} **Action {i}**: {preview}"):
            st.markdown(f"**Description:** {description}")

            # Details in columns
            col1, col2 = st.columns(2)

            with col1:
                owner = item.get("owner", "*Not specified*")
                st.markdown(f"**👤 Owner:** {owner}")

                due_date = item.get("due_date", "*Not specified*")
                st.markdown(f"**📅 Due Date:** {due_date}")

            with col2:
                st.markdown(f"**📊 Status:** {status_text}")


def render_summary_section(intelligence_data: dict):
    """Render the summary section with markdown summary.

    Logic:
    1. Display meeting summary in markdown format
    2. Handle missing summary gracefully
    """
    st.subheader("📋 Meeting Summary")
    summary = intelligence_data.get("summary", "No summary available")
    st.markdown(summary)


def extract_intelligence_with_progress(
    backend: BackendService,
    progress_tracker: ProgressTracker,
    transcript_id: str,
) -> dict | None:
    """Extract intelligence using backend service with progress tracking.

    Logic:
    1. Start intelligence extraction request
    2. Track progress with UI updates
    3. Handle success/error states
    4. Return intelligence data or None
    """

    def on_success(task_data):
        """Handle successful intelligence extraction."""
        result = task_data.get("result", {})
        st.session_state[STATE_KEYS.INTELLIGENCE_DATA] = result
        st.session_state["intelligence_extracted"] = True

        # Also store in legacy format for compatibility
        if "transcript" not in st.session_state:
            st.session_state.transcript = {}
        st.session_state.transcript["intelligence"] = result

        st.success("🎉 Meeting intelligence extracted successfully!")
        return result

    def on_error(error_message):
        """Handle intelligence extraction error."""
        st.error(f"Intelligence extraction failed: {error_message}")
        return None

    # Start extraction
    success, response = backend.extract_intelligence(transcript_id)

    if not success:
        error_msg = response.get("error", "Extraction failed")
        st.error(f"❌ Failed to start extraction: {error_msg}")
        return None

    # Get task ID and track progress
    task_id = response.get("task_id")
    if not task_id:
        st.error("No task ID received")
        return None

    st.session_state[STATE_KEYS.CURRENT_TASK_ID] = task_id
    StateService.set_url_param("task", task_id)

    # Track progress
    success = progress_tracker.track_task(
        task_id=task_id,
        title="🧠 Extracting Meeting Intelligence",
        success_callback=on_success,
        error_callback=on_error,
    )

    if success:
        return st.session_state.get(STATE_KEYS.INTELLIGENCE_DATA)
    return None


def render_intelligence_extraction_section(
    backend: BackendService, progress_tracker: ProgressTracker
):
    """Render intelligence extraction interface.

    Logic:
    1. Check if transcript is available for extraction
    2. Handle extraction process
    3. Provide user guidance
    """
    st.info("🧠 Intelligence not yet extracted from this transcript.")
    st.divider()

    # Extract intelligence button
    if st.button(
        "🧠 Extract Meeting Intelligence", type="primary", use_container_width=True
    ):
        # Get the transcript task_id from session state
        transcript_task_id = st.session_state.get("transcript_task_id")

        if not transcript_task_id:
            st.error(
                "❌ No transcript task ID found. Please re-process your transcript."
            )
            return

        # Extract intelligence
        intelligence_data = extract_intelligence_with_progress(
            backend, progress_tracker, transcript_task_id
        )

        if intelligence_data:
            st.rerun()  # Refresh to show results

    # Show what will be extracted
    st.markdown("**This will:**")
    st.markdown("• 📋 Generate comprehensive executive and detailed summaries")
    st.markdown("• 🎯 Identify action items with owners and deadlines")
    st.markdown("• 🔍 Extract key decisions and topics")


def handle_task_resumption(backend: BackendService, task_service: TaskService):
    """Handle resumption of intelligence extraction task from URL.

    Logic:
    1. Check URL for existing task ID
    2. Verify task is intelligence extraction type
    3. Resume task if valid
    4. Store results in session state
    """
    task_id = StateService.get_url_param("task")
    if not task_id:
        return

    st.info(f"Resuming intelligence task: {task_id}")

    # Get task result
    result = task_service.get_task_result(task_id)

    if result:
        st.session_state[STATE_KEYS.INTELLIGENCE_DATA] = result
        st.session_state["intelligence_extracted"] = True

        # Also store in legacy format for compatibility
        if "transcript" not in st.session_state:
            st.session_state.transcript = {}
        st.session_state.transcript["intelligence"] = result

        st.success("✅ Intelligence task resumed successfully!")
        StateService.clear_url_params(["task"])
    else:
        st.warning("Task not found or expired")
        StateService.clear_url_params(["task"])


def render_intelligence_results(intelligence_data: dict):
    """Render intelligence results in tabbed interface.

    Logic:
    1. Show key metrics header
    2. Display content in organized tabs
    3. Provide export and re-extraction options
    """
    # Header with key metrics
    action_items = intelligence_data.get("action_items", [])
    processing_stats = intelligence_data.get("processing_stats", {})

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Action Items", len(action_items))
    with col2:
        has_owner = sum(1 for item in action_items if item.get("owner"))
        st.metric("With Owner", has_owner)
    with col3:
        has_due_date = sum(1 for item in action_items if item.get("due_date"))
        st.metric("With Due Date", has_due_date)
    with col4:
        processing_time = processing_stats.get("time_ms", 0) / 1000
        st.metric("Processing Time", f"{processing_time:.1f}s")

    st.divider()

    # Main content in tabs
    tab1, tab2, tab3 = st.tabs(["📋 Summary", "🎯 Action Items", "📤 Export"])

    with tab1:
        render_summary_section(intelligence_data)

    with tab2:
        render_action_items(action_items)
    with tab3:
        original_filename = "meeting_transcript"  # Could be from session state
        ExportHandler.render_intelligence_export_section(
            intelligence_data, original_filename, "intelligence"
        )


def main():
    """Main page logic."""
    # Initialize services
    backend, task_service, progress_tracker = initialize_services()
    initialize_page_state()

    st.title("🧠 Meeting Intelligence")
    st.markdown(
        "Extract and view meeting summaries, action items, and key insights using AI."
    )

    # Require healthy backend
    require_healthy_backend(backend)

    # Handle task resumption
    handle_task_resumption(backend, task_service)

    # Check for transcript data (from session state or legacy format)
    transcript = st.session_state.get("transcript") or st.session_state.get(
        STATE_KEYS.TRANSCRIPT_DATA
    )

    if not transcript:
        st.warning(
            "⚠️ No transcript available. Please upload and process a VTT file first."
        )

        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("📤 Go to Upload & Process", type="primary"):
                st.switch_page("pages/1_📤_Upload_Process.py")
        with col2:
            st.markdown(
                "*You need to upload and process a VTT file before extracting intelligence.*"
            )

        # Show feature preview
        st.divider()
        st.markdown("### What you can do with Meeting Intelligence:")
        st.markdown(
            "• 📋 **Executive Summary** - Get a concise overview of your meeting"
        )
        st.markdown(
            "• 🎯 **Action Items** - Automatically identify tasks with owners and deadlines"
        )
        st.markdown(
            "• 🔍 **Key Decisions** - Extract important decisions made during the meeting"
        )
        st.markdown(
            "• 💬 **Topics Discussed** - See all topics covered in the conversation"
        )
        st.markdown("• 📤 **Export Options** - Download results in multiple formats")
        return

    # Check if intelligence has been extracted
    intelligence_data = st.session_state.get(STATE_KEYS.INTELLIGENCE_DATA) or (
        transcript.get("intelligence") if isinstance(transcript, dict) else None
    )

    if not intelligence_data:
        render_intelligence_extraction_section(backend, progress_tracker)
        return

    # Display intelligence results
    render_intelligence_results(intelligence_data)

    st.markdown(
        "*Intelligence extracted from processed transcript. Results are AI-generated and may need review.*"
    )


if __name__ == "__main__":
    main()
