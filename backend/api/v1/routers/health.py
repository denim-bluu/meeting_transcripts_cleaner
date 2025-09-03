"""Health check endpoints."""

import os

from fastapi import APIRouter

from backend.api.v1.schemas import HealthStatus
from backend.config import settings
from backend.tasks.cache import get_task_cache

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Health check endpoint for load balancers and monitoring."""
    # Check OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    dependencies = {
        "openai": "configured" if api_key else "missing"
    }

    # Check cache health
    cache = get_task_cache()
    cache_health = await cache.health_check()
    dependencies["cache"] = cache_health.get("cache", "unknown")

    # Get task count
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
        uptime_seconds=300.0,  # Placeholder
        tasks_in_memory=task_count,
        dependencies=dependencies,
        models={
            "cleaning_model": settings.cleaning_model,
            "review_model": settings.review_model,
            "insights_model": settings.insights_model,
            "synthesis_model": settings.synthesis_model,
        },
    )
