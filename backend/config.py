"""Minimal configuration for Meeting Transcript API."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env file
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

class Settings(BaseSettings):
    """Essential settings only."""

    # Environment
    environment: str = "development"

    # Essential API settings
    openai_api_key: str = ""

    # Task management
    task_ttl_hours: int = 1
    cleanup_interval_minutes: int = 10
    max_concurrent_tasks: int = 10
    rate_limit_per_minute: int = 50

    # Model configuration
    cleaning_model: str = "o3-mini"
    review_model: str = "o3-mini"
    insights_model: str = "o3-mini"
    synthesis_model: str = "o3-mini"

    # Logging
    log_level: str = "INFO"

    def is_production(self) -> bool:
        return self.environment == "production"

    def get_environment_display(self) -> str:
        return self.environment.title()

    def get_cors_config(self) -> dict:
        """Simple CORS config."""
        if self.is_production():
            return {
                "allow_origins": ["https://your-domain.com"],
                "allow_credentials": True,
                "allow_methods": ["GET", "POST", "DELETE"],
                "allow_headers": ["*"],
            }
        else:
            return {
                "allow_origins": ["*"],
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
            }

settings = Settings()

# Hardcoded constants
api_title = "Meeting Transcript API"
api_version = "1.0.0"
max_file_size_mb = 100
default_host = "0.0.0.0"
default_port = 8000
debug = not settings.is_production()
reload = settings.environment == "development"

def configure_structlog() -> None:
    """Simple logging setup."""
    import logging
    import sys

    import structlog

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        stream=sys.stdout,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
