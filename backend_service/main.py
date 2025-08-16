"""
Pragmatic FastAPI backend for Meeting Transcript Cleaner.

Simple, focused architecture that preserves all existing domain logic
while enabling multi-user deployment. No over-engineering - just what's needed.
"""

from datetime import datetime, timedelta
import os
from typing import Any
import uuid

# Configure structured logging
from backend_service.config import configure_structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import structlog

configure_structlog()
logger = structlog.get_logger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    logger.info("Meeting Transcript API starting up")
    
    # Verify OpenAI API key is configured
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not configured - processing will fail")
    else:
        logger.info("OpenAI API key configured successfully")
    
    yield
    
    # Shutdown (if needed)
    logger.info("Meeting Transcript API shutting down")

# FastAPI app setup
app = FastAPI(
    title="Meeting Transcript API",
    description="Backend service for AI-powered meeting transcript processing",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory task store (no Redis overhead for <100 users)
tasks: dict[str, dict[str, Any]] = {}


# Cleanup task results after 1 hour to prevent memory leaks
def cleanup_old_tasks():
    """Remove tasks older than 1 hour."""
    cutoff = datetime.now() - timedelta(hours=1)
    tasks_to_remove = [
        task_id
        for task_id, task in tasks.items()
        if task.get("created_at", datetime.now()) < cutoff
    ]
    for task_id in tasks_to_remove:
        del tasks[task_id]

    if tasks_to_remove:
        logger.info("Cleaned up old tasks", count=len(tasks_to_remove))


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "service": "meeting-transcript-api",
        "tasks_in_memory": len(tasks),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v1/transcript/process")
async def process_transcript(file: UploadFile, background_tasks: BackgroundTasks):
    """
    Upload and process VTT file (combines upload + cleaning in one call).

    Returns task_id for polling progress.
    """
    if not file.filename:
        raise HTTPException(400, "File name is required")
    if not file.filename.endswith(".vtt"):
        raise HTTPException(400, "Only VTT files are supported")

    try:
        content = await file.read()
        content_str = content.decode("utf-8")
    except UnicodeDecodeError as err:
        # Propagate the original decoding error context for better debugging
        raise HTTPException(400, "Invalid VTT file encoding") from err

    task_id = str(uuid.uuid4())

    # Initialize task in store
    tasks[task_id] = {
        "type": "transcript_processing",
        "status": "processing",
        "created_at": datetime.now(),
        "progress": 0.0,
        "message": "Starting VTT processing...",
        "filename": file.filename,
    }

    logger.info(
        "VTT processing task started",
        task_id=task_id,
        filename=file.filename,
        content_size=len(content_str),
    )

    # Process in background using existing TranscriptService
    background_tasks.add_task(run_transcript_processing, task_id, content_str)

    return {
        "task_id": task_id,
        "status": "processing",
        "message": "VTT file received, processing started",
    }


@app.post("/api/v1/intelligence/extract")
async def extract_intelligence(
    data: dict,  # {"transcript_id": "uuid", "detail_level": "comprehensive"}
    background_tasks: BackgroundTasks,
):
    """
    Extract meeting intelligence from processed transcript.

    Requires transcript_id from completed transcript processing.
    """
    transcript_id = data.get("transcript_id")
    detail_level = data.get("detail_level", "comprehensive")

    if not transcript_id:
        raise HTTPException(400, "transcript_id is required")

    # Find the completed transcript
    transcript_task = tasks.get(transcript_id)
    if not transcript_task:
        raise HTTPException(404, "Transcript not found")

    if transcript_task["status"] != "completed":
        raise HTTPException(400, "Transcript processing not completed")

    task_id = str(uuid.uuid4())

    # Initialize intelligence extraction task
    tasks[task_id] = {
        "type": "intelligence_extraction",
        "status": "processing",
        "created_at": datetime.now(),
        "progress": 0.0,
        "message": f"Starting intelligence extraction with {detail_level} detail level...",
        "detail_level": detail_level,
    }

    logger.info(
        "Intelligence extraction task started",
        task_id=task_id,
        transcript_id=transcript_id,
        detail_level=detail_level,
    )

    # Extract intelligence in background
    background_tasks.add_task(
        run_intelligence_extraction, task_id, transcript_task["result"], detail_level
    )

    return {"task_id": task_id, "status": "processing", "detail_level": detail_level}


@app.get("/api/v1/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll task status and get results when completed."""
    # Clean up old tasks before checking
    cleanup_old_tasks()

    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found or expired")

    response = {
        "task_id": task_id,
        "type": task["type"],
        "status": task["status"],
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "created_at": task["created_at"].isoformat(),
    }

    # Include result if completed
    if task["status"] == "completed":
        response["result"] = task.get("result")

    # Include error if failed
    if task["status"] == "failed":
        response["error"] = task.get("error")

    return response


@app.delete("/api/v1/task/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running task (cleanup only - can't stop background processing)."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    # Remove from memory
    del tasks[task_id]

    logger.info("Task cancelled/removed", task_id=task_id)

    return {"message": "Task cancelled"}


# Background task implementations


async def run_transcript_processing(task_id: str, content: str):
    """Background task for VTT processing using existing TranscriptService."""
    try:
        # Import here to avoid startup overhead
        from backend_service.services.transcript_service import TranscriptService

        # Get API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise Exception("OPENAI_API_KEY not configured")

        # Initialize service
        service = TranscriptService(api_key)

        # Progress callback that updates task store
        def update_progress(progress: float, message: str):
            if task_id in tasks:
                tasks[task_id]["progress"] = progress
                tasks[task_id]["message"] = message
                logger.debug("Progress update", task_id=task_id, progress=progress)

        # Process VTT
        tasks[task_id]["message"] = "Parsing VTT file..."
        transcript = service.process_vtt(content)

        tasks[task_id]["progress"] = 0.2
        tasks[task_id]["message"] = (
            f"VTT parsed: {len(transcript['chunks'])} chunks, starting AI cleaning..."
        )

        # Clean transcript with concurrent processing
        cleaned = await service.clean_transcript(
            transcript, progress_callback=update_progress
        )

        # Store result
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 1.0
        tasks[task_id]["message"] = "Transcript processing completed"
        tasks[task_id]["result"] = cleaned

        logger.info(
            "Transcript processing completed",
            task_id=task_id,
            chunks=len(cleaned["chunks"]),
            speakers=len(cleaned["speakers"]),
        )

    except Exception as e:
        logger.error("Transcript processing failed", task_id=task_id, error=str(e))
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["message"] = f"Processing failed: {str(e)}"


async def run_intelligence_extraction(
    task_id: str, transcript_data: dict, detail_level: str
):
    """Background task for intelligence extraction using existing orchestrator."""
    try:
        # Import here to avoid startup overhead
        from backend_service.services.orchestration.intelligence_orchestrator import IntelligenceOrchestrator

        # Initialize orchestrator
        orchestrator = IntelligenceOrchestrator(model="o3-mini")

        # Progress callback
        def update_progress(progress: float, message: str):
            if task_id in tasks:
                tasks[task_id]["progress"] = progress
                tasks[task_id]["message"] = message
                logger.debug(
                    "Intelligence progress", task_id=task_id, progress=progress
                )

        # Extract intelligence
        intelligence = await orchestrator.process_meeting(
            transcript_data["chunks"],
            detail_level=detail_level,
            progress_callback=update_progress,
        )

        # Store result
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 1.0
        tasks[task_id]["message"] = "Intelligence extraction completed"
        tasks[task_id]["result"] = {
            "intelligence": intelligence.model_dump(),  # Convert Pydantic model to dict
            "summary": intelligence.summary,
            "action_items": [item.model_dump() for item in intelligence.action_items],
            "processing_stats": intelligence.processing_stats,
        }

        logger.info(
            "Intelligence extraction completed",
            task_id=task_id,
            action_items=len(intelligence.action_items),
            detail_level=detail_level,
        )

    except Exception as e:
        logger.error("Intelligence extraction failed", task_id=task_id, error=str(e))
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["message"] = f"Intelligence extraction failed: {str(e)}"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
