import time

from api_client import api_client
from config import configure_structlog
import streamlit as st
import structlog
from utils.ui_components import render_metrics_row

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)

logger.info("Upload & Process page initialized", streamlit_page=True, mode="api_client")


def check_backend_health():
    """Check if backend is available and show status."""
    is_healthy, health_data = api_client.health_check()

    if not is_healthy:
        st.error("❌ Backend service is not available")
        st.error(f"Error: {health_data.get('error', 'Unknown error')}")
        st.info("Make sure the FastAPI backend is running at the configured URL")
        st.code(f"Backend URL: {api_client.base_url}")
        return False

    # Show backend status
    st.success(f"✅ Backend connected: {health_data.get('service', 'Unknown')}")
    if "tasks_in_memory" in health_data:
        st.info(f"Active tasks: {health_data['tasks_in_memory']}")

    return True


def process_vtt_file(uploaded_file):
    """Process VTT file using the backend API with real-time progress."""

    # Upload and start processing
    file_content = uploaded_file.getvalue()
    filename = uploaded_file.name

    logger.info(
        "Starting VTT processing", filename=filename, size_bytes=len(file_content)
    )

    # Upload file to backend
    with st.status("Uploading file to backend...", expanded=True) as upload_status:
        # Each upload gets a unique task_id (no idempotency)
        # This ensures proper multi-user support
        success, task_id_or_error, message = api_client.upload_and_process_transcript(
            file_content, filename
        )

        if not success:
            upload_status.update(label="❌ Upload failed", state="error")
            st.error(task_id_or_error)
            return

        task_id = task_id_or_error

        # Persist task_id in URL so we can resume after refresh
        q = st.query_params
        q["task"] = task_id
        st.query_params = q

        upload_status.update(label="✅ Upload successful", state="complete")
        st.info(f"Task ID: {task_id}")

    # Poll for completion with progress updates
    with st.status("Processing VTT file...", expanded=True) as process_status:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        # Metrics for live updates
        metrics_cols = st.columns(4)
        with metrics_cols[0]:
            progress_metric = st.empty()
        with metrics_cols[1]:
            status_metric = st.empty()
        with metrics_cols[2]:
            time_metric = st.empty()
        with metrics_cols[3]:
            task_metric = st.empty()

        start_time = time.time()

        def update_progress(progress: float, message: str):
            """Update the UI with current progress."""
            progress_bar.progress(progress)
            status_text.text(message)

            # Try to extract ETA seconds from backend status string e.g. "... • ETA: 12.3s"
            eta_seconds = None
            marker = "ETA:"
            if marker in message:
                try:
                    after = message.split(marker, 1)[1].strip()
                    num = ""
                    for ch in after:
                        if ch.isdigit() or ch == ".":
                            num += ch
                        else:
                            break
                    if num:
                        eta_seconds = float(num)
                except Exception:
                    eta_seconds = None

            # Update metrics
            progress_metric.metric("Progress", f"{progress*100:.1f}%")
            status_metric.metric("Status", "Processing", delta=message)

            elapsed = time.time() - start_time
            if eta_seconds is not None:
                time_metric.metric(
                    "Elapsed", f"{elapsed:.1f}s", delta=f"ETA {eta_seconds:.1f}s"
                )
            else:
                time_metric.metric("Elapsed", f"{elapsed:.1f}s")
            task_metric.metric("Task", task_id[:8])

        # Poll until complete
        success, final_data = api_client.poll_until_complete(
            task_id,
            progress_callback=update_progress,
            poll_interval=2.0,
            timeout=300.0,  # 5 minutes max
        )

        if not success:
            process_status.update(label="❌ Processing failed", state="error")
            error = final_data.get("error", "Unknown error")
            st.error(f"Processing failed: {error}")
            return

        # Success!
        process_status.update(label="✅ Processing completed", state="complete")
        result = final_data.get("result")

        if result:
            # Store in session state for other pages
            st.session_state.transcript = result
            st.session_state.transcript_task_id = (
                task_id  # Store task_id for intelligence extraction
            )
            st.session_state.processing_complete = True

            # Show success metrics
            transcript = result
            metrics = [
                ("VTT Entries", len(transcript.get("entries", [])), None),
                ("Chunks", len(transcript.get("chunks", [])), None),
                ("Speakers", len(transcript.get("speakers", [])), None),
                ("Duration", f"{transcript.get('duration', 0):.1f}s", None),
            ]
            render_metrics_row(metrics)

            # Show speakers
            speakers = transcript.get("speakers", [])
            if speakers:
                st.markdown(f"**Speakers:** {', '.join(speakers)}")

            # Success message with next steps
            st.success("🎉 VTT processing completed successfully!")


def main():
    """Main function for the Upload & Process page."""
    st.set_page_config(page_title="Upload & Process", page_icon="📤", layout="wide")

    st.title("📤 Upload & Process VTT Files")
    st.markdown(
        "Upload your VTT meeting transcript for AI-powered cleaning and processing."
    )

    # Check backend health first
    if not check_backend_health():
        st.stop()

    # Resume ongoing task from URL if present
    q = st.query_params
    task_in_url = q.get("task")
    if task_in_url and not st.session_state.get("transcript"):
        # Verify the task type before resuming to avoid attaching wrong task
        success, status_data = api_client.get_task_status(task_in_url)
        if not success:
            st.warning("Could not look up task from URL. It may have expired.")
        else:
            if status_data.get("type") != "transcript_processing":
                st.info("Task in URL is not a transcript-processing task. Ignoring.")
                # Optionally clear the param to avoid repeated attempts
                q.pop("task", None)
                st.query_params = q
            else:
                with st.status(
                    "Resuming ongoing processing task...", expanded=True
                ) as resume_status:
                    progress_text = st.empty()

                    def _resume_progress(p, m):
                        progress_text.text(f"{p*100:.1f}% - {m}")

                    ok, data = api_client.poll_until_complete(
                        task_in_url,
                        progress_callback=_resume_progress,
                        poll_interval=2.0,
                        timeout=300.0,
                    )
                    if ok:
                        result = data.get("result")
                        if result:
                            st.session_state.transcript = result
                            st.session_state.transcript_task_id = task_in_url
                            st.session_state.processing_complete = True
                            resume_status.update(
                                label="✅ Task resumed and completed", state="complete"
                            )
                            # Clear task param now that it's done
                            q.pop("task", None)
                            st.query_params = q

    # Show current status if we have a transcript
    if hasattr(st.session_state, "transcript") and st.session_state.transcript:
        st.info(
            "✅ VTT transcript already processed and ready for review/intelligence extraction"
        )

        st.markdown("---")
        st.markdown("**Or upload a new file below:**")

    # File upload section
    st.subheader("📎 File Upload")

    uploaded_file = st.file_uploader(
        "Choose a VTT file",
        type=["vtt"],
        help="Upload a VTT (WebVTT) transcript file from your meeting recording",
        accept_multiple_files=False,
    )

    if uploaded_file is not None:
        # Show file info
        st.markdown("### 📄 File Information")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Filename", uploaded_file.name)
        with col2:
            file_size = len(uploaded_file.getvalue())
            st.metric("Size", f"{file_size:,} bytes")
        with col3:
            st.metric("Type", uploaded_file.type or "text/vtt")

        # Preview content
        with st.expander("🔍 Preview File Content"):
            try:
                content = uploaded_file.getvalue().decode("utf-8")
                # Show first 1000 characters
                preview = content[:1000]
                if len(content) > 1000:
                    preview += "\n\n... (truncated)"
                st.code(preview, language="text")
            except Exception as e:
                st.error(f"Could not preview file: {e}")

        # Process button
        st.markdown("### 🚀 Start Processing")

        if st.button("🔄 Process VTT File", type="primary", use_container_width=True):
            process_vtt_file(uploaded_file)

    else:
        # Show what we can do
        st.markdown("### What happens when you upload?")
        st.markdown("1. **📤 Upload**: File is securely sent to our processing backend")
        st.markdown(
            "2. **🔧 Parse**: VTT content is parsed and chunked for AI processing"
        )
        st.markdown(
            "3. **🤖 Clean**: AI agents clean speech-to-text errors while preserving meaning"
        )
        st.markdown("4. **📊 Review**: Quality review ensures 95%+ accuracy")
        st.markdown(
            "5. **✅ Complete**: Cleaned transcript ready for review and intelligence extraction"
        )

        st.info(
            "💡 **Tip**: VTT files are generated by most meeting recording platforms (Zoom, Teams, Google Meet)"
        )


if __name__ == "__main__":
    main()
