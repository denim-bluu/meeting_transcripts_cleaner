"""
Configuration management for the Meeting Transcript Cleaner.

This module handles YAML configuration files and environment variable overrides
for the dual-agent system. Secrets are kept in .env files.
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog

load_dotenv()


class OpenAIConfig(BaseSettings):
    """OpenAI API configuration."""

    api_key: str = Field(default="", description="OpenAI API key")
    model: str = Field(default="o3-mini", description="Default OpenAI model")
    max_tokens: int = Field(
        default=4000, gt=0, description="Maximum tokens per request"
    )
    timeout_seconds: int = Field(
        default=30, gt=0, description="Request timeout in seconds"
    )
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate OpenAI API key format."""
        # Allow empty API key for testing
        if not v:
            return v
        if not v.startswith("sk-") and not v.startswith("test-"):
            raise ValueError(
                'OpenAI API key must start with "sk-" or "test-" for testing'
            )
        if v.startswith("sk-") and len(v) < 20:
            raise ValueError("OpenAI API key appears to be too short")
        return v


class AgentConfig(BaseSettings):
    """Configuration for AI agents."""

    cleaning_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature for cleaning agent (lower = more focused)",
    )
    review_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for review agent (0 = deterministic)",
    )
    cleaning_model: str = Field(
        default="o3-mini", description="Model to use for cleaning agent"
    )
    review_model: str = Field(
        default="o3-mini", description="Model to use for review agent"
    )
    max_concurrent_requests: int = Field(
        default=5, ge=1, le=20, description="Maximum concurrent API requests"
    )
    rate_limit_requests_per_minute: int = Field(
        default=50, ge=1, description="Rate limit for API requests per minute"
    )


class ProcessingConfig(BaseSettings):
    """Configuration for document processing."""

    max_section_tokens: int = Field(
        default=500, gt=0, le=8000, description="Maximum tokens per document segment"
    )
    token_overlap: int = Field(
        default=50, ge=0, description="Token overlap between segments"
    )
    min_segment_tokens: int = Field(
        default=50, gt=0, description="Minimum tokens per segment"
    )
    preserve_sentence_boundaries: bool = Field(
        default=True,
        description="Whether to preserve sentence boundaries when segmenting",
    )

    @field_validator("token_overlap")
    @classmethod
    def validate_overlap(cls, v: int, info) -> int:
        """Ensure overlap is reasonable compared to max_section_tokens."""
        if "max_section_tokens" in info.data:
            max_tokens = info.data["max_section_tokens"]
            if v >= max_tokens / 2:
                raise ValueError(
                    "token_overlap should be less than half of max_section_tokens"
                )
        return v


class ConfidenceThresholds(BaseSettings):
    """Confidence thresholds for progressive review categorization."""

    auto_accept_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Threshold for auto-accepting segments (>95%)",
    )
    quick_review_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Threshold for quick review (85-95%)"
    )
    detailed_review_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Threshold for detailed review (70-85%)",
    )

    @field_validator("quick_review_threshold")
    @classmethod
    def validate_quick_review(cls, v: float, info) -> float:
        """Ensure quick review threshold is below auto accept."""
        if (
            "auto_accept_threshold" in info.data
            and v >= info.data["auto_accept_threshold"]
        ):
            raise ValueError(
                "quick_review_threshold must be less than auto_accept_threshold"
            )
        return v

    @field_validator("detailed_review_threshold")
    @classmethod
    def validate_detailed_review(cls, v: float, info) -> float:
        """Ensure detailed review threshold is below quick review."""
        if (
            "quick_review_threshold" in info.data
            and v >= info.data["quick_review_threshold"]
        ):
            raise ValueError(
                "detailed_review_threshold must be less than quick_review_threshold"
            )
        return v


class AppConfig(BaseSettings):
    """Complete application configuration loaded from YAML + environment variables."""

    # Core configurations
    openai: OpenAIConfig
    agents: AgentConfig
    processing: ProcessingConfig
    confidence_thresholds: ConfidenceThresholds

    # Application metadata
    app: dict = Field(
        default={
            "name": "Meeting Transcript Cleaner",
            "version": "0.1.0",
            "debug_mode": False,
        }
    )

    # Paths
    paths: dict = Field(
        default={
            "upload_directory": "uploads",
            "temp_directory": "temp",
            "log_directory": "logs",
        }
    )

    # Development settings
    development: dict = Field(
        default={
            "use_mock_responses": False,
            "test_mode": False,
            "test_data_path": "tests/fixtures",
        }
    )

    # Performance settings
    performance: dict = Field(
        default={
            "enable_metrics": True,
            "metrics_export_interval": 60,
            "enable_timing_logs": False,
        }
    )

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow extra fields from environment
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Customize settings sources to load YAML first, then env vars."""
        from pydantic_settings.sources import YamlConfigSettingsSource

        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file="config.yaml"),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    def model_post_init(self, __context) -> None:
        """Create necessary directories after initialization."""
        paths = self.paths
        for directory_key in ["upload_directory", "temp_directory", "log_directory"]:
            directory = Path(paths[directory_key])
            directory.mkdir(exist_ok=True)


@lru_cache
def get_config() -> AppConfig:
    """
    Get application configuration from YAML file with environment variable overrides.

    This function is cached to avoid repeated file parsing.
    """
    return AppConfig()


# Simplified config access - single global instance
_config_instance: AppConfig | None = None


def get_openai_config() -> OpenAIConfig:
    """Get OpenAI config section."""
    global _config_instance
    if _config_instance is None:
        _config_instance = get_config()
    return _config_instance.openai


def get_agents_config() -> AgentConfig:
    """Get agents config section."""
    global _config_instance
    if _config_instance is None:
        _config_instance = get_config()
    return _config_instance.agents


def get_processing_config() -> ProcessingConfig:
    """Get processing config section."""
    global _config_instance
    if _config_instance is None:
        _config_instance = get_config()
    return _config_instance.processing


def get_confidence_thresholds() -> ConfidenceThresholds:
    """Get confidence thresholds config section."""
    global _config_instance
    if _config_instance is None:
        _config_instance = get_config()
    return _config_instance.confidence_thresholds


# For testing override
def reset_config():
    """Reset config cache - useful for testing."""
    global _config_instance
    _config_instance = None


def configure_structlog() -> None:
    """Initialize structlog with complete JSON output including level and logger name."""
    import sys

    class NamedWriteLogger:
        """Write logger that preserves name."""
        def __init__(self, file, name):
            self.file = file
            self.name = name

        def msg(self, message):
            print(message, file=self.file)

        def debug(self, message):
            print(message, file=self.file)

        def info(self, message):
            print(message, file=self.file)

        def warning(self, message):
            print(message, file=self.file)

        def error(self, message):
            print(message, file=self.file)

        def critical(self, message):
            print(message, file=self.file)

    class NamedWriteLoggerFactory:
        """Factory that creates named write loggers."""
        def __init__(self, file=sys.stdout):
            self.file = file

        def __call__(self, name=None):
            return NamedWriteLogger(self.file, name or "unknown")

    # Human-readable structlog configuration (like in the documentation example)
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,              # Add logger name
            structlog.stdlib.add_log_level,                # Add log level
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),  # Human readable timestamp
            structlog.processors.CallsiteParameterAdder([  # Add source location details
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]),
            structlog.dev.ConsoleRenderer()                # Human-readable console output
        ],
        logger_factory=NamedWriteLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
        cache_logger_on_first_use=True,
    )
