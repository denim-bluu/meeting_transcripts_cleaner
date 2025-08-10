"""
Configuration management utilities for the Meeting Transcript Cleaner.

This module provides functions to merge session-based configuration overrides
with the base configuration, validation helpers, cost estimation, and preset
configurations for common use cases.
"""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
import structlog

load_dotenv()

logger = structlog.get_logger(__name__)
try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    # Handle case where streamlit is not available
    STREAMLIT_AVAILABLE = False

    class MockSessionState:
        """Mock session state for non-Streamlit contexts."""

        def __init__(self) -> None:
            self._state: dict[str, Any] = {}

        def get(self, key: str, default: Any = None) -> Any:
            return self._state.get(key, default)

        def __setitem__(self, key: str, value: Any) -> None:
            self._state[key] = value

        def __getattr__(self, key: str) -> Any:
            return self._state.get(key)

        def __setattr__(self, key: str, value: Any) -> None:
            if key.startswith("_"):
                # Allow setting private attributes normally
                super().__setattr__(key, value)
            else:
                # Store public attributes in the state dict
                if not hasattr(self, "_state"):
                    super().__setattr__("_state", {})
                self._state[key] = value

        def __contains__(self, key: str) -> bool:
            return key in self._state

    # Create a mock streamlit module for testing
    class MockStreamlit:
        def __init__(self) -> None:
            self.session_state = MockSessionState()

    st = MockStreamlit()

from config import (
    AgentConfig,
    ConfidenceThresholds,
    ProcessingConfig,
    get_settings,
)


class QualityPreset(Enum):
    """Quality preset options for different use cases."""

    FAST = "Fast"
    BALANCED = "Balanced"
    HIGH_QUALITY = "High Quality"


@dataclass
class PresetConfig:
    """Configuration settings for a quality preset."""

    # Agent settings
    cleaning_temperature: float
    review_temperature: float
    cleaning_model: str
    review_model: str

    # Processing settings
    max_section_tokens: int
    token_overlap: int

    # Confidence thresholds
    auto_accept_threshold: float
    quick_review_threshold: float
    detailed_review_threshold: float

    # Metadata
    description: str
    estimated_cost_multiplier: float


# Preset configurations optimized for different use cases
QUALITY_PRESETS: dict[QualityPreset, PresetConfig] = {
    QualityPreset.FAST: PresetConfig(
        cleaning_temperature=0.3,
        review_temperature=0.1,
        cleaning_model="o3-mini-2025-01-31",
        review_model="o3-mini-2025-01-31",
        max_section_tokens=800,
        token_overlap=75,
        auto_accept_threshold=0.90,
        quick_review_threshold=0.80,
        detailed_review_threshold=0.65,
        description="Optimized for speed with acceptable quality. Good for initial drafts.",
        estimated_cost_multiplier=0.7,
    ),
    QualityPreset.BALANCED: PresetConfig(
        cleaning_temperature=0.2,
        review_temperature=0.0,
        cleaning_model="o3-mini-2025-01-31",
        review_model="o3-mini-2025-01-31",
        max_section_tokens=500,
        token_overlap=50,
        auto_accept_threshold=0.95,
        quick_review_threshold=0.85,
        detailed_review_threshold=0.70,
        description="Balanced approach with good quality and reasonable processing time.",
        estimated_cost_multiplier=1.0,
    ),
    QualityPreset.HIGH_QUALITY: PresetConfig(
        cleaning_temperature=0.1,
        review_temperature=0.0,
        cleaning_model="o3-mini-2025-01-31",
        review_model="o3-mini-2025-01-31",
        max_section_tokens=300,
        token_overlap=30,
        auto_accept_threshold=0.98,
        quick_review_threshold=0.90,
        detailed_review_threshold=0.75,
        description="Maximum quality with thorough processing. Takes longer but produces best results.",
        estimated_cost_multiplier=1.8,
    ),
}


@dataclass
class CostEstimate:
    """Estimated costs for processing based on configuration."""

    estimated_tokens: int
    estimated_cost_usd: float
    processing_time_minutes: int
    confidence: str  # "Low", "Medium", "High"


def get_merged_agent_config() -> AgentConfig:
    """Get agent configuration with session state overrides applied."""
    base_config = get_settings().get_agents_config()
    
    if not STREAMLIT_AVAILABLE:
        return base_config
        
    # Apply session state overrides if they exist
    overrides = st.session_state.get("config_overrides", {}).get("agents", {})
    if not overrides:
        return base_config
        
    # Create new config with overrides
    return AgentConfig(
        cleaning_temperature=overrides.get("cleaning_temperature", base_config.cleaning_temperature),
        review_temperature=overrides.get("review_temperature", base_config.review_temperature),
        cleaning_model=overrides.get("cleaning_model", base_config.cleaning_model),
        review_model=overrides.get("review_model", base_config.review_model),
        max_concurrent_requests=overrides.get("max_concurrent_requests", base_config.max_concurrent_requests),
        rate_limit_requests_per_minute=overrides.get("rate_limit_requests_per_minute", base_config.rate_limit_requests_per_minute),
    )


def get_merged_processing_config() -> ProcessingConfig:
    """Get processing configuration with session state overrides applied."""
    base_config = get_settings().get_processing_config()
    
    if not STREAMLIT_AVAILABLE:
        return base_config
        
    # Apply session state overrides if they exist
    overrides = st.session_state.get("config_overrides", {}).get("processing", {})
    if not overrides:
        return base_config
        
    # Create new config with overrides
    return ProcessingConfig(
        max_section_tokens=overrides.get("max_section_tokens", base_config.max_section_tokens),
        token_overlap=overrides.get("token_overlap", base_config.token_overlap),
        min_segment_tokens=overrides.get("min_segment_tokens", base_config.min_segment_tokens),
        preserve_sentence_boundaries=overrides.get("preserve_sentence_boundaries", base_config.preserve_sentence_boundaries),
    )


def get_merged_confidence_thresholds() -> ConfidenceThresholds:
    """Get confidence thresholds with session state overrides applied."""
    base_config = get_settings().get_confidence_thresholds()
    
    if not STREAMLIT_AVAILABLE:
        return base_config
        
    # Apply session state overrides if they exist
    overrides = st.session_state.get("config_overrides", {}).get("confidence_thresholds", {})
    if not overrides:
        return base_config
        
    # Create new config with overrides
    return ConfidenceThresholds(
        auto_accept_threshold=overrides.get("auto_accept_threshold", base_config.auto_accept_threshold),
        quick_review_threshold=overrides.get("quick_review_threshold", base_config.quick_review_threshold),
        detailed_review_threshold=overrides.get("detailed_review_threshold", base_config.detailed_review_threshold),
    )


def validate_configuration() -> tuple[bool, list[str]]:
    """
    Validate current configuration.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    try:
        # Validate by creating settings instance
        get_settings()
    except Exception as e:
        errors.append(f"Configuration error: {str(e)}")

    return len(errors) == 0, errors


def estimate_processing_cost(document_length_chars: int | None = None) -> CostEstimate:
    """
    Estimate processing cost based on current configuration.

    Args:
        document_length_chars: Optional document length for more accurate estimates

    Returns:
        CostEstimate with rough cost and time projections
    """
    # Get current configuration
    processing_config = get_settings().get_processing_config()

    # Default document size if not provided (typical meeting transcript)
    if document_length_chars is None:
        document_length_chars = 50000  # ~50k chars = ~20-30 pages

    # Rough token estimation (1 token ≈ 4 characters for English text)
    estimated_input_tokens = document_length_chars // 4

    # Calculate segments based on max_section_tokens
    num_segments = max(
        1, estimated_input_tokens // processing_config.max_section_tokens
    )

    # Account for overlap increasing total tokens processed
    overlap_factor = 1.0 + (
        processing_config.token_overlap / processing_config.max_section_tokens
    )
    total_input_tokens = int(estimated_input_tokens * overlap_factor)

    # Estimate output tokens (typically 50-80% of input for cleaning)
    estimated_output_tokens = int(total_input_tokens * 0.65)

    total_tokens = total_input_tokens + estimated_output_tokens

    # Cost estimation for o3-mini (rough pricing)
    # Input: $0.125 per 1M tokens, Output: $0.250 per 1M tokens
    input_cost = (total_input_tokens / 1_000_000) * 0.125
    output_cost = (estimated_output_tokens / 1_000_000) * 0.250
    estimated_cost = input_cost + output_cost

    # Processing time estimate (rough)
    # Assume ~2-5 seconds per segment for API calls + processing
    estimated_time_minutes = max(1, (num_segments * 3) // 60)

    # Confidence based on available information
    confidence = "Medium" if document_length_chars else "Low"

    return CostEstimate(
        estimated_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        processing_time_minutes=estimated_time_minutes,
        confidence=confidence,
    )


def get_configuration_summary() -> dict[str, Any]:
    """
    Get a summary of current configuration for display.

    Returns:
        Dictionary with human-readable configuration summary
    """
    settings = get_settings()
    agent_config = settings.get_agents_config()
    processing_config = settings.get_processing_config()
    confidence_config = settings.get_confidence_thresholds()

    return {
        "Agent Settings": {
            "Cleaning Temperature": f"{agent_config.cleaning_temperature:.2f}",
            "Review Temperature": f"{agent_config.review_temperature:.2f}",
            "Cleaning Model": agent_config.cleaning_model,
            "Review Model": agent_config.review_model,
        },
        "Processing Settings": {
            "Max Section Tokens": processing_config.max_section_tokens,
            "Token Overlap": processing_config.token_overlap,
            "Min Segment Tokens": processing_config.min_segment_tokens,
        },
        "Confidence Thresholds": {
            "Auto Accept": f"{confidence_config.auto_accept_threshold:.2%}",
            "Quick Review": f"{confidence_config.quick_review_threshold:.2%}",
            "Detailed Review": f"{confidence_config.detailed_review_threshold:.2%}",
        },
    }


def get_active_preset() -> QualityPreset | None:
    """
    Determine if current configuration matches a quality preset.

    Returns:
        QualityPreset if configuration matches a preset, None otherwise
    """
    settings = get_settings()
    current_agent = settings.get_agents_config()
    current_processing = settings.get_processing_config()
    current_confidence = settings.get_confidence_thresholds()

    for preset, config in QUALITY_PRESETS.items():
        if (
            abs(current_agent.cleaning_temperature - config.cleaning_temperature)
            < 0.001
            and abs(current_agent.review_temperature - config.review_temperature)
            < 0.001
            and current_agent.cleaning_model == config.cleaning_model
            and current_agent.review_model == config.review_model
            and current_processing.max_section_tokens == config.max_section_tokens
            and current_processing.token_overlap == config.token_overlap
            and abs(
                current_confidence.auto_accept_threshold - config.auto_accept_threshold
            )
            < 0.001
            and abs(
                current_confidence.quick_review_threshold
                - config.quick_review_threshold
            )
            < 0.001
            and abs(
                current_confidence.detailed_review_threshold
                - config.detailed_review_threshold
            )
            < 0.001
        ):
            return preset

    return None


def get_config_warnings() -> list[str]:
    """
    Get warnings about potentially problematic configuration settings.

    Returns:
        List of warning messages
    """
    warnings = []

    try:
        settings = get_settings()
        agent_config = settings.get_agents_config()
        processing_config = settings.get_processing_config()
        confidence_config = settings.get_confidence_thresholds()

        # Check for very high temperatures
        if agent_config.cleaning_temperature > 1.5:
            warnings.append(
                "⚠️ High cleaning temperature may produce inconsistent results"
            )

        if agent_config.review_temperature > 0.5:
            warnings.append(
                "⚠️ High review temperature may affect quality assessment accuracy"
            )

        # Check for very large section sizes (expensive)
        if processing_config.max_section_tokens > 2000:
            warnings.append(
                "💰 Large section tokens will significantly increase processing costs"
            )

        # Check for very high overlap (inefficient)
        if processing_config.token_overlap > processing_config.max_section_tokens * 0.3:
            warnings.append(
                "⏱️ High token overlap may slow processing without much benefit"
            )

        # Check for very strict thresholds
        if confidence_config.auto_accept_threshold > 0.98:
            warnings.append(
                "🔍 Very high auto-accept threshold may require manual review of most segments"
            )

        # Check threshold ordering
        if (
            confidence_config.detailed_review_threshold
            >= confidence_config.quick_review_threshold
        ):
            warnings.append(
                "❌ Detailed review threshold should be lower than quick review threshold"
            )

    except Exception:
        warnings.append(
            "❌ Configuration validation failed - please check your settings"
        )

    return warnings


@lru_cache(maxsize=1)
def get_available_openai_models() -> list[str]:
    """
    Fetch available OpenAI models from the API.

    Returns a list of available model IDs, defaulting to o3-mini first.
    """
    try:
        import openai

        # Get OpenAI configuration
        openai_config = get_settings().get_openai_config()

        # Initialize OpenAI client
        client = openai.OpenAI(api_key=openai_config.api_key)

        # Fetch available models
        models_response = client.models.list()

        # Get all model IDs and sort with o3-mini first
        all_models = [model.id for model in models_response.data]

        # Sort: o3-mini first, then other models alphabetically
        def sort_models(model_id: str) -> tuple[int, str]:
            if "o3-mini" in model_id.lower():
                return (0, model_id)
            else:
                return (1, model_id)

        all_models.sort(key=sort_models)

        logger.info(f"Available OpenAI models: {all_models}")

        return all_models

    except Exception as e:
        logger.error(f"Failed to fetch OpenAI models: {e}")
        # Return fallback models with o3-mini first
        return ["o3-mini", "o3"]


def apply_preset(preset: QualityPreset) -> None:
    """
    Apply a quality preset to the current session configuration.
    
    Args:
        preset: The quality preset to apply
    """
    if not STREAMLIT_AVAILABLE:
        logger.warning("Streamlit not available, cannot apply preset")
        return
        
    config = QUALITY_PRESETS[preset]
    
    # Clear existing overrides
    clear_config_overrides()
    
    # Apply preset configuration to config_overrides
    st.session_state.config_overrides = {
        "agents": {
            "cleaning_temperature": config.cleaning_temperature,
            "review_temperature": config.review_temperature,
            "cleaning_model": config.cleaning_model,
            "review_model": config.review_model,
        },
        "processing": {
            "max_section_tokens": config.max_section_tokens,
            "token_overlap": config.token_overlap,
        },
        "confidence_thresholds": {
            "auto_accept_threshold": config.auto_accept_threshold,
            "quick_review_threshold": config.quick_review_threshold,
            "detailed_review_threshold": config.detailed_review_threshold,
        }
    }
    
    # Also update the Streamlit widget keys so the UI reflects the new values
    st.session_state["cleaning_temperature"] = config.cleaning_temperature
    st.session_state["review_temperature"] = config.review_temperature
    st.session_state["cleaning_model"] = config.cleaning_model
    st.session_state["review_model"] = config.review_model
    st.session_state["max_section_tokens"] = config.max_section_tokens
    st.session_state["token_overlap"] = config.token_overlap
    st.session_state["auto_accept_threshold"] = config.auto_accept_threshold
    st.session_state["quick_review_threshold"] = config.quick_review_threshold
    st.session_state["detailed_review_threshold"] = config.detailed_review_threshold
    
    logger.info(f"Applied {preset.value} preset configuration")


def clear_config_overrides() -> None:
    """Clear all configuration overrides from session state."""
    if not STREAMLIT_AVAILABLE:
        return
        
    # Clear the config overrides
    if "config_overrides" in st.session_state:
        del st.session_state.config_overrides
    
    # Also clear the widget keys to reset them to default values
    widget_keys = [
        "cleaning_temperature", "review_temperature", "cleaning_model", "review_model",
        "max_section_tokens", "token_overlap", "min_segment_tokens", "preserve_sentence_boundaries",
        "auto_accept_threshold", "quick_review_threshold", "detailed_review_threshold"
    ]
    
    for key in widget_keys:
        if key in st.session_state:
            del st.session_state[key]
    
    logger.info("Cleared configuration overrides and widget keys")


def has_config_overrides() -> bool:
    """Check if there are any configuration overrides in session state."""
    if not STREAMLIT_AVAILABLE:
        return False
        
    return bool(st.session_state.get("config_overrides", {}))


def set_config_override(section: str, key: str, value: Any) -> None:
    """
    Set a configuration override in session state.
    
    Args:
        section: Configuration section (agents, processing, confidence_thresholds)
        key: Configuration key
        value: New value
    """
    if not STREAMLIT_AVAILABLE:
        logger.warning("Streamlit not available, cannot set config override")
        return
        
    if "config_overrides" not in st.session_state:
        st.session_state.config_overrides = {}
        
    if section not in st.session_state.config_overrides:
        st.session_state.config_overrides[section] = {}
        
    st.session_state.config_overrides[section][key] = value
    logger.info(f"Set config override: {section}.{key} = {value}")
