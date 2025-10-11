"""Meeting Transcript Cleaner - Main Application.

Clean architecture multi-page Streamlit application with:
- Upload & Process: File upload and AI processing
- Review: Quality assessment and export functionality
- Intelligence: Meeting insights and action items
"""

from dotenv import load_dotenv
from services.state_service import StateService
import streamlit as st
from utils.constants import STATE_KEYS, UI_CONFIG

from backend.config import configure_structlog

# Configure page
st.set_page_config(
    page_title=UI_CONFIG.PAGE_TITLE,
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def initialize_application():
    """Initialize minimal application state."""
    # Load environment and configure logging once
    load_dotenv()
    try:
        configure_structlog()
    except Exception:
        pass

    # Initialize minimal application-wide session state
    app_state = {
        STATE_KEYS.TRANSCRIPT_DATA: None,
        STATE_KEYS.INTELLIGENCE_DATA: None,
    }
    StateService.initialize_page_state(app_state)


def render_transcript_summary():
    """Render transcript summary if available."""
    transcript = st.session_state.get(STATE_KEYS.TRANSCRIPT_DATA)

    if not transcript:
        return

    st.success("✅ Transcript processed and ready")

    # Show basic metrics
    chunks = transcript.get("chunks", [])
    speakers = transcript.get("speakers", [])
    duration = transcript.get("duration", 0)
    total_entries = sum(len(chunk.get("entries", [])) for chunk in chunks)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Chunks", len(chunks))
    with col2:
        st.metric("Entries", total_entries)
    with col3:
        st.metric("Speakers", len(speakers))
    with col4:
        st.metric(
            "Duration", f"{duration/60:.1f}m" if duration > 60 else f"{duration:.1f}s"
        )

    # Show participants
    if speakers:
        st.info(f"**Participants:** {', '.join(speakers)}")

    st.divider()


def main():
    """Main application with minimal design."""
    # Initialize application
    initialize_application()

    # Simple header
    st.title("🎙️ Meeting Transcript Cleaner")

    # Show transcript summary if available
    render_transcript_summary()

    # Define all application pages
    pages = [
        st.Page("pages/1_📤_Upload_Process.py", title="Upload & Process", icon="📤"),
        st.Page("pages/2_👀_Review.py", title="Review", icon="👀"),
        st.Page("pages/3_🧠_Intelligence.py", title="Intelligence", icon="🧠"),
    ]

    # Set up navigation
    navigation = st.navigation(pages)
    navigation.run()


if __name__ == "__main__":
    main()
