from time import sleep

from components.error_display import (
    display_error,
    display_validation_errors,
)
from components.metrics_display import render_transcript_summary_metrics
from services.pipeline import run_transcript_pipeline
from services.state_service import StateService
import streamlit as st
from utils.constants import STATE_KEYS
from utils.helpers import format_file_size, validate_file

# Page configuration
st.set_page_config(page_title="Upload & Process", page_icon="📤", layout="wide")


def initialize_page_state():
    """Initialize page-specific session state."""
    required_state = {
        STATE_KEYS.TRANSCRIPT_DATA: None,
        "upload_file": None,
        "processing_complete": False,
    }
    StateService.initialize_page_state(required_state)


def render_file_upload_section():
    """Render file upload interface."""
    st.subheader("📎 Select VTT File")

    uploaded_file = st.file_uploader(
        "Choose a VTT transcript file",
        type=["vtt"],
        help="Upload your meeting transcript file (.vtt format)",
        key="file_uploader",
    )

    if uploaded_file:
        # Validate file
        is_valid, error_message = validate_file(uploaded_file)

        if not is_valid:
            display_validation_errors([error_message])
            return None

        # Show file info
        st.markdown("### 📄 File Information")
        with st.expander("ℹ️ Details", expanded=True):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Filename", uploaded_file.name)
            with col2:
                file_size = len(uploaded_file.getvalue())
                st.metric("Size", format_file_size(file_size))
            with col3:
                st.metric("Type", uploaded_file.type or "text/vtt")

            # Preview content
            with st.expander("🔍 Preview File Content"):
                try:
                    content = uploaded_file.getvalue().decode("utf-8")
                    preview = content[:1000]
                    if len(content) > 1000:
                        preview += "\n\n... (truncated)"
                    st.code(preview, language="text")
                except Exception as e:
                    st.error(f"Could not preview file: {e}")

        return uploaded_file
    else:
        # Show what happens during processing
        st.markdown("### 🔄 Processing Steps")
        st.markdown("1. **📤 Upload**: File loaded into the app")
        st.markdown("2. **🔧 Parse**: VTT content parsed and chunked for AI processing")
        st.markdown("3. **🤖 Clean**: AI agents clean speech-to-text errors")
        st.markdown("4. **📊 Review**: Quality review ensures high accuracy")
        st.markdown("5. **✅ Complete**: Cleaned transcript ready for review")

    return None


def process_file(uploaded_file) -> bool:
    """Process uploaded file with progress tracking."""
    status_ph = st.empty()
    bar_ph = st.progress(0.0)

    def on_progress(pct: float, message: str) -> None:
        bar_ph.progress(pct)
        status_ph.text(f"{int(pct * 100)}% • {message}")

    try:
        content = uploaded_file.getvalue().decode("utf-8")
    except Exception as e:
        display_error("processing_failed", f"Failed to read file: {e}")
        return False

    try:
        result = run_transcript_pipeline(content, on_progress)
    except Exception as e:
        display_error("processing_failed", str(e))
        return False

    st.session_state[STATE_KEYS.TRANSCRIPT_DATA] = result
    st.session_state["processing_complete"] = True

    render_transcript_summary_metrics(result)

    return True


def render_results_section():
    """Render processing results and next steps."""
    transcript_data = st.session_state.get(STATE_KEYS.TRANSCRIPT_DATA)

    if not transcript_data:
        return

    render_transcript_summary_metrics(transcript_data)


def main():
    """Main page logic."""
    # Initialize
    initialize_page_state()

    # File upload section
    uploaded_file = render_file_upload_section()

    if uploaded_file:
        if st.button("🔄 Process VTT File", type="primary", use_container_width=True):
            st.session_state["upload_file"] = {"name": uploaded_file.name}
            success = process_file(uploaded_file)
            if success:
                st.toast("Processing complete! Navigate to the Review page.", icon="✅")
                sleep(3)
                st.rerun()

    # Check if already completed
    st.divider()
    if st.session_state.get("processing_complete"):
        with st.expander("View Processing Results", icon="✅", expanded=True):
            render_results_section()


if __name__ == "__main__":
    main()
