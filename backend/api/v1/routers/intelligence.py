"""Intelligence extraction endpoints."""

from datetime import datetime
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
import structlog

from backend.api.v1.schemas import IntelligenceExtractionRequest, TaskResponse
from backend.config import settings
from backend.tasks.cache import get_task_cache
from backend.tasks.models import TaskEntry, TaskStatus, TaskType

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


async def get_task_or_404(task_id: str) -> TaskEntry:
    """Get task by ID or raise 404."""
    cache = get_task_cache()
    task = await cache.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or expired"
        )
    return task


@router.post("/extract", response_model=TaskResponse)
async def extract_intelligence(
    request: IntelligenceExtractionRequest,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    """Extract meeting intelligence from processed transcript.

    Logic:
    1. Validate transcript exists and is completed
    2. Create new extraction task
    3. Start background extraction
    4. Return task ID for polling

    Expected behavior:
    - Requires completed transcript task
    - Creates new task for extraction
    - Extracts summary, action items, insights
    """
    cache = get_task_cache()

    # Validate transcript exists and is completed
    transcript_task = await get_task_or_404(request.transcript_id)

    if transcript_task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transcript processing not completed. Current status: {transcript_task.status.value}",
        )

    # Create new task (no idempotency)
    task_id = str(uuid.uuid4())

    task = TaskEntry(
        task_id=task_id,
        task_type=TaskType.INTELLIGENCE_EXTRACTION,
        status=TaskStatus.PROCESSING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        progress=0.0,
        message=f"Starting intelligence extraction with {request.detail_level} detail level...",
        metadata={
            "detail_level": request.detail_level.value,
            "transcript_id": request.transcript_id,
            "custom_instructions": request.custom_instructions,
            "models": {
                "insights_model": settings.insights_model,
                "synthesis_model": settings.synthesis_model,
            },
        },
    )

    # Store task
    await cache.store_task(task)

    logger.info(
        "Intelligence extraction task started",
        task_id=task_id,
        transcript_id=request.transcript_id,
        detail_level=request.detail_level.value,
    )

    # Extract in background
    from backend.api.v1.background_tasks import run_intelligence_extraction

    background_tasks.add_task(
        run_intelligence_extraction,
        task_id,
        transcript_task.result,
        request.detail_level.value,
        request.custom_instructions,
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        message=f"Intelligence extraction started with {request.detail_level.value} detail level",
    )
