from components.export_handlers import ExportHandler
from components.error_display import display_error
from services.pipeline import run_intelligence_pipeline
from services.state_service import StateService
import streamlit as st
from utils.constants import STATE_KEYS

# Page configuration
st.set_page_config(page_title="Meeting Intelligence", page_icon="🧠", layout="wide")

def initialize_page_state():
    """Initialize page-specific session state."""
    required_state = {
        STATE_KEYS.TRANSCRIPT_DATA: None,
        STATE_KEYS.INTELLIGENCE_DATA: None,
        "intelligence_extracted": False,
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


def extract_intelligence_with_progress(transcript: dict) -> dict | None:
    """Extract intelligence directly via the pipeline with inline progress."""
    status_ph = st.empty()
    bar_ph = st.progress(0.0)

    def on_progress(pct: float, message: str) -> None:
        bar_ph.progress(pct)
        status_ph.text(f"{int(pct * 100)}% • {message}")

    with st.spinner("Extracting meeting intelligence..."):
        try:
            chunks = transcript.get("chunks", [])
            result = run_intelligence_pipeline(chunks, on_progress)
        except Exception as e:
            display_error("processing_failed", f"Intelligence extraction failed: {e}")
            return None

    st.session_state[STATE_KEYS.INTELLIGENCE_DATA] = result
    st.session_state["intelligence_extracted"] = True

    # Only use standardized session keys

    st.success("🎉 Meeting intelligence extracted successfully!")
    return result


def render_intelligence_extraction_section():
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
        transcript = st.session_state.get(STATE_KEYS.TRANSCRIPT_DATA)
        if not transcript:
            display_error(
                "missing_data",
                "No transcript found in session. Please process a VTT file first.",
            )
            return

        intelligence_data = extract_intelligence_with_progress(transcript)
        if intelligence_data:
            st.rerun()

    # Show what will be extracted
    st.markdown("**This will:**")
    st.markdown("• 📋 Generate comprehensive executive and detailed summaries")
    st.markdown("• 🎯 Identify action items with owners and deadlines")
    st.markdown("• 🔍 Extract key decisions and topics")


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
        original_filename = (
            st.session_state.get("upload_file", {}).get("name", "transcript.vtt")
        )
        ExportHandler.render_intelligence_export_section(
            intelligence_data, original_filename, "intelligence"
        )


def main():
    """Main page logic."""
    # Initialize services
    initialize_page_state()

    st.title("🧠 Meeting Intelligence")
    st.markdown(
        "Extract and view meeting summaries, action items, and key insights using AI."
    )

    # Check for transcript data
    transcript = st.session_state.get(STATE_KEYS.TRANSCRIPT_DATA)

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
    intelligence_data = st.session_state.get(STATE_KEYS.INTELLIGENCE_DATA)

    if not intelligence_data:
        render_intelligence_extraction_section()
        return

    # Display intelligence results
    render_intelligence_results(intelligence_data)

    st.markdown(
        "*Intelligence extracted from processed transcript. Results are AI-generated and may need review.*"
    )


if __name__ == "__main__":
    main()
