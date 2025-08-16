"""
Pragmatic FastAPI backend for Meeting Transcript Cleaner.

Production-ready API with formal Pydantic schemas, comprehensive validation,
and automatic OpenAPI documentation. Built for scalable SPCS deployment.
"""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

# Configure structured logging first
from backend_service.config import configure_structlog

configure_structlog()
logger = structlog.get_logger(__name__)

# Import API routes and repositories
from backend_service.api.v1.endpoints import router as api_v1_router
from backend_service.repositories.factory import initialize_repositories


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    logger.info("Meeting Transcript API starting up", version="1.0.0")

    # Initialize repositories
    initialize_repositories()
    logger.info("Repositories initialized successfully")

    # Verify OpenAI API key is configured
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not configured - processing will fail")
    else:
        logger.info("OpenAI API key configured successfully")

    # Log API configuration
    logger.info("API routes registered", endpoints=len(app.routes))

    yield

    # Shutdown
    logger.info("Meeting Transcript API shutting down")


# FastAPI app setup with enhanced metadata
app = FastAPI(
    title="Meeting Transcript API",
    description="""
    **AI-Powered Meeting Transcript Processing Service**

    This API provides enterprise-grade meeting transcript processing with:

    * **VTT File Processing**: Upload and clean transcript files using AI
    * **Intelligence Extraction**: Extract summaries, action items, and insights
    * **Asynchronous Processing**: Background task execution with progress tracking
    * **Formal Validation**: Comprehensive Pydantic schema validation
    * **Production Ready**: Built for Snowpark Container Services deployment

    ## Authentication

    Currently using API key authentication. SPCS deployments will use
    automatic OAuth token authentication via `/snowflake/session/token`.

    ## Rate Limits

    - File uploads: 100MB max size
    - Concurrent tasks: 10 per instance
    - Request rate: 1000 requests/minute per client

    ## Support

    For issues or questions, see the project documentation.
    """,
    version="1.0.0",
    lifespan=lifespan,
    # API documentation configuration
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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
        {"url": "http://localhost:8000", "description": "Development server"},
        {
            "url": "https://your-spcs-endpoint.snowflakecomputing.com",
            "description": "Production SPCS deployment",
        },
    ],
)

# CORS middleware for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Local Streamlit development
        "https://*.snowflakecomputing.com",  # SPCS production domains
        "*",  # TODO: Restrict for production
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Processing-Time"],
)

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
        "service": "Meeting Transcript API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# Application startup
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Only for development
        log_config=None,  # Use our structured logging
    )
