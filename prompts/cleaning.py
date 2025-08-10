"""
Prompt template for the Cleaning Agent.

This agent performs the first stage of transcript cleaning with high accuracy
and provides confidence scoring for progressive review categorization.
"""

from typing import Any

# Base cleaning prompt template
CLEANING_PROMPT = """Segment {segment_number}/{total_segments} ({token_count} tokens)
ID: {segment_id}

Context:
Previous: {previous_context}
Following: {following_context}

Text to clean:
```
{text_content}
```

Apply standard cleaning (grammar, fillers, clarity) while preserving all meaning, speaker voice, and content. Document changes made."""


def get_cleaning_prompt(
    text_content: str,
    segment_number: int,
    total_segments: int,
    token_count: int,
    segment_id: str,
    previous_context: str = "",
    following_context: str = "",
) -> str:
    """
    Generate a complete cleaning prompt with context.

    Args:
        text_content: The transcript text to clean
        segment_number: Current segment number (1-indexed)
        total_segments: Total number of segments in the document
        token_count: Number of tokens in the current segment
        previous_context: Context from previous segment (optional)
        following_context: Context from following segment (optional)

    Returns:
        Complete prompt string ready for the AI model
    """
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

    return CLEANING_PROMPT.format(
        segment_number=segment_number,
        total_segments=total_segments,
        token_count=token_count,
        segment_id=segment_id,
        previous_context=prev_context,
        following_context=next_context,
        text_content=text_content.strip(),
    )


def get_cleaning_examples() -> dict[str, Any]:
    """
    Get example inputs and expected outputs for the cleaning agent.

    Returns:
        Dictionary containing example scenarios for testing and validation
    """
    return {
        "high_confidence": {
            "input": "So, um, we need to, uh, discuss the budget for Q4. Their going to review it next week.",
            "expected_output": {
                "cleaned_text": "We need to discuss the budget for Q4. They're going to review it next week.",
                "changes_made": [
                    "Removed filler words: 'So, um' and 'uh'",
                    "Fixed typo: 'Their' → 'They're'",
                ],
            },
        },
        "medium_confidence": {
            "input": "John mentioned that the thing we talked about before should be done by next Friday. The team lead will handle it.",
            "expected_output": {
                "cleaned_text": "John mentioned that the project we discussed previously should be completed by next Friday. The team lead will handle it.",
                "changes_made": [
                    "Clarified vague reference: 'the thing' → 'the project'",
                    "Improved verb choice: 'should be done' → 'should be completed'",
                ],
            },
        },
        "low_confidence": {
            "input": "The... when we... I think the numbers were... maybe around 15% or something like that?",
            "expected_output": {
                "cleaned_text": "The numbers were approximately 15%.",
                "changes_made": [
                    "Removed incomplete speech fragments",
                    "Consolidated uncertain phrasing into clear statement",
                ],
            },
        },
    }
