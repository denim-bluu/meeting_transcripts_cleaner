"""
Multi-page Streamlit application for Meeting Transcript Cleaner.

This is the main entry point that sets up st.navigation between pages:
- Upload & Process: Unified workflow for file upload and AI processing
- Review: Progressive review interface with export functionality
"""

from typing import Any

from dotenv import load_dotenv
import streamlit as st

from frontend.config import configure_structlog

# Configure structured logging for the entire application
configure_structlog()

# Load environment variables
load_dotenv()

# Configure page
st.set_page_config(
    page_title="Meeting Transcript Cleaner",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state() -> None:
    """Initialize all session state variables in one place."""
    defaults: dict[str, Any] = {
        "document": None,
        "processing_complete": False,
        "categories": [],
        "user_decisions": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# Initialize session state
init_session_state()


def main() -> None:
    """Main application with modern 2-page navigation."""

    # App header using native Streamlit components
    st.title("🎙️ Meeting Transcript Cleaner")

    # Show processing summary if transcript is loaded
    if "transcript" in st.session_state and st.session_state.transcript:
        from utils.ui_components import render_metrics_row

        transcript = st.session_state.transcript
        st.success("✅ VTT transcript loaded - ready for processing")

        # Show transcript metrics
        homepage_metrics = [
            ("VTT Entries", len(transcript["entries"]), None),
            ("Chunks", len(transcript["chunks"]), None),
            ("Speakers", len(transcript["speakers"]), None),
            ("Duration", f"{transcript.get('duration', 0) / 60:.1f}m", None),
        ]
        render_metrics_row(homepage_metrics)

        # Show speakers
        if transcript["speakers"]:
            st.info(f"**Meeting participants:** {', '.join(transcript['speakers'])}")

    # Define the 2-page structure (simplified architecture)
    all_pages = [
        st.Page("pages/1_📤_Upload_Process.py", title="Upload & Process", icon="📤"),
        st.Page("pages/2_👀_Review.py", title="Review", icon="👀"),
        st.Page("pages/3_🧠_Intelligence.py", title="Intelligence", icon="🧠"),
    ]

    # All pages are always available (Review page shows appropriate messaging if no data)
    available_pages = all_pages

    # Set up navigation
    pg = st.navigation(available_pages)
    pg.run()


if __name__ == "__main__":
    main()
