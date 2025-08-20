"""
Intelligence Page - Simplified API-based intelligence extraction.

This page uses the FastAPI backend to extract meeting intelligence from processed
transcripts, with simple polling for progress updates.
"""

from datetime import datetime
import time

from api_client import api_client
from config import configure_structlog
import streamlit as st
import structlog

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)

logger.info("Intelligence page initialized", streamlit_page=True, mode="api_client")


def render_action_items(action_items: list[dict]):
    """Render action items with status indicators and details."""
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

        # Create expandable action item
        with st.expander(
            f"{status_icon} **Action {i}**: {description[:80]}{'...' if len(description) > 80 else ''}"
        ):
            # Full description
            st.markdown(f"**Description:** {description}")

            # Details in columns
            col1, col2 = st.columns(2)

            with col1:
                if item.get("owner"):
                    st.markdown(f"**👤 Owner:** {item['owner']}")
                else:
                    st.markdown("**👤 Owner:** *Not specified*")

                if item.get("due_date"):
                    st.markdown(f"**📅 Due Date:** {item['due_date']}")
                else:
                    st.markdown("**📅 Due Date:** *Not specified*")

            with col2:
                st.markdown(f"**📊 Status:** {status_text}")


def render_summary_section(intelligence_data: dict):
    """Render the summary section with markdown summary."""
    st.subheader("📋 Meeting Summary")

    # Display the markdown summary
    summary = intelligence_data.get("summary", "No summary available")
    st.markdown(summary)


def render_processing_stats_section(intelligence_data: dict):
    """Render processing statistics."""
    st.subheader("📊 Processing Statistics")

    processing_stats = intelligence_data.get("processing_stats", {})

    if processing_stats:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if "vtt_chunks" in processing_stats:
                st.metric("VTT Chunks", processing_stats["vtt_chunks"])

        with col2:
            if "semantic_chunks" in processing_stats:
                st.metric("Semantic Chunks", processing_stats["semantic_chunks"])

        with col3:
            if "api_calls" in processing_stats:
                st.metric("API Calls", processing_stats["api_calls"])

        with col4:
            if "time_ms" in processing_stats:
                seconds = processing_stats["time_ms"] / 1000
                st.metric("Processing Time", f"{seconds:.1f}s")

        # Additional stats
        if "avg_importance" in processing_stats:
            st.metric(
                "Avg Importance",
                f"{processing_stats['avg_importance']:.2f}",
            )
    else:
        st.info("No processing statistics available.")


def render_export_section(intelligence_data: dict):
    """Render export functionality."""
    st.subheader("📤 Export Options")

    summary = intelligence_data.get("summary", "No summary available")
    action_items = intelligence_data.get("action_items", [])

    col1, col2 = st.columns(2)
    with col1:
        # Markdown export
        markdown_data = (
            f"# Meeting Intelligence Report\n\n{summary}\n\n## Action Items\n\n"
        )
        for i, item in enumerate(action_items, 1):
            description = item.get("description", "No description")
            markdown_data += f"{i}. **{description}**\n"
            if item.get("owner"):
                markdown_data += f"   - Owner: {item['owner']}\n"
            if item.get("due_date"):
                markdown_data += f"   - Due: {item['due_date']}\n"
            markdown_data += "\n"

        st.download_button(
            label="📝 Download Markdown",
            data=markdown_data,
            file_name=f"meeting_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            help="Export as formatted Markdown report",
        )

    with col2:
        # CSV export for action items
        csv_data = "Description,Owner,Due Date\n"
        for item in action_items:
            description = (item.get("description") or "").replace('"', '""')
            owner = (item.get("owner") or "").replace('"', '""')
            due_date = (item.get("due_date") or "").replace('"', '""')
            csv_data += f'"{description}","{owner}","{due_date}"\n'

        st.download_button(
            label="📊 Download CSV",
            data=csv_data,
            file_name=f"action_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            help="Export action items as CSV spreadsheet",
        )

    # Preview section
    st.markdown("### Export Preview")
    preview_tab1, preview_tab2 = st.tabs(["Markdown Preview", "CSV Preview"])

    with preview_tab1:
        with st.expander("🔍 Markdown Preview"):
            # Show first part of markdown
            markdown_preview = (
                markdown_data[:1500] + "..."
                if len(markdown_data) > 1500
                else markdown_data
            )
            st.markdown(markdown_preview)

    with preview_tab2:
        with st.expander("🔍 CSV Preview"):
            if action_items:
                # Show CSV as table
                st.code(
                    csv_data[:800] + "..." if len(csv_data) > 800 else csv_data,
                    language="csv",
                )
            else:
                st.info("No action items to export in CSV format.")


def extract_intelligence_with_api(
    transcript_id: str, detail_level: str = "comprehensive"
):
    """Extract intelligence using the backend API with polling."""

    logger.info(
        "Starting intelligence extraction via API",
        transcript_id=transcript_id,
        detail_level=detail_level,
    )

    # Start intelligence extraction
    with st.status(
        "Starting intelligence extraction...", expanded=True
    ) as extract_status:
        idempotency_key = f"{transcript_id}:{detail_level}"
        success, task_id_or_error, message = api_client.extract_intelligence(
            transcript_id, detail_level, idempotency_key=idempotency_key
        )

        if not success:
            extract_status.update(label="❌ Extraction failed", state="error")
            st.error(task_id_or_error)
            return None

        task_id = task_id_or_error
        extract_status.update(label="✅ Extraction started", state="complete")
        st.info(f"Task ID: {task_id}")
        # Persist task_id in URL so refresh can resume
        q = st.query_params
        q["task"] = task_id
        st.query_params = q

    # Poll for completion with progress updates
    with st.status(
        "Extracting meeting intelligence...", expanded=True
    ) as process_status:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        # Metrics for live updates
        metrics_cols = st.columns(4)
        with metrics_cols[0]:
            progress_metric = st.empty()
        with metrics_cols[1]:
            detail_metric = st.empty()
        with metrics_cols[2]:
            time_metric = st.empty()
        with metrics_cols[3]:
            task_metric = st.empty()

        start_time = time.time()

        def update_progress(progress: float, message: str):
            """Update the UI with current progress."""
            progress_bar.progress(progress)
            status_text.text(message)

            # Update metrics
            progress_metric.metric("Progress", f"{progress*100:.1f}%")
            detail_metric.metric("Detail Level", detail_level.replace("_", " ").title())

            elapsed = time.time() - start_time
            time_metric.metric("Elapsed", f"{elapsed:.1f}s")
            task_metric.metric("Task", task_id[:8])

        # Poll until complete
        success, final_data = api_client.poll_until_complete(
            task_id,
            progress_callback=update_progress,
            poll_interval=2.0,
            timeout=600.0,  # 10 minutes max for intelligence
        )

        if not success:
            process_status.update(
                label="❌ Intelligence extraction failed", state="error"
            )
            error = final_data.get("error", "Unknown error")
            st.error(f"Intelligence extraction failed: {error}")
            return None

        # Success!
        process_status.update(
            label="✅ Intelligence extraction completed", state="complete"
        )
        result = final_data.get("result")

        if result:
            # Store intelligence in session state
            st.session_state.transcript["intelligence"] = result
            st.session_state.intelligence_extracted = True

            st.success("🎉 Meeting intelligence extracted successfully!")

            return result
        else:
            st.error("No intelligence data returned from backend")
            return None


def main():
    """Main function for the Intelligence page."""
    st.set_page_config(page_title="Meeting Intelligence", page_icon="🧠", layout="wide")

    st.title("🧠 Meeting Intelligence")
    st.markdown(
        "Extract and view meeting summaries, action items, and key insights using AI."
    )

    # Check backend health
    is_healthy, health_data = api_client.health_check()
    if not is_healthy:
        st.error("❌ Backend service is not available")
        st.error(f"Error: {health_data.get('error', 'Unknown error')}")
        st.info("Make sure the FastAPI backend is running")
        st.stop()

    # Initialize session state if needed
    if "transcript" not in st.session_state:
        st.session_state.transcript = None
    if "intelligence_extracted" not in st.session_state:
        st.session_state.intelligence_extracted = False

    # Early resume: if a task id is present in the URL, attempt to resume intelligence extraction
    q = st.query_params
    task_in_url = q.get("task")
    if task_in_url:
        # Verify the task type before resuming to avoid attaching to the wrong task
        success, status_data = api_client.get_task_status(task_in_url)
        if success and status_data.get("type") == "intelligence_extraction":
            with st.status(
                "Resuming ongoing intelligence extraction...", expanded=True
            ) as resume_status:
                progress_text = st.empty()

                def _resume_progress(p, m):
                    progress_text.text(f"{p*100:.1f}% - {m}")

                ok, data = api_client.poll_until_complete(
                    task_in_url,
                    progress_callback=_resume_progress,
                    poll_interval=2.0,
                    timeout=600.0,
                )
                if ok:
                    result = data.get("result")
                    if result:
                        # Ensure a minimal transcript object exists
                        if not st.session_state.get("transcript"):
                            st.session_state.transcript = {}
                        st.session_state.transcript["intelligence"] = result
                        st.session_state.intelligence_extracted = True
                        resume_status.update(
                            label="✅ Intelligence task resumed and completed",
                            state="complete",
                        )
                        # Clear the task param now that it's done
                        q.pop("task", None)
                        st.query_params = q
        elif success:
            # Not an intelligence task; ignore and optionally clear the param
            if status_data.get("type") != "intelligence_extraction":
                q.pop("task", None)
                st.query_params = q

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
            "• 📤 **Export Options** - Download results in Markdown or CSV formats"
        )
        return

    transcript = st.session_state.transcript

    # Resume of intelligence tasks is handled earlier before transcript checks.

    # Check if intelligence has been extracted
    if "intelligence" not in transcript:
        st.info("🧠 Intelligence not yet extracted from this transcript.")

        st.markdown("---")

        # Industry-standard detail level selector
        detail_level = st.selectbox(
            "📊 Summary Detail Level",
            ["comprehensive", "standard", "technical_focus"],
            index=0,  # Default to comprehensive
            format_func=lambda x: x.replace("_", " ").title(),
            help="""
            • **Comprehensive**: Rich summaries with full context (recommended for most meetings)
            • **Standard**: Key decisions and action items with basic context
            • **Technical Focus**: Preserves ALL technical details, numbers, and specifications verbatim
            """,
        )

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

            # Extract intelligence using the transcript task_id
            intelligence_data = extract_intelligence_with_api(
                transcript_task_id, detail_level
            )

            if intelligence_data:
                st.rerun()  # Refresh to show results

        st.markdown("**This will:**")
        st.markdown("• 📋 Generate executive and detailed summaries")
        st.markdown("• 🎯 Identify action items with owners and deadlines")
        st.markdown("• 🔍 Extract key decisions and topics")
        st.markdown("• ⚡ Process using parallel AI agents for speed")

        return

    # Display intelligence results
    intelligence_data = transcript["intelligence"]

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

    st.markdown("---")

    # Main content in tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Summary", "🎯 Action Items", "📊 Statistics", "📤 Export"]
    )

    with tab1:
        render_summary_section(intelligence_data)

    with tab2:
        render_action_items(action_items)

    with tab3:
        render_processing_stats_section(intelligence_data)

    with tab4:
        render_export_section(intelligence_data)

    # Footer with regeneration option
    st.markdown("---")

    # Re-extraction section
    with st.expander("🔄 Re-extract Intelligence with Different Detail Level"):
        col1, col2 = st.columns([2, 1])

        with col1:
            # Detail level selector for re-extraction
            re_detail_level = st.selectbox(
                "📊 New Detail Level",
                ["comprehensive", "standard", "technical_focus"],
                index=0,  # Default to comprehensive
                key="re_extract_detail_level",
                format_func=lambda x: x.replace("_", " ").title(),
                help="""
                • **Comprehensive**: Rich summaries with full context (recommended for most meetings)
                • **Standard**: Key decisions and action items with basic context
                • **Technical Focus**: Preserves ALL technical details, numbers, and specifications verbatim
                """,
            )

        with col2:
            if st.button(
                "🔄 Re-extract Intelligence", type="secondary", use_container_width=True
            ):
                # Clear existing intelligence and re-extract with new detail level
                if "intelligence" in st.session_state.transcript:
                    del st.session_state.transcript["intelligence"]

                # Get the transcript task_id from session state
                transcript_task_id = st.session_state.get("transcript_task_id")

                if not transcript_task_id:
                    st.error(
                        "❌ No transcript task ID found. Please re-process your transcript."
                    )
                    return

                intelligence_data = extract_intelligence_with_api(
                    transcript_task_id, re_detail_level
                )

                if intelligence_data:
                    st.rerun()

    st.markdown(
        "*Intelligence extracted from processed transcript. Results are AI-generated and may need review.*"
    )


if __name__ == "__main__":
    main()
