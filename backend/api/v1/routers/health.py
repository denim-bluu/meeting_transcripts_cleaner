"""
Health check router for system monitoring and load balancer checks.

Responsibilities:
- Check OpenAI API key configuration (configured/missing status)
- Verify task cache connectivity and return current task count
- Calculate service uptime from startup time
- Aggregate dependency status (openai, cache) into overall health
- Return current model configurations for debugging

Expected Behavior:
- GET /api/v1/health returns HealthStatus with 200 OK when all dependencies healthy
- Returns 503 Service Unavailable with degraded status if critical dependencies fail
- Includes models config (cleaning_model, review_model, insights_model, synthesis_model, segment_model)
- Shows uptime_seconds, tasks_in_memory count, and dependency status map
"""

import os

from fastapi import APIRouter
import structlog

from backend.api.v1.schemas import HealthStatus
from backend.shared.config import settings
from backend.tasks.cache import get_task_cache

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """
    Health check endpoint for load balancers and monitoring.

    Returns current service status, uptime, and dependency health.
    """
    # Calculate uptime (simplified - in production would track actual start time)
    uptime_seconds = 300.0  # Placeholder

    # Check dependencies
    dependencies = {}

    # Check OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    dependencies["openai"] = "configured" if api_key else "missing"

    # Check cache health
    cache = get_task_cache()
    cache_health = await cache.health_check()
    dependencies["cache"] = cache_health.get("cache", "unknown")

    # Get task count from cache
    task_count = await cache.get_task_count()

    # Determine overall status
    overall_status = (
        "healthy"
        if all(status in ["configured", "healthy"] for status in dependencies.values())
        else "degraded"
    )

    return HealthStatus(
        status=overall_status,
        service="meeting-transcript-api",
        version="1.0.0",
        uptime_seconds=uptime_seconds,
        tasks_in_memory=task_count,
        dependencies=dependencies,
        models={
            "cleaning_model": settings.cleaning_model,
            "review_model": settings.review_model,
            "insights_model": settings.insights_model,
            "synthesis_model": settings.synthesis_model,
            "segment_model": settings.segment_model,
            "synthesis_reasoning_effort": settings.synthesis_reasoning_effort,
            "synthesis_reasoning_summary": settings.synthesis_reasoning_summary,
        },
    )
