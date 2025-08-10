"""
Prompt template for the Review Agent.

This agent performs quality assurance as the second stage in the dual-agent system,
validating cleaning results and making final approval decisions.
"""

from typing import Any

# Base review prompt template
REVIEW_PROMPT = """Segment {segment_number}/{total_segments} ({token_count} tokens)
ID: {segment_id}

Original:
```
{original_text}
```

Cleaned:
```
{cleaned_text}
```

Changes: {changes_made}

Context:
Previous: {previous_context}
Following: {following_context}

Review for meaning preservation, quality, and appropriateness. Score confidence and preservation."""


def get_review_prompt(
    original_text: str,
    cleaned_text: str,
    changes_made: list,
    segment_number: int,
    total_segments: int,
    token_count: int,
    segment_id: str,
    previous_context: str = "",
    following_context: str = "",
) -> str:
    """
    Generate a complete review prompt with all context.

    Args:
        original_text: The original transcript segment
        cleaned_text: The cleaned version from the Cleaning Agent
        changes_made: List of changes made by the Cleaning Agent
        segment_number: Current segment number (1-indexed)
        total_segments: Total number of segments in the document
        token_count: Number of tokens in the original segment
        segment_id: Unique UUID identifier for the segment
        previous_context: Context from previous segment (optional)
        following_context: Context from following segment (optional)

    Returns:
        Complete prompt string ready for the AI model
    """
    # Format changes list
    changes_str = (
        "\n".join([f"  • {change}" for change in changes_made])
        if changes_made
        else "  • No changes listed"
    )

    # Prepare context strings
    prev_context = (
        f'Previous segment ended with: "...{previous_context}"'
        if previous_context
        else "This is the first segment."
    )
    next_context = (
        f'Following segment begins with: "{following_context}..."'
        if following_context
        else "This is the last segment."
    )

    return REVIEW_PROMPT.format(
        original_text=original_text.strip(),
        cleaned_text=cleaned_text.strip(),
        changes_made=changes_str,
        segment_number=segment_number,
        total_segments=total_segments,
        token_count=token_count,
        segment_id=segment_id,
        previous_context=prev_context,
        following_context=next_context,
    )


def get_review_examples() -> dict[str, Any]:
    """
    Get example inputs and expected outputs for the review agent.

    Returns:
        Dictionary containing example review scenarios for testing and validation
    """
    return {
        "accept_scenario": {
            "original": "So, um, we need to, uh, discuss the budget for Q4. Their going to review it next week.",
            "cleaned": "We need to discuss the budget for Q4. They're going to review it next week.",
            "changes": ["Removed filler words", "Fixed typo: 'Their' → 'They're'"],
            "expected_decision": {
                "decision": "accept",
                "confidence": 0.98,
                "preservation_score": 1.0,
                "issues_found": [],
                "suggested_corrections": None,
                "reasoning": "Excellent cleaning work. Filler words were appropriately removed and the typo was corrected. Original meaning and context are perfectly preserved. Changes improve readability without altering intent.",
            },
        },
        "modify_scenario": {
            "original": "John mentioned the project deadline.",
            "cleaned": "John stated that the project deadline is unrealistic and needs to be extended.",
            "changes": ["Enhanced clarity and added context"],
            "expected_decision": {
                "decision": "modify",
                "confidence": 0.75,
                "preservation_score": 0.6,
                "issues_found": ["Added interpretation not present in original"],
                "suggested_corrections": "John mentioned the project deadline.",
                "reasoning": "The cleaning agent added interpretation ('unrealistic and needs to be extended') that wasn't in the original text. This violates meaning preservation. The original should be kept as-is.",
            },
        },
        "reject_scenario": {
            "original": "The meeting will be at 3 PM in conference room A.",
            "cleaned": "The team gathering will occur at 3:00 PM in the main conference facility.",
            "changes": ["Improved formality and precision"],
            "expected_decision": {
                "decision": "reject",
                "confidence": 0.85,
                "preservation_score": 0.4,
                "issues_found": [
                    "Changed 'meeting' to 'team gathering' - alters meaning",
                    "Changed 'conference room A' to 'main conference facility' - loses specific information",
                ],
                "suggested_corrections": None,
                "reasoning": "Multiple unnecessary changes that alter specific information. 'Conference room A' is specific location data that shouldn't be generalized. The original was already clear and appropriate.",
            },
        },
    }
