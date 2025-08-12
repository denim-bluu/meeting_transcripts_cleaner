"""
Upload & Process Page - Unified file upload and AI processing interface.

This page combines the upload and processing workflows into a single seamless experience
with modern UI components and real-time progress updates.
"""

import asyncio
import threading
import time

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
import structlog

from config import Config, configure_structlog
from services.transcript_service import TranscriptService
from utils.ui_components import render_metrics_row

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)

# Ensure we see logs in Streamlit terminal
logger.info("Upload & Process page initialized", streamlit_page=True)


async def process_document_with_status(uploaded_file: UploadedFile) -> None:
    """Handle file upload and processing in single workflow with live updates."""
    try:
        # Initialize service - get API key from config (loads from .env)
        api_key = Config.OPENAI_API_KEY

        if not api_key:
            st.error("❌ OpenAI API key not found. Please set OPENAI_API_KEY in:")
            st.error("- `.env` file in project root")
            st.error("- Environment variable")
            st.info("Create `.env` file with:")
            st.code("OPENAI_API_KEY=sk-your-actual-openai-key-here")
            return

        service = TranscriptService(api_key)

        # Phase 1: Document Processing
        with st.status("Processing document...", expanded=True) as status:
            # Create single status placeholder that updates in place
            status_placeholder = st.empty()

            status_placeholder.write("📖 Reading file content...")
            content = uploaded_file.getvalue().decode("utf-8")

            status_placeholder.write("🔧 Parsing and chunking VTT file...")
            transcript = service.process_vtt(content)

            # Store in session state
            st.session_state.transcript = transcript

            # Display success message
            status_placeholder.success(
                f"✅ Created {len(transcript['chunks'])} chunks from {len(transcript['entries'])} VTT entries"
            )
            status.update(label="VTT processed successfully!", state="complete")

        # Show metrics after processing
        metrics = [
            ("VTT Entries", len(transcript["entries"]), None),
            ("Chunks", len(transcript["chunks"]), None),
            ("Speakers", len(transcript["speakers"]), None),
            ("Duration", f"{transcript['duration']:.1f}s", None),
        ]
        render_metrics_row(metrics)

        # Show speaker list
        speakers = transcript["speakers"]
        if speakers:
            st.markdown(f"**Speakers:** {', '.join(speakers)}")

        # Phase 2: AI Processing
        st.container()
        st.container()

        # Processing state for UI updates
        processing_state = {
            "progress": 0.0,
            "status": "Initializing AI processing...",
            "eta": 0.0,
            "tokens_per_sec": 0,
            "completed": False,
            "error": None,
            "result": None,  # Store the cleaned transcript result
        }

        def update_progress(progress: float, status: str):
            """Callback to update processing progress."""
            logger.info(f"Progress update: {progress:.2%} - {status}")  # Log progress

            processing_state["progress"] = progress
            processing_state["status"] = status

            # Calculate ETA and processing rate
            if progress > 0:
                total_time = time.time() - start_time
                eta = (total_time / progress) * (1 - progress)

                # Calculate chunks per second
                chunks_processed = int(progress * len(transcript["chunks"]))
                chunks_per_sec = chunks_processed / total_time if total_time > 0 else 0
                processing_state["tokens_per_sec"] = (
                    chunks_per_sec  # Reuse field name for display
                )

                processing_state["eta"] = eta

        def run_ai_processing():
            """Run AI processing in background thread with proper async handling."""
            try:
                processing_info = {
                    "chunk_count": len(transcript["chunks"]),
                    "speakers": len(transcript["speakers"]),
                    "vtt_native": True,
                }

                logger.info(
                    "Starting AI processing",
                    phase="ai_processing",
                    processing=processing_info,
                )

                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Run cleaning and review with proper async context
                    cleaned_transcript = loop.run_until_complete(
                        service.clean_transcript(transcript, update_progress)
                    )

                    # Store result in processing_state (will be moved to session_state in main thread)
                    processing_state["result"] = cleaned_transcript

                    processing_state["completed"] = True
                    processing_state["status"] = "AI processing completed!"
                    logger.info(
                        "AI processing completed successfully",
                        phase="ai_processing_complete",
                    )
                finally:
                    loop.close()

            except Exception as e:
                logger.error(
                    "AI processing failed",
                    phase="ai_processing_error",
                    error_info={"error": str(e)},
                    exc_info=True,
                )
                processing_state["error"] = str(e)
                processing_state["status"] = f"Processing failed: {str(e)}"

        # Start processing
        start_time = time.time()
        thread = threading.Thread(target=run_ai_processing)
        thread.start()

        # Real-time UI updates
        with st.status("AI Processing Pipeline", expanded=True) as ai_status:
            progress_bar = st.progress(0)
            status_text = st.empty()

            metrics_cols = st.columns(3)

            # Create metric placeholders once (prevents stacking)
            with metrics_cols[0]:
                progress_placeholder = st.empty()
            with metrics_cols[1]:
                eta_placeholder = st.empty()
            with metrics_cols[2]:
                tokens_placeholder = st.empty()

            while thread.is_alive() or not processing_state["completed"]:
                # Update progress bar
                progress_bar.progress(processing_state["progress"])

                # Update status text
                status_text.write(f"**{processing_state['status']}**")

                # Update metrics using placeholders (prevents multiple lines)
                progress_placeholder.metric(
                    "Progress", f"{processing_state['progress']:.1%}"
                )
                eta_placeholder.metric("ETA", f"{processing_state['eta']:.1f}s")
                # Display processing rate metric
                tokens_placeholder.metric(
                    "Chunks/sec", f"{processing_state['tokens_per_sec']:.1f}"
                )

                # Check for completion or error
                if processing_state["error"]:
                    ai_status.update(label="AI Processing Failed", state="error")
                    st.error(f"❌ Processing failed: {processing_state['error']}")
                    return
                elif processing_state["completed"]:
                    ai_status.update(label="AI Processing Completed!", state="complete")
                    break

                time.sleep(0.1)

        # Wait for thread completion
        thread.join()

        # Store the cleaned transcript result in session state (main thread)
        if processing_state.get("result"):
            st.session_state.cleaned_transcript = processing_state["result"]
            logger.info("Cleaned transcript stored in session state")

        # Set up for Review page
        st.session_state.categories = []

        # Set processing complete flag for navigation
        st.session_state.processing_complete = True
        logger.info(
            "Processing completed - navigation unlocked",
            # Key identifier (flat)
            phase="completion",
        )

        # Show completion metrics using shared component
        st.success("✅ Processing completed successfully!")

        # Show completion metrics using the result from processing_state
        cleaned_transcript = processing_state.get("result", {})
        review_results = cleaned_transcript.get("review_results", [])
        accepted_count = sum(1 for r in review_results if r.get("accept", False))

        completion_metrics = [
            ("Total Chunks", len(cleaned_transcript.get("cleaned_chunks", [])), None),
            ("Accepted", accepted_count, None),
            ("Needs Review", len(review_results) - accepted_count, None),
            (
                "Quality Score",
                f"{sum(r.get('quality_score', 0) for r in review_results) / len(review_results):.2f}"
                if review_results
                else "N/A",
                None,
            ),
        ]
        render_metrics_row(completion_metrics)

        st.balloons()
        st.info(
            "Navigate to the **Review** page to examine results and make any needed adjustments."
        )

        # Trigger rerun to update navigation
        st.rerun()

    except Exception as e:
        logger.error(
            "Document processing failed",
            error=str(e),
            exc_info=True,
            phase="document_processing",
        )
        st.error(f"❌ Processing failed: {str(e)}")


# MAIN PAGE EXECUTION
st.set_page_config(
    page_title="Upload & Process",
    page_icon="📤",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.header("📤 Upload & Process Transcript")

# Help section
with st.expander("ℹ️ VTT-Native Processing Pipeline", expanded=False):
    st.markdown("""
    **Simple VTT Workflow:**
    1. **Upload** your VTT meeting transcript (Zoom, Teams, Google Meet)
    2. **Parse** with token-based chunking (preserves speakers & timing)
    3. **Clean** using AI with minimal context for efficiency
    4. **Review** with quality scoring and acceptance validation
    5. **Export** in VTT, text, or JSON format
    6. **Navigate** to Review page for final adjustments

    **Key Features:**
    - 🎯 **Speaker Preservation**: Maintains who said what throughout
    - 🚀 **Simple & Fast**: Token-based chunking for reliable performance
    - 📊 **Minimal Context**: Previous chunk context for flow awareness
    - 👥 **Speaker Support**: Automatic speaker detection and preservation
    - ⏱️ **Timestamp Support**: Preserves original timing information
    - 🔄 **Multi-format Export**: VTT, text, and JSON export options
    """)

# VTT-only file upload section
uploaded_file = st.file_uploader(
    "Choose a VTT transcript file",
    type=["vtt"],
    help="Upload a VTT meeting transcript from Zoom, Teams, Google Meet, or other meeting platforms",
)

if uploaded_file is not None:
    # Show file info
    st.subheader(f"📄 {uploaded_file.name}")
    st.write(
        f"**Size:** {uploaded_file.size:,} bytes | **Type:** {uploaded_file.type or 'text/plain'}"
    )

    # Process button
    if st.button("🚀 Process Transcript", type="primary", use_container_width=True):
        # Run async processing
        asyncio.run(process_document_with_status(uploaded_file))

# Removed redundant processing overview - details available in expander above

# Show recent transcript if available
if "transcript" in st.session_state and st.session_state.transcript:
    transcript = st.session_state.transcript
    st.subheader("📋 Current Transcript")

    # Display transcript metrics
    current_metrics = [
        ("VTT Entries", len(transcript["entries"]), None),
        ("Chunks", len(transcript["chunks"]), None),
        ("Speakers", len(transcript["speakers"]), None),
        ("Duration", f"{transcript['duration']:.1f}s", None),
    ]
    render_metrics_row(current_metrics)

    # Show speaker list
    if transcript["speakers"]:
        st.markdown(f"**Speakers:** {', '.join(transcript['speakers'])}")

    # Show VTT preview
    with st.expander("📝 Transcript Preview (First 3 Chunks)", expanded=False):
        for i, chunk in enumerate(transcript["chunks"][:3]):
            st.markdown(f"**Chunk {i+1}** ({chunk.token_count} tokens):")
            st.text(chunk.to_transcript_text()[:200] + "...")
