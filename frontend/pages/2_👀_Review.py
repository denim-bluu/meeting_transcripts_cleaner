from datetime import datetime
import json

from api_client import api_client
from config import configure_structlog
import streamlit as st
import structlog
from utils.ui_components import render_metrics_row

# Configure logging
configure_structlog()
logger = structlog.get_logger(__name__)

logger.info("Review page initialized", streamlit_page=True, mode="api_client")


def get_quality_status(score: float) -> tuple[str, str, str]:
    """Get quality status icon, text, and color based on score."""
    if score >= 0.8:
        return "✅", "High Quality", "green"
    elif score >= 0.6:
        return "🟡", "Medium Quality", "orange"
    else:
        return "🔴", "Low Quality", "red"


def generate_export_data(transcript_data: dict, format_type: str) -> str:
    """Generate export data in the specified format."""

    if format_type == "vtt":
        # Generate VTT format using cleaned text if available
        vtt_content = "WEBVTT\n\n"

        chunks = transcript_data.get("chunks", [])
        cleaned_chunks = transcript_data.get("cleaned_chunks", [])

        for i, chunk in enumerate(chunks):
            entries = chunk.get("entries", [])
            for entry in entries:
                start_time = entry.get("start_time", 0)
                end_time = entry.get("end_time", 0)
                speaker = entry.get("speaker", "Speaker")

                # Use cleaned text if available, otherwise original
                if i < len(cleaned_chunks) and cleaned_chunks[i]:
                    # For cleaned export, we'll use the original structure but note it's cleaned
                    text = entry.get("text", "")
                else:
                    text = entry.get("text", "")

                # Format timestamps
                start_formatted = format_timestamp(start_time)
                end_formatted = format_timestamp(end_time)

                vtt_content += f"{start_formatted} --> {end_formatted}\n"
                vtt_content += f"{speaker}: {text}\n\n"

        return vtt_content

    elif format_type == "txt":
        # Generate plain text format with cleaned content
        txt_content = "# Meeting Transcript (Cleaned)\n\n"
        txt_content += (
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        # Use final_transcript if available (cleaned version)
        final_transcript = transcript_data.get("final_transcript")
        if final_transcript:
            txt_content += final_transcript
        else:
            # Fallback to original chunks
            chunks = transcript_data.get("chunks", [])
            for chunk in chunks:
                entries = chunk.get("entries", [])
                for entry in entries:
                    speaker = entry.get("speaker", "Speaker")
                    text = entry.get("text", "")
                    txt_content += f"{speaker}: {text}\n"

        return txt_content

    elif format_type == "json":
        # Generate JSON format with all processing data
        export_data = {
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "source": "Meeting Transcript Cleaner",
                "speakers": transcript_data.get("speakers", []),
                "duration": transcript_data.get("duration", 0),
                "total_chunks": len(transcript_data.get("chunks", [])),
                "processing_stats": transcript_data.get("processing_stats", {}),
            },
            "transcript": transcript_data,
        }
        return json.dumps(export_data, indent=2, ensure_ascii=False)

    return ""


def format_timestamp(seconds: float) -> str:
    """Format seconds to VTT timestamp format (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def main():
    """Main function for the Review page."""
    st.set_page_config(page_title="Review Results", page_icon="👀", layout="wide")

    st.title("👀 Review Cleaned Transcript")
    st.markdown(
        "Review your processed transcript with quality assessment and export options."
    )

    # Check backend health
    is_healthy, health_data = api_client.health_check()
    if not is_healthy:
        st.error("❌ Backend service is not available")
        st.error(f"Error: {health_data.get('error', 'Unknown error')}")
        st.info("Make sure the FastAPI backend is running")
        st.stop()

    # Check if we have processed transcript
    transcript = st.session_state.get("transcript")
    if not transcript:
        st.warning(
            "⚠️ No processed transcript found. Please upload and process a file first."
        )

        # Debug info
        if st.checkbox("Show debug info"):
            st.write("Session state keys:", list(st.session_state.keys()))

        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "📤 Go to Upload & Process", type="primary", use_container_width=True
            ):
                st.switch_page("pages/1_📤_Upload_Process.py")

        with col2:
            st.info("💡 **Tip**: Process a VTT file first to see review results here.")

        st.stop()

    # Get processing results
    chunks = transcript.get("chunks", [])
    cleaned_chunks = transcript.get("cleaned_chunks", [])
    review_results = transcript.get("review_results", [])
    speakers = transcript.get("speakers", [])
    duration = transcript.get("duration", 0)
    final_transcript = transcript.get("final_transcript", "")
    transcript.get("processing_stats", {})

    # Calculate total entries
    total_entries = sum(len(chunk.get("entries", [])) for chunk in chunks)

    # Show processing summary
    st.subheader("📊 Processing Summary")

    if cleaned_chunks and review_results:
        # Calculate quality metrics - Handle serialized Pydantic models (dicts)
        total_chunks = len(cleaned_chunks)
        accepted_count = sum(1 for r in review_results if r and r.get("accept", False))
        avg_quality = (
            sum(r.get("quality_score", 0) for r in review_results if r)
            / len(review_results)
            if review_results
            else 0
        )
        total_changes = sum(len(c.get("changes_made", [])) for c in cleaned_chunks if c)

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
        quality_scores = [r.get("quality_score", 0) for r in review_results if r]
        high_quality = sum(1 for score in quality_scores if score >= 0.8)
        medium_quality = sum(1 for score in quality_scores if 0.6 <= score < 0.8)
        low_quality = sum(1 for score in quality_scores if score < 0.6)

        quality_metrics = [
            ("High Quality (≥0.8)", high_quality, "🟢"),
            ("Medium Quality (0.6-0.8)", medium_quality, "🟡"),
            ("Low Quality (<0.6)", low_quality, "🔴"),
        ]
        render_metrics_row(quality_metrics)
    else:
        # Basic metrics when no cleaning results available
        metrics = [
            ("Total Chunks", len(chunks), None),
            ("Total Entries", total_entries, None),
            ("Speakers", len(speakers), None),
            (
                "Duration",
                f"{duration:.1f}s",
                f"{duration/60:.1f}m" if duration > 60 else None,
            ),
        ]
        render_metrics_row(metrics)

    # Show speakers
    if speakers:
        st.info(f"**Meeting participants:** {', '.join(speakers)}")

    # Export section
    st.subheader("📥 Export Options")

    # Export format selection
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📄 Export as VTT", use_container_width=True):
            vtt_content = generate_export_data(transcript, "vtt")
            st.download_button(
                label="💾 Download VTT",
                data=vtt_content,
                file_name=f"cleaned_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.vtt",
                mime="text/vtt",
                help="Download as WebVTT format (cleaned version)",
            )

    with col2:
        if st.button("📝 Export as Text", use_container_width=True):
            txt_content = generate_export_data(transcript, "txt")
            st.download_button(
                label="💾 Download Text",
                data=txt_content,
                file_name=f"cleaned_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                help="Download as plain text format (cleaned version)",
            )

    with col3:
        if st.button("🔧 Export as JSON", use_container_width=True):
            json_content = generate_export_data(transcript, "json")
            st.download_button(
                label="💾 Download JSON",
                data=json_content,
                file_name=f"cleaned_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                help="Download complete processing data as JSON",
            )

    # Review detailed results
    st.subheader("🔍 Detailed Review")

    if chunks:
        # Show transcript content in tabs - restore original simple design
        tabs = st.tabs(["📋 By Chunks", "📄 Full Transcript"])

        with tabs[0]:  # By Chunks
            st.markdown("**Processing Results by Chunk with Quality Assessment:**")

            if cleaned_chunks and review_results:
                # Show chunks with quality scores and side-by-side comparison
                for i, (chunk, clean_result, review) in enumerate(
                    zip(chunks, cleaned_chunks, review_results, strict=False)
                ):
                    if not clean_result or not review:
                        continue

                    # Get quality info - Handle serialized Pydantic models (dicts)
                    quality_score = review.get("quality_score", 0)
                    quality_icon, quality_text, quality_color = get_quality_status(
                        quality_score
                    )
                    accept_status = review.get("accept", False)

                    with st.expander(
                        f"{quality_icon} **Chunk {i + 1}** - Quality: {quality_score:.2f} ({quality_text}) {'✅ Accepted' if accept_status else '⚠️ Needs Review'}"
                    ):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("**🔤 Original Text:**")
                            original_text = chunk.get("entries", [])
                            if original_text:
                                # Convert chunk entries to readable text
                                original_content = ""
                                for entry in original_text:
                                    speaker = entry.get("speaker", "Unknown")
                                    text = entry.get("text", "")
                                    original_content += f"{speaker}: {text}\n"

                                st.text_area(
                                    f"Original Chunk {i + 1}",
                                    value=original_content,
                                    height=150,
                                    key=f"original_{i}",
                                    help="Original text before cleaning",
                                )

                        with col2:
                            st.markdown("**✨ Cleaned Text:**")
                            cleaned_text = clean_result.get("cleaned_text", "")
                            confidence = clean_result.get("confidence", 0)

                            st.text_area(
                                f"Cleaned Chunk {i + 1} (Confidence: {confidence:.2f})",
                                value=cleaned_text,
                                height=150,
                                key=f"cleaned_{i}",
                                help="Text after AI cleaning and processing",
                            )

                        # Quality metrics row
                        st.markdown("**📊 Quality Metrics:**")
                        metrics_cols = st.columns(4)
                        with metrics_cols[0]:
                            st.metric("Quality Score", f"{quality_score:.2f}")
                        with metrics_cols[1]:
                            st.metric("Confidence", f"{confidence:.2f}")
                        with metrics_cols[2]:
                            st.metric("Status", quality_text)
                        with metrics_cols[3]:
                            st.metric("Accept", "Yes" if accept_status else "No")
            else:
                # Fallback when no cleaning results available
                st.info(
                    "No detailed cleaning analysis available. Showing basic chunk information."
                )
                for i, chunk in enumerate(chunks):
                    entries = chunk.get("entries", [])
                    if not entries:
                        continue

                    # Calculate chunk duration and speaker info
                    start_time = min(entry.get("start_time", 0) for entry in entries)
                    end_time = max(entry.get("end_time", 0) for entry in entries)
                    chunk_duration = end_time - start_time
                    chunk_speakers = list(
                        {entry.get("speaker", "Unknown") for entry in entries}
                    )

                    with st.expander(
                        f"📋 Chunk {i + 1} - {len(entries)} entries, {chunk_duration:.1f}s, Speakers: {', '.join(chunk_speakers)}"
                    ):
                        for entry in entries:
                            start_time = entry.get("start_time", 0)
                            speaker = entry.get("speaker", "Unknown")
                            text = entry.get("text", "")

                            # Format timestamp
                            timestamp = format_timestamp(start_time)

                            st.markdown(f"**[{timestamp}] {speaker}:** {text}")

        with tabs[1]:  # Full Transcript
            st.markdown("**Complete cleaned transcript:**")

            if final_transcript:
                st.text_area(
                    "Final Cleaned Transcript",
                    value=final_transcript,
                    height=400,
                    help="Complete cleaned transcript ready for export",
                )
            else:
                # Fallback to original content
                full_text = ""
                for chunk in chunks:
                    entries = chunk.get("entries", [])
                    for entry in entries:
                        speaker = entry.get("speaker", "Unknown")
                        text = entry.get("text", "")
                        full_text += f"{speaker}: {text}\n"

                st.text_area(
                    "Original Transcript",
                    value=full_text,
                    height=400,
                    help="Complete transcript text",
                )

    else:
        st.info("No transcript chunks available for review.")

    # Action section
    st.markdown("---")
    st.subheader("🧠 Next Steps")

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "🧠 Extract Intelligence", type="primary", use_container_width=True
        ):
            st.switch_page("pages/3_🧠_Intelligence.py")

    with col2:
        if st.button("📤 Upload New File", use_container_width=True):
            st.switch_page("pages/1_📤_Upload_Process.py")

    st.markdown(
        "*Transcript processed through our microservices backend with AI-powered cleaning and quality assessment.*"
    )


if __name__ == "__main__":
    main()
