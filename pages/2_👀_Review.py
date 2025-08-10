"""
Review Page - Progressive review interface with export functionality.

This page shows processed segments categorized by confidence level, allowing users
to review and export the final cleaned transcript.
"""

import streamlit as st
import structlog

from services.transcript_service import TranscriptService
from utils.ui_components import render_metrics_row

logger = structlog.get_logger(__name__)


@st.cache_data
def _get_cached_document_summary(document_id: str, total_segments: int):
    """Cache document summary to avoid recomputation."""
    service = get_transcript_service()
    document = st.session_state.document
    return service.get_document_change_summary(document)


def show_change_summary_dashboard(document) -> None:
    """Display document-level change summary with metrics."""

    # Get change summary from service (cached)
    try:
        summary = _get_cached_document_summary(
            document.filename, len(document.segments)
        )
    except Exception as e:
        st.error(f"Error loading change summary: {str(e)}")
        return

    # Metrics row using shared component
    delta_text = f"{summary['change_density']:.1%} of document"
    if len(document.segments) > 0:
        segments_pct = f"{summary['segments_modified']/len(document.segments)*100:.1f}%"
    else:
        segments_pct = "0%"
    avg_conf = summary["avg_confidence"]
    quality_text = (
        "High Quality"
        if avg_conf > 0.8
        else ("Good Quality" if avg_conf > 0.6 else "Needs Review")
    )

    metrics = [
        ("Total Changes", summary["total_changes"], delta_text),
        ("Segments Modified", summary["segments_modified"], segments_pct),
        ("Avg Confidence", f"{avg_conf:.2f}", quality_text),
        ("Change Types", len(summary["change_types"]), None),
    ]
    render_metrics_row(metrics)

    # Change type breakdown
    if summary["change_types"]:
        st.subheader("🔧 Types of Changes Made")
        change_cols = st.columns(len(summary["change_types"]))
        for i, (change_type, count) in enumerate(summary["change_types"].items()):
            with change_cols[i]:
                st.metric(change_type.replace("_", " ").title(), count)

    # Confidence distribution using shared component
    if any(summary["confidence_stats"].values()):
        st.subheader("🎯 Confidence Distribution")
        confidence_metrics = [
            ("High (≥80%)", summary["confidence_stats"]["high"], "🟢"),
            ("Medium (60-79%)", summary["confidence_stats"]["medium"], "🟡"),
            ("Low (<60%)", summary["confidence_stats"]["low"], "🔴"),
        ]
        render_metrics_row(confidence_metrics)


@st.fragment
def show_document_diff_view(service: TranscriptService, document) -> None:
    """Display full document diff with navigation."""
    from typing import Literal, cast

    # View mode selector with icons - simplified to 2 modes
    _selected_mode = st.radio(
        "View Mode",
        ["inline", "side_by_side"],
        format_func=lambda x: {
            "inline": "✏️ Inline Changes",
            "side_by_side": "↔️ Side-by-Side",
        }[x],
        index=0,  # Default to inline (Google Docs style)
        horizontal=True,
        key="doc_view_mode",
    )

    # Explicitly cast to the expected Literal type to satisfy static type checkers
    view_mode: Literal["inline", "side_by_side"] = cast(
        Literal["inline", "side_by_side"], _selected_mode
    )

    # Generate and display document diff
    try:
        if view_mode == "side_by_side":
            # Use Streamlit native rendering for side-by-side view
            from utils.document_diff_viewer import DocumentDiffViewer

            document_diff_viewer = DocumentDiffViewer()

            diff_data = document_diff_viewer.generate_side_by_side_data(
                document.segments, document.cleaning_results, document.review_decisions
            )

            # Create two columns for side-by-side display
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("📄 Original Document")
                for segment_data in diff_data["segments"]:
                    st.text(f"S{segment_data['sequence_number']}:")
                    st.text(segment_data["original"])
                    if segment_data != diff_data["segments"][-1]:  # Not last segment
                        st.divider()

            with col2:
                st.subheader("✨ Cleaned Document")
                for segment_data in diff_data["segments"]:
                    st.text(f"S{segment_data['sequence_number']}:")

                    # Highlight segments with changes
                    if segment_data["has_changes"]:
                        st.info(
                            f"🔧 Changes: {', '.join(segment_data['changes'][:2])}..."
                        )
                        st.text(segment_data["cleaned"])
                    else:
                        st.text(segment_data["cleaned"])

                    if segment_data != diff_data["segments"][-1]:  # Not last segment
                        st.divider()
        else:
            # Use existing HTML rendering for inline view
            diff_html = service.generate_document_diff(document, view_mode)
            st.markdown(diff_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error generating document diff: {str(e)}")
        logger.error(
            "Document diff generation failed",
            error=str(e),
            exc_info=True,
            phase="diff_generation",
        )
        return

    # Change navigation (only show for non-inline views where navigation makes sense)
    if view_mode != "inline":
        try:
            changes = service.get_change_navigation(document)
            if changes:
                st.subheader("🧭 Jump to Changes")
                change_options = [
                    f"Segment {c['segment_num']}: {c['type']} ({c['change_count']} changes)"
                    for c in changes
                ]
                selected = st.selectbox(
                    "Navigate to change",
                    options=change_options,
                    key="change_navigation",
                )
                if selected:
                    st.info(
                        "💡 Tip: Use your browser's Find feature (Ctrl+F) to locate specific segments in the diff above."
                    )
        except Exception as e:
            logger.error(
                "Change navigation generation failed",
                error=str(e),
                exc_info=True,
                phase="navigation_generation",
            )


# Session state is now managed globally through sidebar preferences


def export_results() -> None:
    """Export the final cleaned transcript using the service layer."""
    try:
        service = get_transcript_service()
        user_decisions = st.session_state.get("user_decisions", {})

        final_content = service.export_transcript(
            document=st.session_state.document, user_decisions=user_decisions
        )

        # Create download button
        st.download_button(
            label="💾 Download Cleaned Transcript",
            data=final_content,
            file_name=f"{st.session_state.document.filename}_cleaned.txt",
            mime="text/plain",
            help="Download the final cleaned transcript with all improvements applied",
        )

        st.success("✅ Export ready! Click the download button above.")

        # Show preview
        with st.expander("👀 Preview (first 1000 characters)"):
            st.text(
                final_content[:1000] + "..."
                if len(final_content) > 1000
                else final_content
            )

    except Exception as e:
        logger.error("Export failed", error=str(e), phase="export")
        st.error(f"❌ Export failed: {str(e)}")


# STANDALONE PAGE SCRIPT - Execute directly
document = st.session_state.get("document")
if not document:
    st.warning("⚠️ No document found in session. Please upload and process a file.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "📤 Go to Upload & Process", type="primary", use_container_width=True
        ):
            st.switch_page("pages/1_📤_Upload_Process.py")

    with col2:
        st.info(
            "💡 **Tip**: If you recently processed a document and see this message after refreshing the page, this is normal - Streamlit resets the session on refresh. Please re-upload and process your document."
        )

    st.stop()

if not st.session_state.get("processing_complete", False):
    st.warning("Document processing is not complete. Please complete processing first.")
    if st.button("🔄 Go to Upload & Process", use_container_width=True):
        st.switch_page("pages/1_📤_Upload_Process.py")
    st.stop()


# Initialize service for this page (cached)
@st.cache_resource
def get_transcript_service() -> TranscriptService:
    """Get cached TranscriptService instance."""
    return TranscriptService()


service = get_transcript_service()

# Fix: Check both document categories AND session state
has_categories = (
    hasattr(document, "segment_categories") and document.segment_categories
) or st.session_state.get("categories", [])

if not has_categories:
    st.error("❌ No processing results found. Please reprocess the document.")
    if st.button("🔄 Go to Processing"):
        st.rerun()
    st.stop()


# Get statistics for export info (cached)
@st.cache_data
def _get_cached_category_stats(num_categories: int):
    """Cache category stats to avoid recomputation."""
    return service.get_category_stats(st.session_state.categories)


st.subheader("📥 Export Results")
if st.session_state.categories:
    stats = _get_cached_category_stats(len(st.session_state.categories))

    # Quick statistics before export using shared component
    export_metrics = [
        ("Total Segments", len(document.segments), None),
        (
            "Auto-accepted",
            stats["auto_accept"],
            f"{stats['auto_accept']/len(document.segments)*100:.1f}%",
        ),
        (
            "Needs Review",
            stats["needs_review"],
            f"{stats['needs_review']/len(document.segments)*100:.1f}%",
        ),
        (
            "AI Flagged",
            stats["ai_flagged"],
            f"{stats['ai_flagged']/len(document.segments)*100:.1f}%",
        ),
    ]
    render_metrics_row(export_metrics)

    # Export button
    if st.button("📄 Export Cleaned Transcript", type="primary"):
        export_results()
else:
    st.warning("No processing results available for export.")
st.divider()

st.subheader("🖍️ Review Results")
# Main interface with beautiful tabs (Export moved to separate section)
main_tabs = st.tabs(["📄 Document Diff View", "📊 Summary"])

with main_tabs[0]:  # Document View
    show_document_diff_view(service, document)

with main_tabs[1]:  # Summary
    show_change_summary_dashboard(document)

# Export section - separate from tabs to avoid rerun issues
st.divider()
