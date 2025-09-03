"""Review Cleaned Transcript - Refactored with clean architecture."""

from components.export_handlers import ExportHandler
from components.health_check import require_healthy_backend
from components.metrics_display import (
    get_quality_status,
    render_review_quality_distribution,
    render_transcript_summary_metrics,
)
from services.backend_service import BackendService
from services.state_service import StateService
import streamlit as st
from utils.constants import STATE_KEYS

# Page configuration
st.set_page_config(page_title="Review Results", page_icon="👀", layout="wide")


def initialize_services():
    """Initialize required services."""
    backend = BackendService()
    return backend


def initialize_page_state():
    """Initialize page-specific session state."""
    required_state = {
        STATE_KEYS.TRANSCRIPT_DATA: None,
    }
    StateService.initialize_page_state(required_state)


def render_detailed_review_section(transcript_data: dict) -> None:
    """Render detailed chunk-by-chunk review and full transcript view.

    Logic:
    1. Display tabbed interface for chunks vs full transcript
    2. Show quality assessment for each chunk if available
    3. Provide side-by-side comparison of original vs cleaned text
    """
    st.subheader("🔍 Detailed Review")

    chunks = transcript_data.get("chunks", [])
    if not chunks:
        st.info("No transcript chunks available for review.")
        return

    # Show transcript content in tabs
    tabs = st.tabs(["📋 By Chunks", "📄 Full Transcript"])

    with tabs[0]:  # By Chunks
        st.markdown("**Processing Results by Chunk with Quality Assessment:**")

        cleaned_chunks = transcript_data.get("cleaned_chunks", [])
        review_results = transcript_data.get("review_results", [])

        if cleaned_chunks and review_results:
            # Show chunks with quality scores and side-by-side comparison
            for i, (chunk, clean_result, review) in enumerate(
                zip(chunks, cleaned_chunks, review_results, strict=False)
            ):
                if not clean_result or not review:
                    continue

                # Get quality info
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
                        hours = int(start_time // 3600)
                        minutes = int((start_time % 3600) // 60)
                        secs = start_time % 60
                        timestamp = f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

                        st.markdown(f"**[{timestamp}] {speaker}:** {text}")

    with tabs[1]:  # Full Transcript
        st.markdown("**Complete cleaned transcript:**")

        final_transcript = transcript_data.get("final_transcript", "")
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


def main():
    """Main page logic."""
    # Initialize
    backend = initialize_services()
    initialize_page_state()

    st.title("👀 Review Cleaned Transcript")
    st.markdown(
        "Review your processed transcript with quality assessment and export options."
    )

    # Require healthy backend
    require_healthy_backend(backend)

    # Check if we have processed transcript
    transcript = st.session_state.get("transcript") or st.session_state.get(
        STATE_KEYS.TRANSCRIPT_DATA
    )

    if not transcript:
        st.warning(
            "⚠️ No processed transcript found. Please upload and process a file first."
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "📤 Go to Upload & Process", type="primary", use_container_width=True
            ):
                st.switch_page("pages/1_📤_Upload_Process.py")

        with col2:
            st.info("💡 **Tip**: Process a VTT file first to see review results here.")

        st.stop()

    # Display metrics using our components
    cleaned_chunks = transcript.get("cleaned_chunks", [])
    review_results = transcript.get("review_results", [])

    if cleaned_chunks and review_results:
        # Show quality distribution using component
        render_review_quality_distribution(review_results)
    else:
        # Show basic transcript summary
        render_transcript_summary_metrics(transcript)

    # Export section using component
    original_filename = st.session_state.get("upload_file", {}).get(
        "name", "transcript.vtt"
    )
    ExportHandler.render_export_section(transcript, original_filename, "cleaned")

    # Detailed review section
    render_detailed_review_section(transcript)


if __name__ == "__main__":
    main()
