"""
Pragmatic FastAPI backend for Meeting Transcript Cleaner.

Production-ready API with formal Pydantic schemas, comprehensive validation,
and automatic OpenAPI documentation. Built for scalable SPCS deployment.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from backend.api.v1.routers.debug import router as debug_router

# Import API domain routers
from backend.api.v1.routers.health import router as health_router
from backend.api.v1.routers.intelligence import router as intelligence_router
from backend.api.v1.routers.tasks import router as tasks_router
from backend.api.v1.routers.transcript import router as transcript_router

# Configure structured logging first
from backend.shared.config import configure_structlog, settings
from backend.tasks.cache import initialize_cache

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
        debug=settings.debug,
    )

    # Initialize task cache first (required by InMemoryTaskRepository)
    initialize_cache(
        ttl_hours=settings.task_ttl_hours,
        cleanup_interval_minutes=settings.cleanup_interval_minutes,
    )
    logger.info(
        "Task cache initialized successfully",
        ttl_hours=settings.task_ttl_hours,
        cleanup_interval_minutes=settings.cleanup_interval_minutes,
    )

    # Verify OpenAI API key is configured
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not configured - processing will fail")
    else:
        logger.info("OpenAI API key configured successfully")

        # Initialize application services with shared dependencies
        from backend.integrations.factories import create_application_services

        try:
            transcript_processor, intelligence_processor = create_application_services(
                settings.openai_api_key
            )

            # Store services in app state for dependency injection
            app.state.transcript_processor = transcript_processor
            app.state.intelligence_processor = intelligence_processor

            logger.info(
                "Application services initialized successfully",
                services=["transcript_processor", "intelligence_processor"],
                shared_dependencies=True,
            )
        except Exception as e:
            logger.error("Failed to initialize application services", error=str(e))
            # Services will be created on-demand as fallback

    # Log API configuration
    logger.info("API routes registered", endpoints=len(app.routes))
    logger.info(
        "LLM model configuration",
        cleaning_model=settings.cleaning_model,
        review_model=settings.review_model,
        insights_model=settings.insights_model,
        synthesis_model=settings.synthesis_model,
        segment_model=settings.segment_model,
        synthesis_reasoning_effort=settings.synthesis_reasoning_effort,
        synthesis_reasoning_summary=settings.synthesis_reasoning_summary,
    )

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
    docs_url="/docs"
    if not settings.is_production()
    else None,  # Disable docs in production
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
        {
            "url": f"http://{settings.host}:{settings.port}",
            "description": f"{settings.get_environment_display()} server",
        },
    ]
    if not settings.is_production()
    else [
        {
            "url": "https://your-spcs-endpoint.snowflakecomputing.com",
            "description": "Production SPCS deployment",
        },
    ],
)

# CORS middleware with environment-aware configuration
cors_config = settings.get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)

# Include all domain routers
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(transcript_router, prefix="/api/v1", tags=["transcript"])
app.include_router(intelligence_router, prefix="/api/v1", tags=["intelligence"])
app.include_router(tasks_router, prefix="/api/v1", tags=["tasks"])
app.include_router(debug_router, prefix="/api/v1", tags=["debug"])


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


# Application startup with optimized production configuration
if __name__ == "__main__":
    import uvicorn

    # Determine optimal configuration based on environment
    is_production = settings.is_production()

    if is_production:
        # Production configuration with multi-worker setup
        uvicorn.run(
            "main:app",
            host="0.0.0.0",  # Listen on all interfaces in container
            port=8000,
            workers=4,  # 4 worker processes for multi-user concurrency
            loop="uvloop",  # High-performance event loop
            limit_concurrency=100,  # Max 100 concurrent connections
            limit_max_requests=1000,  # Restart workers after 1000 requests (prevent leaks)
            access_log=False,  # Disable access logs for performance
            log_config=None,  # Use our structured logging
            timeout_keep_alive=65,  # Keep connections alive longer
            timeout_graceful_shutdown=30,  # Graceful shutdown timeout
        )
    else:
        # Development configuration
        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_config=None,  # Use our structured logging
            access_log=True,  # Enable access logs in development
        )
