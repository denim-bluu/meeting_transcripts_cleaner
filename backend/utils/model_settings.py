"""Utilities for configuring OpenAI model settings with optional reasoning support."""

from __future__ import annotations

from typing import Any

from pydantic_ai.models.openai import OpenAIResponsesModelSettings

_REASONING_PREFIXES = (
    "o1",
    "o2",
    "o3",
    "o4",
    "o-",
)


def supports_reasoning_settings(model_name: str | None) -> bool:
    """Return True when the model accepts reasoning options."""
    if not model_name:
        return False
    normalized = model_name.strip().lower()
    return normalized.startswith(_REASONING_PREFIXES)


def build_openai_model_settings(
    model_name: str | None,
    *,
    reasoning_effort: str | None = None,
    reasoning_summary: str | None = None,
    **overrides: Any,
) -> OpenAIResponsesModelSettings:
    """Create OpenAIResponsesModelSettings gating reasoning kwargs by model capability."""
    kwargs: dict[str, Any] = dict(overrides)
    if supports_reasoning_settings(model_name):
        if reasoning_effort:
            kwargs["openai_reasoning_effort"] = reasoning_effort
        if reasoning_summary:
            kwargs["openai_reasoning_summary"] = reasoning_summary
    return OpenAIResponsesModelSettings(**kwargs)

