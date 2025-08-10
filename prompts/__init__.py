"""Prompt templates for the dual-agent transcript cleaning system."""

from .cleaning import CLEANING_PROMPT, get_cleaning_prompt
from .review import REVIEW_PROMPT, get_review_prompt

__all__ = [
    "CLEANING_PROMPT",
    "get_cleaning_prompt",
    "REVIEW_PROMPT",
    "get_review_prompt",
]
