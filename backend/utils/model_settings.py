"""Utilities for configuring OpenAI model settings with optional reasoning support."""

from __future__ import annotations

from typing import Any

from pydantic_ai.models.openai import OpenAIResponsesModelSettings

_REASONING_PREFIXES = ("o1", "o2", "o3", "o4", "o-")


def build_openai_model_settings(
    model_name: str | None,
    *,
    reasoning_effort: str | None = None,
    reasoning_summary: str | None = None,
    **overrides: Any,
) -> OpenAIResponsesModelSettings:
    """Create OpenAIResponsesModelSettings gating reasoning kwargs by model capability."""
    kwargs: dict[str, Any] = dict(overrides)
    # Check if model supports reasoning settings by checking prefix
    supports_reasoning = model_name and model_name.strip().lower().startswith(
        _REASONING_PREFIXES
    )
    if supports_reasoning:
        if reasoning_effort:
            kwargs["openai_reasoning_effort"] = reasoning_effort
        if reasoning_summary:
            kwargs["openai_reasoning_summary"] = reasoning_summary
    return OpenAIResponsesModelSettings(**kwargs)
