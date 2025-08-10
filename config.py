"""
Configuration management for the Meeting Transcript Cleaner.

This module handles YAML configuration files and environment variable overrides
for the dual-agent system. Secrets are kept in .env files.
"""

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource
import structlog


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


def get_openai_config() -> OpenAIConfig:
    """Get OpenAI config section."""
    return get_settings().get_openai_config()


def get_agents_config() -> AgentConfig:
    """Get agents config section."""
    return get_settings().get_agents_config()


def get_processing_config() -> ProcessingConfig:
    """Get processing config section."""
    return get_settings().get_processing_config()


def get_confidence_thresholds() -> ConfidenceThresholds:
    """Get confidence thresholds config section."""
    return get_settings().get_confidence_thresholds()


def reset_config() -> None:
    """Reset config cache - useful for testing."""
    global _settings_instance
    _settings_instance = None


class Settings(BaseSettings):
    """Application settings with automatic environment variable loading."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        extra='ignore',
        case_sensitive=False,
    )

    # OpenAI settings
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="o3-mini-2025-01-31", description="Default OpenAI model")
    openai_max_tokens: int = Field(
        default=4000, gt=0, description="Maximum tokens per request"
    )
    openai_timeout_seconds: int = Field(
        default=30, gt=0, description="Request timeout in seconds"
    )
    openai_max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")

    # Agent settings
    agents_cleaning_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature for cleaning agent (lower = more focused)",
    )
    agents_review_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for review agent (0 = deterministic)",
    )
    agents_cleaning_model: str = Field(
        default="o3-mini-2025-01-31", description="Model to use for cleaning agent"
    )
    agents_review_model: str = Field(
        default="o3-mini-2025-01-31", description="Model to use for review agent"
    )
    agents_max_concurrent_requests: int = Field(
        default=5, ge=1, le=20, description="Maximum concurrent API requests"
    )
    agents_rate_limit_requests_per_minute: int = Field(
        default=50, ge=1, description="Rate limit for API requests per minute"
    )

    # Processing settings
    processing_max_section_tokens: int = Field(
        default=500, gt=0, le=8000, description="Maximum tokens per document segment"
    )
    processing_token_overlap: int = Field(
        default=50, ge=0, description="Token overlap between segments"
    )
    processing_min_segment_tokens: int = Field(
        default=50, gt=0, description="Minimum tokens per segment"
    )
    processing_preserve_sentence_boundaries: bool = Field(
        default=True,
        description="Whether to preserve sentence boundaries when segmenting",
    )

    # Confidence thresholds
    confidence_thresholds_auto_accept_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Threshold for auto-accepting segments (>95%)",
    )
    confidence_thresholds_quick_review_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Threshold for quick review (85-95%)"
    )
    confidence_thresholds_detailed_review_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Threshold for detailed review (70-85%)",
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
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file="config.yaml"),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("openai_api_key")
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

    @field_validator("processing_token_overlap")
    @classmethod
    def validate_overlap(cls, v: int, info) -> int:
        """Ensure overlap is reasonable compared to max_section_tokens."""
        if "processing_max_section_tokens" in info.data:
            max_tokens = info.data["processing_max_section_tokens"]
            if v >= max_tokens / 2:
                raise ValueError(
                    "token_overlap should be less than half of max_section_tokens"
                )
        return v

    @field_validator("confidence_thresholds_quick_review_threshold")
    @classmethod
    def validate_quick_review(cls, v: float, info) -> float:
        """Ensure quick review threshold is below auto accept."""
        if (
            "confidence_thresholds_auto_accept_threshold" in info.data
            and v >= info.data["confidence_thresholds_auto_accept_threshold"]
        ):
            raise ValueError(
                "quick_review_threshold must be less than auto_accept_threshold"
            )
        return v

    @field_validator("confidence_thresholds_detailed_review_threshold")
    @classmethod
    def validate_detailed_review(cls, v: float, info) -> float:
        """Ensure detailed review threshold is below quick review."""
        if (
            "confidence_thresholds_quick_review_threshold" in info.data
            and v >= info.data["confidence_thresholds_quick_review_threshold"]
        ):
            raise ValueError(
                "detailed_review_threshold must be less than quick_review_threshold"
            )
        return v

    def get_openai_config(self) -> "OpenAIConfig":
        """Get OpenAI configuration."""
        return OpenAIConfig(
            api_key=self.openai_api_key,
            model=self.openai_model,
            max_tokens=self.openai_max_tokens,
            timeout_seconds=self.openai_timeout_seconds,
            max_retries=self.openai_max_retries,
        )

    def get_agents_config(self) -> "AgentConfig":
        """Get agents configuration."""
        return AgentConfig(
            cleaning_temperature=self.agents_cleaning_temperature,
            review_temperature=self.agents_review_temperature,
            cleaning_model=self.agents_cleaning_model,
            review_model=self.agents_review_model,
            max_concurrent_requests=self.agents_max_concurrent_requests,
            rate_limit_requests_per_minute=self.agents_rate_limit_requests_per_minute,
        )

    def get_processing_config(self) -> "ProcessingConfig":
        """Get processing configuration."""
        return ProcessingConfig(
            max_section_tokens=self.processing_max_section_tokens,
            token_overlap=self.processing_token_overlap,
            min_segment_tokens=self.processing_min_segment_tokens,
            preserve_sentence_boundaries=self.processing_preserve_sentence_boundaries,
        )

    def get_confidence_thresholds(self) -> "ConfidenceThresholds":
        """Get confidence thresholds configuration."""
        return ConfidenceThresholds(
            auto_accept_threshold=self.confidence_thresholds_auto_accept_threshold,
            quick_review_threshold=self.confidence_thresholds_quick_review_threshold,
            detailed_review_threshold=self.confidence_thresholds_detailed_review_threshold,
        )


# Global settings instance
_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Get application settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


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
