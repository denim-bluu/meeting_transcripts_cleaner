"""
Production-ready configuration for Meeting Transcript API.

Supports multiple environments (development, staging, production) with
appropriate defaults and validation.
"""

import os
from enum import Enum
from typing import Any, Dict

import structlog
from pydantic import Field, validator
from pydantic_settings import BaseSettings

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
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        env="ENVIRONMENT",
        description="Application environment"
    )
    
    # API Configuration
    api_title: str = Field(
        default="Meeting Transcript API",
        env="API_TITLE",
        description="API title for OpenAPI docs"
    )
    api_version: str = Field(
        default="1.0.0",
        env="API_VERSION",
        description="API version"
    )
    debug: bool = Field(
        default=True,
        env="DEBUG",
        description="Enable debug mode"
    )
    
    # Server Configuration
    host: str = Field(
        default="0.0.0.0",
        env="HOST",
        description="Server host"
    )
    port: int = Field(
        default=8000,
        env="PORT",
        ge=1,
        le=65535,
        description="Server port"
    )
    reload: bool = Field(
        default=False,
        env="RELOAD",
        description="Enable auto-reload (development only)"
    )
    
    # AI Model Configuration
    default_model: str = Field(
        default="o3-mini",
        env="DEFAULT_MODEL",
        description="Default AI model for processing"
    )
    cleaning_model: str = Field(
        default="",
        env="CLEANING_MODEL",
        description="Model for transcript cleaning (defaults to default_model)"
    )
    review_model: str = Field(
        default="",
        env="REVIEW_MODEL", 
        description="Model for transcript review (defaults to default_model)"
    )
    openai_api_key: str = Field(
        default="",
        env="OPENAI_API_KEY",
        description="OpenAI API key for AI processing"
    )
    
    # Task Cache Configuration
    task_ttl_hours: int = Field(
        default=1,
        env="TASK_TTL_HOURS",
        ge=1,
        le=24,
        description="Task time-to-live in hours"
    )
    cleanup_interval_minutes: int = Field(
        default=10,
        env="CLEANUP_INTERVAL_MINUTES",
        ge=1,
        le=60,
        description="Cache cleanup interval in minutes"
    )
    
    # Processing Configuration
    max_concurrent_tasks: int = Field(
        default=10,
        env="MAX_CONCURRENT_TASKS",
        ge=1,
        le=50,
        description="Maximum concurrent AI processing tasks"
    )
    rate_limit_per_minute: int = Field(
        default=50,
        env="RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=300,
        description="API rate limit per minute"
    )
    max_file_size_mb: int = Field(
        default=100,
        env="MAX_FILE_SIZE_MB",
        ge=1,
        le=500,
        description="Maximum file upload size in MB"
    )
    
    # CORS Configuration
    cors_origins: list[str] = Field(
        default=["*"],
        env="CORS_ORIGINS",
        description="Allowed CORS origins (comma-separated)"
    )
    
    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        env="LOG_LEVEL",
        description="Logging level"
    )
    log_json: bool = Field(
        default=False,
        env="LOG_JSON",
        description="Enable JSON logging for production"
    )
    
    # Health Check Configuration
    health_check_timeout: int = Field(
        default=10,
        env="HEALTH_CHECK_TIMEOUT",
        ge=1,
        le=60,
        description="Health check timeout in seconds"
    )
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables
        
    @validator("cleaning_model", pre=True)
    def set_cleaning_model_default(cls, v: str, values: Dict[str, Any]) -> str:
        """Set cleaning model to default_model if not specified."""
        if not v:
            return values.get("default_model", "o3-mini")
        return v
    
    @validator("review_model", pre=True) 
    def set_review_model_default(cls, v: str, values: Dict[str, Any]) -> str:
        """Set review model to default_model if not specified."""
        if not v:
            return values.get("default_model", "o3-mini")
        return v
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @validator("debug")
    def set_debug_from_environment(cls, v: bool, values: Dict[str, Any]) -> bool:
        """Automatically disable debug in production."""
        env = values.get("environment", Environment.DEVELOPMENT)
        if env == Environment.PRODUCTION:
            return False
        return v
    
    @validator("reload")
    def set_reload_from_environment(cls, v: bool, values: Dict[str, Any]) -> bool:
        """Only allow reload in development."""
        env = values.get("environment", Environment.DEVELOPMENT)
        if env != Environment.DEVELOPMENT:
            return False
        return v
    
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
        if self.is_production():
            # Restrictive CORS for production
            return {
                "allow_origins": [origin for origin in self.cors_origins if origin != "*"],
                "allow_credentials": True,
                "allow_methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["*"],
                "expose_headers": ["X-Request-ID", "X-Processing-Time"],
            }
        else:
            # Permissive CORS for development
            return {
                "allow_origins": self.cors_origins,
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
                "expose_headers": ["X-Request-ID", "X-Processing-Time"],
            }


# Global settings instance
settings = Settings()


# Legacy Config class for backward compatibility
class Config:
    """Legacy configuration class for backward compatibility."""
    
    DEFAULT_MODEL = settings.default_model
    CLEANING_MODEL = settings.cleaning_model
    REVIEW_MODEL = settings.review_model
    OPENAI_API_KEY = settings.openai_api_key


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
