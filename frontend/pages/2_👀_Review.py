"""
Review Page - API-based interface for reviewing cleaned transcripts.

This page shows processing results from the backend API and allows export 
in multiple formats through the microservices architecture.
"""

import json
from datetime import datetime

import streamlit as st
import structlog

from api_client import api_client
from config import configure_structlog
from utils.ui_components import render_metrics_row

# Configure logging
configure_structlog()
logger = structlog.get_logger(__name__)

logger.info("Review page initialized", streamlit_page=True, mode="api_client")


def generate_export_data(transcript_data: dict, format_type: str) -> str:
    """Generate export data in the specified format."""
    
    if format_type == "vtt":
        # Generate VTT format
        vtt_content = "WEBVTT\n\n"
        
        chunks = transcript_data.get("chunks", [])
        for chunk in chunks:
            entries = chunk.get("entries", [])
            for entry in entries:
                start_time = entry.get("start_time", 0)
                end_time = entry.get("end_time", 0)
                speaker = entry.get("speaker", "Speaker")
                text = entry.get("text", "")
                
                # Format timestamps
                start_formatted = format_timestamp(start_time)
                end_formatted = format_timestamp(end_time)
                
                vtt_content += f"{start_formatted} --> {end_formatted}\n"
                vtt_content += f"{speaker}: {text}\n\n"
        
        return vtt_content
        
    elif format_type == "txt":
        # Generate plain text format
        txt_content = "# Meeting Transcript\n\n"
        txt_content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        chunks = transcript_data.get("chunks", [])
        for chunk in chunks:
            entries = chunk.get("entries", [])
            for entry in entries:
                speaker = entry.get("speaker", "Speaker")
                text = entry.get("text", "")
                txt_content += f"{speaker}: {text}\n"
        
        return txt_content
        
    elif format_type == "json":
        # Generate JSON format
        export_data = {
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "source": "Meeting Transcript Cleaner",
                "speakers": transcript_data.get("speakers", []),
                "duration": transcript_data.get("duration", 0),
                "total_chunks": len(transcript_data.get("chunks", []))
            },
            "transcript": transcript_data
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
    st.markdown("Review your processed transcript and export in multiple formats.")

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

    # Display transcript information
    st.subheader("📊 Transcript Overview")

    # Show basic metrics
    chunks = transcript.get("chunks", [])
    speakers = transcript.get("speakers", [])
    duration = transcript.get("duration", 0)
    
    # Calculate total entries
    total_entries = sum(len(chunk.get("entries", [])) for chunk in chunks)

    metrics = [
        ("Total Chunks", len(chunks), None),
        ("Total Entries", total_entries, None),
        ("Speakers", len(speakers), None),
        ("Duration", f"{duration:.1f}s", f"{duration/60:.1f}m" if duration > 60 else None),
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
                help="Download as WebVTT format for video players",
            )

    with col2:
        if st.button("📝 Export as Text", use_container_width=True):
            txt_content = generate_export_data(transcript, "txt")
            st.download_button(
                label="💾 Download Text",
                data=txt_content,
                file_name=f"cleaned_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                help="Download as plain text format",
            )

    with col3:
        if st.button("🔧 Export as JSON", use_container_width=True):
            json_content = generate_export_data(transcript, "json")
            st.download_button(
                label="💾 Download JSON",
                data=json_content,
                file_name=f"cleaned_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                help="Download as structured JSON data",
            )

    # Review detailed results
    st.subheader("🔍 Transcript Details")

    if chunks:
        # Show transcript content in tabs
        tabs = st.tabs(["📋 By Chunks", "📄 Full Text", "👥 By Speaker"])

        with tabs[0]:  # By Chunks
            st.markdown("**Transcript organized by processing chunks:**")

            for i, chunk in enumerate(chunks):
                entries = chunk.get("entries", [])
                if not entries:
                    continue
                    
                # Calculate chunk duration and speaker info
                start_time = min(entry.get("start_time", 0) for entry in entries)
                end_time = max(entry.get("end_time", 0) for entry in entries)
                chunk_duration = end_time - start_time
                chunk_speakers = list(set(entry.get("speaker", "Unknown") for entry in entries))
                
                with st.expander(
                    f"Chunk {i + 1} - {len(entries)} entries, {chunk_duration:.1f}s, Speakers: {', '.join(chunk_speakers)}"
                ):
                    for entry in entries:
                        start_time = entry.get("start_time", 0)
                        speaker = entry.get("speaker", "Unknown")
                        text = entry.get("text", "")
                        
                        # Format timestamp
                        timestamp = format_timestamp(start_time)
                        
                        st.markdown(f"**[{timestamp}] {speaker}:** {text}")

        with tabs[1]:  # Full Text
            st.markdown("**Complete transcript as continuous text:**")
            
            full_text = ""
            for chunk in chunks:
                entries = chunk.get("entries", [])
                for entry in entries:
                    speaker = entry.get("speaker", "Unknown")
                    text = entry.get("text", "")
                    full_text += f"{speaker}: {text}\n"
            
            st.text_area(
                "Full Transcript",
                value=full_text,
                height=400,
                help="Complete transcript text ready for copying",
            )

        with tabs[2]:  # By Speaker
            st.markdown("**Transcript organized by speaker:**")
            
            # Group entries by speaker
            speaker_entries = {}
            for chunk in chunks:
                entries = chunk.get("entries", [])
                for entry in entries:
                    speaker = entry.get("speaker", "Unknown")
                    if speaker not in speaker_entries:
                        speaker_entries[speaker] = []
                    speaker_entries[speaker].append(entry)
            
            for speaker, entries in speaker_entries.items():
                with st.expander(f"👤 {speaker} ({len(entries)} statements)"):
                    for entry in entries:
                        start_time = entry.get("start_time", 0)
                        text = entry.get("text", "")
                        timestamp = format_timestamp(start_time)
                        st.markdown(f"**[{timestamp}]** {text}")

    else:
        st.info("No transcript chunks available for review.")

    # Action section
    st.markdown("---")
    st.subheader("🧠 Next Steps")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🧠 Extract Intelligence", type="primary", use_container_width=True):
            st.switch_page("pages/3_🧠_Intelligence.py")
    
    with col2:
        if st.button("📤 Upload New File", use_container_width=True):
            st.switch_page("pages/1_📤_Upload_Process.py")

    st.markdown(
        "*Transcript processed through our microservices backend. Ready for intelligence extraction.*"
    )


if __name__ == "__main__":
    main()