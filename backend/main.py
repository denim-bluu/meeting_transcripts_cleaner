"""
Pragmatic FastAPI backend for Meeting Transcript Cleaner.

Production-ready API with formal Pydantic schemas, comprehensive validation,
and automatic OpenAPI documentation. Built for scalable SPCS deployment.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

# Import API routes and cache
from backend.api.v1.endpoints import router as api_v1_router

# Configure structured logging first
from backend.config import configure_structlog, settings
from backend.services.transcript.task_cache import initialize_cache

configure_structlog()
logger = structlog.get_logger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    logger.info(
        "Meeting Transcript API starting up",
        version=settings.api_version,
        environment=settings.get_environment_display(),
        debug=settings.debug
    )

    # Initialize task cache
    initialize_cache(
        ttl_hours=settings.task_ttl_hours,
        cleanup_interval_minutes=settings.cleanup_interval_minutes
    )
    logger.info(
        "Task cache initialized successfully",
        ttl_hours=settings.task_ttl_hours,
        cleanup_interval_minutes=settings.cleanup_interval_minutes
    )

    # Verify OpenAI API key is configured
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not configured - processing will fail")
    else:
        logger.info("OpenAI API key configured successfully")

    # Log API configuration
    logger.info("API routes registered", endpoints=len(app.routes))

    yield

    # Shutdown
    logger.info("Meeting Transcript API shutting down")


# FastAPI app setup with environment-aware configuration
app = FastAPI(
    title=settings.api_title,
    description=f"""
    **AI-Powered Meeting Transcript Processing Service**

    This API provides enterprise-grade meeting transcript processing with:

    * **VTT File Processing**: Upload and clean transcript files using AI
    * **Intelligence Extraction**: Extract summaries, action items, and insights
    * **Asynchronous Processing**: Background task execution with progress tracking
    * **Formal Validation**: Comprehensive Pydantic schema validation
    * **Production Ready**: Built for Snowpark Container Services deployment

    ## Environment

    Currently running in **{settings.get_environment_display()}** mode.

    ## Authentication

    Currently using API key authentication. SPCS deployments will use
    automatic OAuth token authentication via `/snowflake/session/token`.

    ## Rate Limits

    - File uploads: {settings.max_file_size_mb}MB max size
    - Concurrent tasks: {settings.max_concurrent_tasks} per instance
    - Request rate: {settings.rate_limit_per_minute} requests/minute per client

    ## Support

    For issues or questions, see the project documentation.
    """,
    version=settings.api_version,
    debug=settings.debug,
    lifespan=lifespan,
    # API documentation configuration
    docs_url="/docs" if not settings.is_production() else None,  # Disable docs in production
    redoc_url="/redoc" if not settings.is_production() else None,
    openapi_url="/openapi.json" if not settings.is_production() else None,
    # Add contact and license info for production
    contact={
        "name": "Meeting Transcript API Support",
        "url": "https://github.com/your-org/minutes_cleaner",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    # Add server info for different environments
    servers=[
        {"url": f"http://{settings.host}:{settings.port}", "description": f"{settings.get_environment_display()} server"},
    ] if not settings.is_production() else [
        {"url": "https://your-spcs-endpoint.snowflakecomputing.com", "description": "Production SPCS deployment"},
    ],
)

# CORS middleware with environment-aware configuration
cors_config = settings.get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)

# Include API routes
app.include_router(api_v1_router, tags=["API v1"])


# Root endpoint for basic health check
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint providing basic API information.

    Use `/api/v1/health` for detailed health checks.
    """
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "environment": settings.get_environment_display(),
        "status": "operational",
        "docs": "/docs" if not settings.is_production() else "disabled",
        "health": "/api/v1/health",
    }


# Application startup
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_config=None,  # Use our structured logging
    )
