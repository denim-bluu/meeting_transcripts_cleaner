"""
Review Page - Simple interface for reviewing cleaned transcripts.

Shows processing results and allows export in multiple formats.
"""

import streamlit as st
import structlog

from config import Config, configure_structlog
from services.transcript_service import TranscriptService
from utils.ui_components import render_metrics_row

# Configure logging
configure_structlog()
logger = structlog.get_logger(__name__)

st.set_page_config(page_title="Review Results", page_icon="👀", layout="wide")

st.header("👀 Review Cleaned Transcript")

# Check if we have processed transcript
cleaned_transcript = st.session_state.get("cleaned_transcript")
if not cleaned_transcript or "cleaned_chunks" not in cleaned_transcript:
    st.warning(
        "⚠️ No processed transcript found. Please upload and process a file first."
    )

    # Debug info
    if st.checkbox("Show debug info"):
        st.write("Session state keys:", list(st.session_state.keys()))
        if cleaned_transcript:
            st.write("Cleaned transcript keys:", list(cleaned_transcript.keys()))

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "📤 Go to Upload & Process", type="primary", use_container_width=True
        ):
            st.switch_page("pages/1_📤_Upload_Process.py")

    with col2:
        st.info("💡 **Tip**: Process a VTT file first to see review results here.")

    st.stop()

# Get the cleaned transcript
cleaned_transcript = st.session_state.cleaned_transcript
original_transcript = st.session_state.get("transcript", {})

# Show processing summary
st.subheader("📊 Processing Summary")

if cleaned_transcript and "review_results" in cleaned_transcript:
    review_results = cleaned_transcript["review_results"]
    cleaned_chunks = cleaned_transcript.get("cleaned_chunks", [])

    # Calculate metrics
    total_chunks = len(cleaned_chunks)
    accepted_count = sum(1 for r in review_results if r.accept)
    avg_quality = (
        sum(r.quality_score for r in review_results) / len(review_results)
        if review_results
        else 0
    )
    total_changes = sum(len(c.changes_made) for c in cleaned_chunks)

    # Show metrics
    metrics = [
        ("Total Chunks", total_chunks, None),
        ("Accepted", accepted_count, f"{accepted_count / total_chunks * 100:.1f}%"),
        (
            "Needs Review",
            total_chunks - accepted_count,
            f"{(total_chunks - accepted_count) / total_chunks * 100:.1f}%",
        ),
        (
            "Avg Quality",
            f"{avg_quality:.2f}",
            "Good" if avg_quality > 0.7 else "Needs Review",
        ),
        ("Total Changes", total_changes, None),
    ]
    render_metrics_row(metrics)

    # Quality distribution
    st.subheader("🎯 Quality Distribution")
    quality_scores = [r.quality_score for r in review_results]
    high_quality = sum(1 for score in quality_scores if score >= 0.8)
    medium_quality = sum(1 for score in quality_scores if 0.6 <= score < 0.8)
    low_quality = sum(1 for score in quality_scores if score < 0.6)

    quality_metrics = [
        ("High Quality (≥0.8)", high_quality, "🟢"),
        ("Medium Quality (0.6-0.8)", medium_quality, "🟡"),
        ("Low Quality (<0.6)", low_quality, "🔴"),
    ]
    render_metrics_row(quality_metrics)

# Export section
st.subheader("📥 Export Options")

if cleaned_transcript:
    service = TranscriptService(Config.OPENAI_API_KEY)

    # Export format selection
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📄 Export as VTT", use_container_width=True):
            vtt_content = service.export(cleaned_transcript, "vtt")
            st.download_button(
                label="💾 Download VTT",
                data=vtt_content,
                file_name="cleaned_transcript.vtt",
                mime="text/vtt",
            )

    with col2:
        if st.button("📝 Export as Text", use_container_width=True):
            txt_content = service.export(cleaned_transcript, "txt")
            st.download_button(
                label="💾 Download Text",
                data=txt_content,
                file_name="cleaned_transcript.txt",
                mime="text/plain",
            )

    with col3:
        if st.button("🔧 Export as JSON", use_container_width=True):
            json_content = service.export(cleaned_transcript, "json")
            st.download_button(
                label="💾 Download JSON",
                data=json_content,
                file_name="cleaned_transcript.json",
                mime="application/json",
            )

# Review detailed results
st.subheader("🔍 Detailed Review")

if cleaned_transcript and "cleaned_chunks" in cleaned_transcript:
    # Show chunks with review status
    tabs = st.tabs(["📋 Chunk Summary", "📄 Full Transcript", "🔧 Changes Made"])

    with tabs[0]:  # Chunk Summary
        st.markdown("**Processing Results by Chunk:**")

        for i, (chunk, review) in enumerate(
            zip(
                cleaned_transcript.get("cleaned_chunks", []),
                cleaned_transcript.get("review_results", []),
                strict=False,
            )
        ):
            with st.expander(
                f"Chunk {i + 1} - Quality: {review.quality_score:.2f} {'✅' if review.accept else '⚠️'}"
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Original:**")
                    original_chunk = (
                        original_transcript["chunks"][i]
                        if i < len(original_transcript.get("chunks", []))
                        else None
                    )
                    if original_chunk:
                        st.text(
                            original_chunk.to_transcript_text()[:300] + "..."
                            if len(original_chunk.to_transcript_text()) > 300
                            else original_chunk.to_transcript_text()
                        )

                with col2:
                    st.markdown("**Cleaned:**")
                    cleaned_text = chunk.cleaned_text
                    st.text(
                        cleaned_text[:300] + "..."
                        if len(cleaned_text) > 300
                        else cleaned_text
                    )

                # Show changes and issues
                if chunk.changes_made:
                    st.markdown("**Changes Made:**")
                    for change in chunk.changes_made:
                        st.markdown(f"- {change}")

                if review.issues:
                    st.markdown("**Issues Found:**")
                    for issue in review.issues:
                        st.markdown(f"- {issue}")

    with tabs[1]:  # Full Transcript
        st.markdown("**Complete Cleaned Transcript:**")
        final_transcript = cleaned_transcript.get("final_transcript", "")
        st.text_area(
            "Cleaned Transcript",
            value=final_transcript,
            height=400,
            help="The complete cleaned transcript ready for export",
        )

    with tabs[2]:  # Changes Made
        st.markdown("**Summary of All Changes:**")

        all_changes = []
        cleaned_chunks = cleaned_transcript.get("cleaned_chunks", [])
        for chunk in cleaned_chunks:
            all_changes.extend(chunk.changes_made)

        if all_changes:
            # Count change types
            change_counts = {}
            for change in all_changes:
                change_counts[change] = change_counts.get(change, 0) + 1

            # Show top changes
            sorted_changes = sorted(
                change_counts.items(), key=lambda x: x[1], reverse=True
            )

            for change, count in sorted_changes[:10]:  # Top 10
                st.markdown(f"- **{change}** ({count} times)")
        else:
            st.info("No changes were made to the transcript.")

else:
    st.info(
        "No detailed results available. The transcript may not have been fully processed."
    )
