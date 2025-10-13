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


def main():
    """Main application with minimal design."""
    # Initialize application
    initialize_application()

    # Simple header
    st.title("🎙️ Meeting Transcript Cleaner")


    # Define all application pages
    pages = [
        st.Page("pages/1_📤_Upload_Process.py", title="Upload & Process", icon="📤"),
        st.Page("pages/2_👀_Review.py", title="Review", icon="👀"),
        st.Page("pages/3_🧠_Intelligence.py", title="Intelligence", icon="🧠"),
    ]

    # Set up navigation
    navigation = st.navigation(pages, position="top")
    navigation.run()


if __name__ == "__main__":
    main()
