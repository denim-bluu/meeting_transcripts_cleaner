"""
Multi-page Streamlit application for Meeting Transcript Cleaner.

This is the main entry point that sets up st.navigation between pages:
- Upload & Process: Unified workflow for file upload and AI processing
- Review: Progressive review interface with export functionality
"""

from typing import Any

from dotenv import load_dotenv
import streamlit as st

from config import configure_structlog

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

    # Define the 3-page structure
    all_pages = [
        st.Page("pages/1_📤_Upload_Process.py", title="Upload & Process", icon="📤"),
        st.Page("pages/2_👀_Review.py", title="Review", icon="👀"),
        st.Page("pages/3_⚙️_Settings.py", title="Settings", icon="⚙️"),
    ]

    # Determine page availability based on processing state
    available_pages = [all_pages[0]]  # Upload & Process always available

    # Settings page always available
    available_pages.append(all_pages[1])

    # Review page always available but will show appropriate messaging if no data
    available_pages.append(all_pages[2])

    # Set up navigation
    pg = st.navigation(available_pages)
    pg.run()


if __name__ == "__main__":
    main()
