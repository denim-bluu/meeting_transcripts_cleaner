"""
Production-ready configuration for Meeting Transcript API.

Supports multiple environments (development, staging, production) with
appropriate defaults and validation.
"""

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog

# Resolve .env relative to project root (minutes_cleaner/.env)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)


class Environment(str, Enum):
    """Application environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Application settings with environment-specific defaults.

    Uses Pydantic for validation and type safety.
    Environment variables override defaults.
    """

    # Environment
    environment: Environment = Environment.DEVELOPMENT

    # API Configuration
    api_title: str = "Meeting Transcript API"
    api_version: str = "1.0.0"
    debug: bool = True

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    # AI Model Configuration
    default_model: str = "gpt-5"
    cleaning_model: str = ""
    review_model: str = ""
    insights_model: str = ""
    synthesis_model: str = ""
    synthesis_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    synthesis_reasoning_summary: Literal["detailed", "concise"] = "detailed"
    synthesis_timeout_seconds: int = 300
    openai_api_key: str = ""

    # Task Cache Configuration
    task_ttl_hours: int = 1
    cleanup_interval_minutes: int = 10

    # Processing Configuration
    max_concurrent_tasks: int = 10
    rate_limit_per_minute: int = 50
    max_file_size_mb: int = 100
    synthesis_context_token_limit: int = 50000

    # CORS Configuration
    cors_origins: str = "*"

    # Logging Configuration
    log_level: str = "INFO"
    log_json: bool = False
    suppress_access_log_prefixes: str = "/api/v1/task/"
    suppress_polling_access_logs: bool = True

    # Health Check Configuration
    health_check_timeout: int = 10

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string to list."""
        if isinstance(self.cors_origins, str):
            return [
                origin.strip()
                for origin in self.cors_origins.split(",")
                if origin.strip()
            ]
        return [self.cors_origins]

    def get_suppress_access_log_prefixes_list(self) -> list[str]:
        """Parse suppressed access log path prefixes from comma-separated string to list."""
        value = self.suppress_access_log_prefixes
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return [value]

    @model_validator(mode="after")
    def set_environment_specific_defaults(self):
        """Set environment-specific defaults."""
        # Disable debug in production
        if self.environment == Environment.PRODUCTION:
            self.debug = False

        # Only allow reload in development
        if self.environment != Environment.DEVELOPMENT:
            self.reload = False

        # Use env values if provided; otherwise fall back to "o3-mini"
        def _fallback(v: str) -> str:
            return v or "o3-mini"

        self.cleaning_model = _fallback(self.cleaning_model)
        self.review_model = _fallback(self.review_model)
        self.insights_model = _fallback(self.insights_model)
        self.synthesis_model = _fallback(self.synthesis_model)
        self.segment_model = _fallback(self.segment_model)

        return self

    def get_environment_display(self) -> str:
        """Get human-readable environment name."""
        return self.environment.value.title()

    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == Environment.DEVELOPMENT

    def get_cors_config(self) -> dict[str, Any]:
        """Get CORS configuration."""
        origins_list = self.get_cors_origins_list()

        if self.is_production():
            # Restrictive CORS for production
            return {
                "allow_origins": [origin for origin in origins_list if origin != "*"],
                "allow_credentials": True,
                "allow_methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["*"],
                "expose_headers": ["X-Request-ID", "X-Processing-Time"],
            }
        else:
            # Permissive CORS for development
            return {
                "allow_origins": origins_list,
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
                "expose_headers": ["X-Request-ID", "X-Processing-Time"],
            }


# Global settings instance
settings = Settings()
print(settings)


def configure_structlog() -> None:
    """Initialize structlog with clean, readable logging."""
    import logging
    import sys

    # SIMPLE FIX: Just force INFO level and stdout
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        force=True,
        format="%(message)s",  # Only show the structured message, not the Python logging prefix
    )
    logging.root.setLevel(logging.INFO)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),  # Clean timestamp
            structlog.stdlib.add_log_level,  # Add log level
            structlog.dev.ConsoleRenderer(
                colors=True,
                pad_event=20,  # Pad event names for alignment
                level_styles={  # Custom level colors
                    "debug": "\033[36m",  # cyan
                    "info": "\033[32m",  # green
                    "warning": "\033[33m",  # yellow
                    "error": "\033[31m",  # red
                },
            ),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Suppress noisy uvicorn access logs for polling endpoints (e.g., task status)
    try:
        if settings.suppress_polling_access_logs:
            suppressed_prefixes = settings.get_suppress_access_log_prefixes_list()

            class _AccessPathFilter(logging.Filter):
                def filter(self, record: logging.LogRecord) -> bool:
                    try:
                        msg = record.getMessage()
                    except Exception:
                        msg = str(record.msg)
                    # Suppress GET/POST logs that start with configured prefixes
                    return not any(
                        f"GET {prefix}" in msg or f"POST {prefix}" in msg
                        for prefix in suppressed_prefixes
                    )

            logging.getLogger("uvicorn.access").addFilter(_AccessPathFilter())
    except Exception:
        # Never fail logging setup if filter cannot be applied
        pass
