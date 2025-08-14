"""
Intelligence Page - Display meeting intelligence with summaries and action items.

This page shows the extracted intelligence from processed transcripts including
executive summaries, action items, and export functionality.
"""

import asyncio
from datetime import datetime

import streamlit as st
import structlog

from config import Config, configure_structlog
from models.simple_intelligence import ActionItem, MeetingIntelligence
from services.transcript_service import TranscriptService

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)

# Ensure we see logs in Streamlit terminal
logger.info("Intelligence page initialized", streamlit_page=True)


def render_action_items(action_items: list[ActionItem]):
    """Render action items with status indicators and details."""
    if not action_items:
        st.info("🎯 No action items identified in this meeting.")
        return

    st.subheader(f"🎯 Action Items ({len(action_items)})")

    # Show summary stats - simplified for new structure
    has_owner = sum(1 for item in action_items if item.owner)
    has_due_date = sum(1 for item in action_items if item.due_date)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Items", len(action_items))
    with col2:
        st.metric(
            "With Owner",
            has_owner,
            delta=f"{has_owner/len(action_items)*100:.0f}%" if action_items else "0%",
        )
    with col3:
        st.metric(
            "With Due Date",
            has_due_date,
            delta=f"{has_due_date/len(action_items)*100:.0f}%"
            if action_items
            else "0%",
        )

    st.markdown("---")

    # Render each action item
    for i, item in enumerate(action_items, 1):
        # Determine status icon based on completeness
        if item.owner and item.due_date:
            status_icon = "✅"
            status_text = "Complete"
        elif item.owner or item.due_date:
            status_icon = "🟡"
            status_text = "Partial"
        else:
            status_icon = "🔴"
            status_text = "Needs Details"

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

                if item.due_date:
                    st.markdown(f"**📅 Due Date:** {item.due_date}")
                else:
                    st.markdown("**📅 Due Date:** *Not specified*")

            with col2:
                st.markdown(f"**📊 Status:** {status_text}")

            # Action controls
            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.button(f"📝 Edit Item {i}", key=f"edit_{i}"):
                    st.info("Edit functionality coming soon!")
            with action_col2:
                if st.button(f"✅ Mark Complete {i}", key=f"complete_{i}"):
                    st.success("Feature coming soon!")


def render_summary_section(intelligence: MeetingIntelligence):
    """Render the summary section with markdown summary."""
    st.subheader("📋 Meeting Summary")

    # Display the markdown summary
    st.markdown(intelligence.summary)


def render_processing_stats_section(intelligence: MeetingIntelligence):
    """Render processing statistics."""
    st.subheader("📊 Processing Statistics")

    if intelligence.processing_stats:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if "vtt_chunks" in intelligence.processing_stats:
                st.metric("VTT Chunks", intelligence.processing_stats["vtt_chunks"])

        with col2:
            if "semantic_chunks" in intelligence.processing_stats:
                st.metric(
                    "Semantic Chunks", intelligence.processing_stats["semantic_chunks"]
                )

        with col3:
            if "api_calls" in intelligence.processing_stats:
                st.metric("API Calls", intelligence.processing_stats["api_calls"])

        with col4:
            if "time_ms" in intelligence.processing_stats:
                st.metric(
                    "Processing Time", f"{intelligence.processing_stats['time_ms']}ms"
                )

        # Additional stats
        if "avg_importance" in intelligence.processing_stats:
            st.metric(
                "Avg Importance",
                f"{intelligence.processing_stats['avg_importance']:.2f}",
            )
    else:
        st.info("No processing statistics available.")


def render_export_section(intelligence: MeetingIntelligence):
    """Render export functionality for new intelligence format."""
    st.subheader("📤 Export Options")

    import json

    col1, col2, col3 = st.columns(3)

    with col1:
        # JSON export
        json_data = json.dumps(
            {
                "summary": intelligence.summary,
                "action_items": [
                    {
                        "description": item.description,
                        "owner": item.owner,
                        "due_date": item.due_date,
                    }
                    for item in intelligence.action_items
                ],
                "processing_stats": intelligence.processing_stats,
            },
            indent=2,
        )

        st.download_button(
            label="📄 Download JSON",
            data=json_data,
            file_name=f"meeting_intelligence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            help="Export complete intelligence data as JSON",
        )

    with col2:
        # Markdown export - use the summary directly
        markdown_data = f"# Meeting Intelligence Report\n\n{intelligence.summary}\n\n## Action Items\n\n"
        for i, item in enumerate(intelligence.action_items, 1):
            markdown_data += f"{i}. **{item.description}**\n"
            if item.owner:
                markdown_data += f"   - Owner: {item.owner}\n"
            if item.due_date:
                markdown_data += f"   - Due: {item.due_date}\n"
            markdown_data += "\n"

        st.download_button(
            label="📝 Download Markdown",
            data=markdown_data,
            file_name=f"meeting_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            help="Export as formatted Markdown report",
        )

    with col3:
        # CSV export for action items
        csv_data = "Description,Owner,Due Date\n"
        for item in intelligence.action_items:
            csv_data += (
                f'"{item.description}","{item.owner or ""}","{item.due_date or ""}"\n'
            )

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


async def extract_intelligence_async(transcript_data):
    """Extract intelligence from transcript data."""
    try:
        # Get API key
        api_key = Config.OPENAI_API_KEY
        if not api_key:
            return False, "OpenAI API key not found. Please configure it first."

        # Initialize service
        service = TranscriptService(api_key)

        # Extract intelligence
        result_transcript = await service.extract_intelligence(transcript_data)
        return True, result_transcript

    except Exception as e:
        logger.error("Intelligence extraction failed", error=str(e))
        return False, str(e)


def run_intelligence_extraction():
    """Run intelligence extraction and update session state."""
    # Check if transcript exists in session state
    if "transcript" not in st.session_state:
        st.error("❌ No transcript available for intelligence extraction.")
        return

    # Get the transcript data from session state
    transcript_data = st.session_state.transcript.copy()

    # Show progress and run extraction
    with st.status("Extracting meeting intelligence...", expanded=True) as status:
        progress_placeholder = st.empty()
        progress_placeholder.progress(
            0.1, text="Initializing intelligence extraction..."
        )

        # Run the async function in the current thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            progress_placeholder.progress(0.3, text="Processing transcript chunks...")
            success, result = loop.run_until_complete(
                extract_intelligence_async(transcript_data)
            )

            if success:
                progress_placeholder.progress(
                    1.0, text="Intelligence extraction complete!"
                )

                # Update session state with the result
                st.session_state.transcript = result
                st.session_state.intelligence_extracted = True

                status.update(
                    label="✅ Intelligence extraction completed!", state="complete"
                )
                st.rerun()
            else:
                status.update(label="❌ Intelligence extraction failed", state="error")
                st.error(f"❌ Intelligence extraction failed: {result}")

        except Exception as e:
            logger.error("Intelligence extraction failed", error=str(e))
            status.update(label="❌ Intelligence extraction failed", state="error")
            st.error(f"❌ Intelligence extraction failed: {str(e)}")
        finally:
            loop.close()


def main():
    """Main function for the Intelligence page."""
    st.set_page_config(page_title="Meeting Intelligence", page_icon="🧠", layout="wide")

    st.title("🧠 Meeting Intelligence")
    st.markdown("Extract and view meeting summaries, action items, and key insights.")

    # Initialize session state if needed
    if "transcript" not in st.session_state:
        st.session_state.transcript = None
    if "intelligence_extracted" not in st.session_state:
        st.session_state.intelligence_extracted = False

    # Check if we have a processed transcript
    if st.session_state.transcript is None or not st.session_state.transcript:
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

        st.markdown("---")
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
        st.markdown(
            "• 📤 **Export Options** - Download results in JSON, Markdown, or CSV formats"
        )
        return

    transcript = st.session_state.transcript

    # Check if intelligence has been extracted
    if "intelligence" not in transcript:
        st.info("🧠 Intelligence not yet extracted from this transcript.")

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
        has_owner = sum(1 for item in intelligence.action_items if item.owner)
        st.metric("With Owner", has_owner)
    with col3:
        has_due_date = sum(1 for item in intelligence.action_items if item.due_date)
        st.metric("With Due Date", has_due_date)
    with col4:
        processing_time = intelligence.processing_stats.get("time_ms", 0)
        st.metric("Processing Time", f"{processing_time}ms")

    st.markdown("---")

    # Main content in tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Summary", "🎯 Action Items", "📊 Statistics", "📤 Export"]
    )

    with tab1:
        render_summary_section(intelligence)

    with tab2:
        render_action_items(intelligence.action_items)

    with tab3:
        render_processing_stats_section(intelligence)

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
