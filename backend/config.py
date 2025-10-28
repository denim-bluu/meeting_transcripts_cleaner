"""Minimal settings + logging for Streamlit prototype."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env file from backend directory
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BACKEND_DIR / ".env")


class Settings(BaseSettings):
    """Essential settings for domain services and logging."""

    # Environment + logging
    log_level: str = "INFO"

    # Model configuration
    cleaning_model: str = "o3-mini"
    review_model: str = "o3-mini"
    chunk_model: str = "o3-mini"
    aggregation_model: str = "o3-mini"

    # Concurrency + rate limits
    transcript_max_concurrency: int = 20
    transcript_rate_limit_per_minute: int = 80
    intelligence_max_concurrency: int = 8


settings = Settings()


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
