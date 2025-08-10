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

from config import configure_structlog
from services.transcript_service import TranscriptService
from utils.ui_components import render_document_preview, render_metrics_row

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)


async def process_document_with_status(uploaded_file: UploadedFile) -> None:
    """Handle file upload and processing in single workflow with live updates."""
    try:
        # Initialize service (cached)
        @st.cache_resource
        def get_transcript_service() -> TranscriptService:
            """Get cached TranscriptService instance."""
            return TranscriptService()

        service = get_transcript_service()

        # Phase 1: Document Processing
        with st.status("Processing document...", expanded=True) as status:
            # Create single status placeholder that updates in place
            status_placeholder = st.empty()

            status_placeholder.write("📖 Reading file content...")
            content = uploaded_file.getvalue().decode("utf-8")

            status_placeholder.write("🔧 Parsing and segmenting document...")
            document = service.process_document(
                filename=uploaded_file.name,
                content=content,
                file_size=uploaded_file.size,
                content_type=uploaded_file.type,
            )

            # Store in session state
            st.session_state.document = document
            status_placeholder.success(
                f"✅ Created {len(document.segments)} segments ({document.total_tokens:,} tokens)"
            )
            status.update(label="Document processed successfully!", state="complete")

        # Show metrics after processing using shared component
        metrics = [
            ("Segments", len(document.segments), None),
            ("Total Tokens", f"{document.total_tokens:,}", None),
            ("File Size", f"{uploaded_file.size:,} bytes", None),
            ("Type", uploaded_file.type or "text/plain", None),
        ]
        render_metrics_row(metrics)

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
        }

        def update_progress(progress: float, status: str):
            """Callback to update processing progress."""
            processing_state["progress"] = progress
            processing_state["status"] = status

            # Calculate ETA and tokens/sec
            if progress > 0:
                total_time = time.time() - start_time
                eta = (total_time / progress) * (1 - progress)
                tokens_processed = int(progress * document.total_tokens)
                tokens_per_sec = tokens_processed / total_time if total_time > 0 else 0

                processing_state["eta"] = eta
                processing_state["tokens_per_sec"] = tokens_per_sec

        def run_ai_processing():
            """Run AI processing in background thread."""
            try:
                logger.info(
                    "Starting AI processing",
                    # Key identifier (flat)
                    phase="ai_processing",
                    # Processing context (grouped)
                    processing={"segment_count": len(document.segments)},
                )
                asyncio.run(
                    service.process_transcript(
                        document=document, progress_callback=update_progress
                    )
                )
                processing_state["completed"] = True
                processing_state["status"] = "AI processing completed!"
                logger.info(
                    "AI processing completed successfully",
                    # Key identifier (flat)
                    phase="ai_processing_complete",
                )
            except Exception as e:
                logger.error(
                    "AI processing failed",
                    # Key identifier (flat)
                    phase="ai_processing_error",
                    # Error details (grouped)
                    error_info={"error": str(e)},
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
                tokens_placeholder.metric(
                    "Tokens/sec", f"{processing_state['tokens_per_sec']:.0f}"
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

        # Extract categories for Review page
        if hasattr(document, "segment_categories") and document.segment_categories:
            st.session_state.categories = list(document.segment_categories.values())
            logger.info(
                "Extracted categories",
                # Key identifier (flat)
                phase="categorization_complete",
                # Results (grouped)
                results={"category_count": len(st.session_state.categories)},
            )
        else:
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

        completion_metrics = [
            (
                "Auto Accept",
                document.processing_status.auto_accept_count
                if document.processing_status
                else 0,
                None,
            ),
            (
                "Quick Review",
                document.processing_status.quick_review_count
                if document.processing_status
                else 0,
                None,
            ),
            (
                "Detailed Review",
                document.processing_status.detailed_review_count
                if document.processing_status
                else 0,
                None,
            ),
            (
                "AI Flagged",
                document.processing_status.ai_flagged_count
                if document.processing_status
                else 0,
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
with st.expander("ℹ️ How it works", expanded=False):
    st.markdown("""
    **Unified Workflow:**
    1. **Upload** your meeting transcript (TXT or VTT format)
    2. **Parse** document into optimized segments
    3. **Clean** segments with AI (parallel processing)
    4. **Review** cleaned content for quality (parallel processing)
    5. **Categorize** segments for efficient review
    6. **Navigate** to Review page for final adjustments

    **Performance Features:**
    - 🚀 **Parallel Processing**: 5-10x faster than sequential
    - 📊 **Real-time Progress**: Live ETA and tokens/sec metrics
    - 🎯 **Smart Categorization**: Focus only on segments that need attention
    - 🔄 **VTT Support**: Preserves speaker boundaries automatically
    """)

# File upload section
uploaded_file = st.file_uploader(
    "Choose a transcript file",
    type=["txt", "vtt"],
    help="Upload a meeting transcript in TXT or VTT format for AI processing",
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

# Show processing overview
st.subheader("🔬 Processing Pipeline Overview")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    **Phase 1: Document Parsing**
    - Content extraction and validation
    - Smart segmentation (500 tokens/segment)
    - Sentence boundary preservation
    - VTT speaker detection
    """)

with col2:
    st.markdown("""
    **Phase 2: AI Processing**
    - Parallel cleaning (CleaningAgent)
    - Parallel review (ReviewAgent)
    - Confidence categorization
    - Progressive review workflow
    """)

# Show recent document if available
if "document" in st.session_state and st.session_state.document:
    document = st.session_state.document
    st.subheader("📋 Current Document")

    current_metrics = [
        ("Segments", len(document.segments), None),
        ("Total Tokens", f"{document.total_tokens:,}", None),
        (
            "Status",
            (
                document.processing_status.status.value
                if document.processing_status and document.processing_status.status
                else "Processed"
            ),
            None,
        ),
    ]
    render_metrics_row(current_metrics)

    # Show segment preview using shared component
    with st.expander("📝 Segment Preview (First 3)", expanded=False):
        render_document_preview(document.segments, max_segments=3)
