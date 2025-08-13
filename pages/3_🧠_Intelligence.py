"""
Intelligence Page - Display meeting intelligence with summaries and action items.

This page shows the extracted intelligence from processed transcripts including
executive summaries, action items, and export functionality.
"""

import asyncio
from datetime import datetime
import threading

import streamlit as st
import structlog

from config import Config, configure_structlog
from models.intelligence import IntelligenceResult
from services.transcript_service import TranscriptService

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)

# Ensure we see logs in Streamlit terminal
logger.info("Intelligence page initialized", streamlit_page=True)


def render_action_items(action_items):
    """Render action items with status indicators and details."""
    if not action_items:
        st.info("🎯 No action items identified in this meeting.")
        return

    st.subheader(f"🎯 Action Items ({len(action_items)})")

    # Show summary stats
    needs_review = sum(1 for item in action_items if item.needs_review)
    critical_items = sum(1 for item in action_items if item.is_critical)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Items", len(action_items))
    with col2:
        st.metric(
            "Needs Review",
            needs_review,
            delta=f"{needs_review/len(action_items)*100:.0f}%"
            if action_items
            else "0%",
        )
    with col3:
        st.metric(
            "Critical",
            critical_items,
            delta=f"{critical_items/len(action_items)*100:.0f}%"
            if action_items
            else "0%",
        )

    st.markdown("---")

    # Render each action item
    for i, item in enumerate(action_items, 1):
        # Determine status icon
        if item.needs_review:
            status_icon = "🔴" if item.is_critical else "🟡"
            status_text = "Critical Review" if item.is_critical else "Needs Review"
        else:
            status_icon = "✅"
            status_text = "Approved"

        # Create expandable action item
        with st.expander(
            f"{status_icon} **Action {i}**: {item.description[:80]}{'...' if len(item.description) > 80 else ''}"
        ):
            # Full description
            st.markdown(f"**Description:** {item.description}")

            # Details in columns
            col1, col2 = st.columns(2)

            with col1:
                if item.owner:
                    st.markdown(f"**👤 Owner:** {item.owner}")
                else:
                    st.markdown("**👤 Owner:** *Not specified*")

                if item.deadline:
                    st.markdown(f"**📅 Deadline:** {item.deadline}")
                else:
                    st.markdown("**📅 Deadline:** *Not specified*")

            with col2:
                st.markdown(f"**🎯 Confidence:** {item.confidence:.2f}")
                st.markdown(f"**📊 Status:** {status_text}")

            # Dependencies and source chunks
            if item.dependencies:
                st.markdown(f"**🔗 Dependencies:** {', '.join(item.dependencies)}")

            st.markdown(
                f"**📄 Source Chunks:** {', '.join(map(str, item.source_chunks))}"
            )

            # Review controls for items that need review
            if item.needs_review:
                st.markdown("**Review Required:**")
                review_col1, review_col2 = st.columns(2)
                with review_col1:
                    if st.button(f"✅ Approve Item {i}", key=f"approve_{i}"):
                        st.success("Item approved! (Feature coming soon)")
                with review_col2:
                    if st.button(f"✏️ Edit Item {i}", key=f"edit_{i}"):
                        st.info("Edit functionality coming soon!")


def render_summary_section(intelligence: IntelligenceResult):
    """Render the summary section with executive and detailed summaries."""
    st.subheader("📋 Meeting Summary")

    # Executive summary in a highlighted box
    st.markdown("### Executive Summary")
    st.info(intelligence.executive_summary)

    # Key takeaways as bullet points
    st.markdown("### Key Takeaways")
    for point in intelligence.bullet_points:
        st.markdown(f"• {point}")

    # Detailed summary in expandable section
    with st.expander("📖 Detailed Summary", expanded=False):
        st.markdown(intelligence.detailed_summary)


def render_decisions_and_topics(intelligence: IntelligenceResult):
    """Render key decisions and topics discussed."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Key Decisions")
        if intelligence.key_decisions:
            for decision in intelligence.key_decisions:
                if isinstance(decision, dict):
                    decision_text = decision.get("description", str(decision))
                else:
                    decision_text = str(decision)
                st.markdown(f"• {decision_text}")
        else:
            st.info("No key decisions identified.")

    with col2:
        st.subheader("💬 Topics Discussed")
        for topic in intelligence.topics_discussed:
            st.markdown(f"• {topic}")


def render_export_section(intelligence: IntelligenceResult):
    """Render export functionality."""
    st.subheader("📤 Export Options")

    # Import the service to access export methods
    from services.intelligence_service import IntelligenceService

    # Create a temporary service instance for export methods
    service = IntelligenceService(api_key="dummy")  # API key not needed for export

    col1, col2, col3 = st.columns(3)

    with col1:
        # JSON export
        json_data = service.export_json(intelligence)
        st.download_button(
            label="📄 Download JSON",
            data=json_data,
            file_name=f"meeting_intelligence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            help="Export complete intelligence data as JSON",
        )

    with col2:
        # Markdown export
        markdown_data = service.export_markdown(intelligence)
        st.download_button(
            label="📝 Download Markdown",
            data=markdown_data,
            file_name=f"meeting_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            help="Export as formatted Markdown report",
        )

    with col3:
        # CSV export for action items
        csv_data = service.export_csv(intelligence)
        st.download_button(
            label="📊 Download CSV",
            data=csv_data,
            file_name=f"action_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            help="Export action items as CSV spreadsheet",
        )

    # Preview section
    st.markdown("### Export Preview")
    preview_tab1, preview_tab2, preview_tab3 = st.tabs(
        ["JSON Preview", "Markdown Preview", "CSV Preview"]
    )

    with preview_tab1:
        with st.expander("🔍 JSON Structure Preview"):
            # Show truncated JSON for preview
            json_preview = (
                json_data[:1000] + "..." if len(json_data) > 1000 else json_data
            )
            st.code(json_preview, language="json")

    with preview_tab2:
        with st.expander("🔍 Markdown Preview"):
            # Show first part of markdown
            markdown_preview = (
                markdown_data[:1500] + "..."
                if len(markdown_data) > 1500
                else markdown_data
            )
            st.markdown(markdown_preview)

    with preview_tab3:
        with st.expander("🔍 CSV Preview"):
            if intelligence.action_items:
                # Show CSV as table
                st.code(
                    csv_data[:800] + "..." if len(csv_data) > 800 else csv_data,
                    language="csv",
                )
            else:
                st.info("No action items to export in CSV format.")


def render_processing_stats(intelligence: IntelligenceResult):
    """Render processing statistics and metadata."""
    with st.expander("📊 Processing Statistics", expanded=False):
        stats = intelligence.processing_stats

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Overall Confidence", f"{intelligence.confidence_score:.2f}")
            if stats.get("total_pipeline_time_ms"):
                st.metric("Processing Time", f"{stats['total_pipeline_time_ms']} ms")

        with col2:
            if stats.get("successful_chunks"):
                st.metric("Chunks Processed", stats["successful_chunks"])
            if stats.get("success_rate"):
                st.metric("Success Rate", f"{stats['success_rate']:.1%}")

        with col3:
            if stats.get("review_level"):
                st.metric("Review Level", stats["review_level"])
            if stats.get("speakers"):
                st.metric("Speakers", len(stats["speakers"]))

        # Detailed stats
        st.markdown("**Detailed Statistics:**")
        for key, value in stats.items():
            if key not in ["speakers"]:  # Skip large lists
                st.text(f"{key}: {value}")


async def extract_intelligence_async():
    """Extract intelligence from transcript in session state."""
    try:
        # Get API key
        api_key = Config.OPENAI_API_KEY
        if not api_key:
            st.error("❌ OpenAI API key not found. Please configure it first.")
            return False

        # Initialize service
        service = TranscriptService(api_key)

        # Extract intelligence with progress updates
        with st.status("Extracting meeting intelligence...", expanded=True) as status:
            progress_placeholder = st.empty()

            def progress_callback(progress: float, message: str):
                progress_placeholder.progress(progress, text=message)

            transcript = await service.extract_intelligence(
                st.session_state.transcript,
                # Note: progress_callback not supported in current implementation
            )

            progress_placeholder.progress(1.0, text="Intelligence extraction complete!")

            # Update session state
            st.session_state.transcript = transcript
            st.session_state.intelligence_extracted = True

            status.update(
                label="✅ Intelligence extraction completed!", state="complete"
            )

        return True

    except Exception as e:
        logger.error("Intelligence extraction failed", error=str(e))
        st.error(f"❌ Intelligence extraction failed: {str(e)}")
        return False


def run_intelligence_extraction():
    """Run intelligence extraction in a thread to avoid blocking Streamlit."""

    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(extract_intelligence_async())
            if success:
                st.rerun()
        finally:
            loop.close()

    thread = threading.Thread(target=run_async)
    thread.start()
    thread.join()


def main():
    """Main function for the Intelligence page."""
    st.set_page_config(page_title="Meeting Intelligence", page_icon="📊", layout="wide")

    st.title("📊 Meeting Intelligence")
    st.markdown("Extract and view meeting summaries, action items, and key insights.")

    # Check if we have a processed transcript
    if "transcript" not in st.session_state:
        st.warning(
            "⚠️ No transcript available. Please upload and process a VTT file first."
        )
        if st.button("📤 Go to Upload & Process"):
            st.switch_page("pages/1_📤_Upload_Process.py")
        return

    transcript = st.session_state.transcript

    # Check if intelligence has been extracted
    if "intelligence" not in transcript:
        st.info("🧠 Intelligence not yet extracted from this transcript.")

        # Show transcript summary
        if "chunks" in transcript:
            st.markdown("### Current Transcript Status")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Chunks", len(transcript["chunks"]))
            with col2:
                st.metric("Speakers", len(transcript.get("speakers", [])))
            with col3:
                duration_min = transcript.get("duration", 0) / 60
                st.metric("Duration", f"{duration_min:.1f} min")
            with col4:
                if "processing_stats" in transcript:
                    acceptance_rate = transcript["processing_stats"].get(
                        "acceptance_rate", "N/A"
                    )
                    st.metric("Quality", acceptance_rate)

        st.markdown("---")

        # Extract intelligence button
        if st.button(
            "🧠 Extract Meeting Intelligence", type="primary", use_container_width=True
        ):
            run_intelligence_extraction()

        st.markdown("**This will:**")
        st.markdown("• 📋 Generate executive and detailed summaries")
        st.markdown("• 🎯 Identify action items with owners and deadlines")
        st.markdown("• 🔍 Extract key decisions and topics")
        st.markdown("• ⚡ Process using parallel AI agents for speed")

        return

    # Display intelligence results
    intelligence = transcript["intelligence"]

    # Header with key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Action Items", len(intelligence.action_items))
    with col2:
        needs_review = sum(1 for item in intelligence.action_items if item.needs_review)
        st.metric("Needs Review", needs_review)
    with col3:
        st.metric("Confidence", f"{intelligence.confidence_score:.2f}")
    with col4:
        st.metric("Topics", len(intelligence.topics_discussed))

    st.markdown("---")

    # Main content in tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Summary", "🎯 Action Items", "🔍 Details", "📤 Export"]
    )

    with tab1:
        render_summary_section(intelligence)

    with tab2:
        render_action_items(intelligence.action_items)

    with tab3:
        render_decisions_and_topics(intelligence)
        st.markdown("---")
        render_processing_stats(intelligence)

    with tab4:
        render_export_section(intelligence)

    # Footer with regeneration option
    st.markdown("---")
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(
            "*Intelligence extracted from processed transcript. Results are AI-generated and may need review.*"
        )

    with col2:
        if st.button("🔄 Re-extract Intelligence"):
            # Clear existing intelligence and re-extract
            if "intelligence" in st.session_state.transcript:
                del st.session_state.transcript["intelligence"]
            st.rerun()


if __name__ == "__main__":
    main()
