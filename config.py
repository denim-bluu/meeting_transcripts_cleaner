"""
Simple configuration for VTT transcript processing.

This module provides basic settings for the simplified VTT processing pipeline.
"""

import os
from pathlib import Path

import structlog

# Load .env file if it exists
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # dotenv not available, rely on system environment variables
    pass


class Config:
    """Simple configuration for VTT processing."""

    # AI Agent settings
    DEFAULT_MODEL = "o3-mini"
    CLEANING_MODEL = os.getenv("CLEANING_MODEL", DEFAULT_MODEL)
    REVIEW_MODEL = os.getenv("REVIEW_MODEL", DEFAULT_MODEL)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def configure_structlog() -> None:
    """Initialize structlog with clean, readable logging."""
    import logging
    import sys
    
    # SIMPLE FIX: Just force INFO level and stdout 
    logging.basicConfig(
        level=logging.INFO, 
        stream=sys.stdout, 
        force=True,
        format="%(message)s"  # Only show the structured message, not the Python logging prefix
    )
    logging.root.setLevel(logging.INFO)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),  # Clean timestamp
            structlog.stdlib.add_log_level,                   # Add log level
            structlog.dev.ConsoleRenderer(
                colors=True,
                pad_event=20,  # Pad event names for alignment
                level_styles={  # Custom level colors
                    "debug": "\033[36m",     # cyan
                    "info": "\033[32m",      # green  
                    "warning": "\033[33m",   # yellow
                    "error": "\033[31m",     # red
                }
            )
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


