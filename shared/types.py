"""Shared type definitions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

# Standardized progress callback type
ProgressCallback = (
    Callable[[float, str], None] | Callable[[float, str], Awaitable[None]]
)
