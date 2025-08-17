"""
Production-ready configuration for Meeting Transcript API.

Supports multiple environments (development, staging, production) with
appropriate defaults and validation.
"""

import os
from enum import Enum
from typing import Any, Dict, Union

import structlog
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, rely on system environment variables
    pass


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
    default_model: str = "o3-mini"
    cleaning_model: str = ""
    review_model: str = ""
    openai_api_key: str = ""
    
    # Task Cache Configuration
    task_ttl_hours: int = 1
    cleanup_interval_minutes: int = 10
    
    # Processing Configuration
    max_concurrent_tasks: int = 10
    rate_limit_per_minute: int = 50
    max_file_size_mb: int = 100
    
    # CORS Configuration
    cors_origins: str = "*"
    
    # Logging Configuration
    log_level: str = "INFO"
    log_json: bool = False
    
    # Health Check Configuration
    health_check_timeout: int = 10
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables
    )
        
    @field_validator("cleaning_model")
    @classmethod
    def set_cleaning_model_default(cls, v: str) -> str:
        """Set cleaning model to default_model if not specified."""
        if not v:
            return "o3-mini"
        return v
    
    @field_validator("review_model") 
    @classmethod
    def set_review_model_default(cls, v: str) -> str:
        """Set review model to default_model if not specified."""
        if not v:
            return "o3-mini"
        return v
    
    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string to list."""
        if isinstance(self.cors_origins, str):
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return [self.cors_origins]
    
    @model_validator(mode='after')
    def set_environment_specific_defaults(self):
        """Set environment-specific defaults."""
        # Disable debug in production
        if self.environment == Environment.PRODUCTION:
            self.debug = False
        
        # Only allow reload in development
        if self.environment != Environment.DEVELOPMENT:
            self.reload = False
            
        # Set model defaults if not specified
        if not self.cleaning_model:
            self.cleaning_model = self.default_model
        if not self.review_model:
            self.review_model = self.default_model
            
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
    
    def get_cors_config(self) -> Dict[str, Any]:
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
