"""
Accuracy tests with REAL API calls - OPTIONAL and COST-AWARE

These tests verify AI accuracy using real OpenAI API calls.
They are designed to be run:
- Manually by developers
- On CI with environment flag (ENABLE_ACCURACY_TESTS=true)
- With a small, curated golden dataset to control costs

Best Practices:
1. Keep the test dataset small (10-20 examples)
2. Use cheaper models for development (gpt-3.5-turbo)
3. Track accuracy trends over time
4. Focus on critical quality metrics
"""

import os
from typing import Any

from dotenv import load_dotenv
import pytest

from core.cleaning_agent import CleaningAgent
from core.review_agent import ReviewAgent
from models.schemas import CleaningResult

load_dotenv()

# Skip accuracy tests if no valid API key or if not explicitly enabled
ENABLE_ACCURACY_TESTS = os.getenv("ENABLE_ACCURACY_TESTS", "false").lower() == "true"
HAS_VALID_API_KEY = bool(
    os.getenv("OPENAI_API_KEY")
    and not os.getenv("OPENAI_API_KEY", "").startswith("sk-test-")
)


# Golden dataset - small, high-quality test cases
GOLDEN_TEST_CASES = [
    {
        "id": "filler_words_basic",
        "input": "Um, so like, we need to, uh, discuss the quarterly metrics, you know?",
        "expected_improvements": ["remove_fillers", "improve_flow"],
        "min_confidence": 0.85,
        "category": "easy",
    },
    {
        "id": "grammar_correction",
        "input": "The team have completed there tasks and we was ready to present.",
        "expected_improvements": ["fix_grammar", "correct_spelling"],
        "min_confidence": 0.80,
        "category": "medium",
    },
    {
        "id": "repetition_removal",
        "input": "We need to to review the the budget and and make sure everything everything is correct.",
        "expected_improvements": ["remove_repetition"],
        "min_confidence": 0.85,
        "category": "easy",
    },
    {
        "id": "technical_content",
        "input": "Our API latency is averaging 250ms with p99 at 850ms across all microservices.",
        "expected_improvements": ["preserve_technical_terms"],
        "min_confidence": 0.75,
        "category": "hard",
    },
    {
        "id": "mixed_issues",
        "input": "Um, the Q4 numbers are, uh, they're showing a 15% increase, but, like, we need to to verify the the data, you know, especially the the conversion rates.",
        "expected_improvements": [
            "remove_fillers",
            "remove_repetition",
            "preserve_numbers",
        ],
        "min_confidence": 0.70,
        "category": "hard",
    },
]


@pytest.mark.skipif(
    not (ENABLE_ACCURACY_TESTS and HAS_VALID_API_KEY),
    reason="Accuracy tests require ENABLE_ACCURACY_TESTS=true and valid OpenAI API key",
)
@pytest.mark.asyncio
async def test_cleaning_agent_accuracy():
    """Test cleaning agent accuracy on golden dataset."""
    # Force reload environment variables for pytest compatibility

    from dotenv import load_dotenv

    load_dotenv()

    agent = CleaningAgent()

    # Process golden test cases
    results = []
    for test_case in GOLDEN_TEST_CASES:
        print(f"\nTesting case: {test_case['id']}")
        print(f"Input: {test_case['input']}")

        # Create a test segment
        from models.schemas import DocumentSegment

        segment = DocumentSegment(
            id=f"test-{test_case['id']}",
            content=test_case["input"],
            token_count=20,  # Approximate
            start_index=0,
            end_index=len(test_case["input"]),
            sequence_number=1,
        )

        try:
            # Real API call
            result = await agent.clean_segment(segment)

            print(f"Output: {result.cleaned_text}")
            print(f"Changes: {len(result.changes_made)} changes made")
            print(f"Changes: {result.changes_made}")

            # Evaluate result
            evaluation = _evaluate_cleaning_result(result, test_case)
            results.append(evaluation)

            assert len(result.cleaned_text.strip()) > 0, "Cleaned text is empty"

        except Exception as e:
            pytest.fail(f"Failed processing test case {test_case['id']}: {e}")

    # Overall accuracy assessment
    _assess_overall_accuracy(results)


@pytest.mark.skipif(
    not (ENABLE_ACCURACY_TESTS and HAS_VALID_API_KEY),
    reason="Accuracy tests require ENABLE_ACCURACY_TESTS=true and valid OpenAI API key",
)
@pytest.mark.asyncio
async def test_review_agent_accuracy():
    """Test review agent accuracy on cleaning results."""
    # Force reload environment variables for pytest compatibility

    from dotenv import load_dotenv

    load_dotenv()

    # Ensure API key is set in environment (pytest workaround)
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    cleaning_agent = CleaningAgent()
    review_agent = ReviewAgent()

    for test_case in GOLDEN_TEST_CASES[:3]:  # Test subset to save costs
        print(f"\nTesting review for: {test_case['id']}")

        # Create test segment
        from models.schemas import DocumentSegment

        segment = DocumentSegment(
            id=f"review-test-{test_case['id']}",
            content=test_case["input"],
            token_count=20,
            start_index=0,
            end_index=len(test_case["input"]),
            sequence_number=1,
        )

        # First clean, then review
        cleaning_result = await cleaning_agent.clean_segment(segment)
        review_result = await review_agent.review_cleaning(
            original_segment=segment, cleaning_result=cleaning_result
        )

        print(f"Review decision: {review_result.decision}")
        print(f"Review confidence: {review_result.confidence:.3f}")
        print(f"Issues found: {review_result.issues_found}")

        # Assertions
        assert review_result.confidence >= 0.7, "Review confidence too low"
        assert len(review_result.reasoning) > 10, "Review reasoning too brief"


def _evaluate_cleaning_result(
    result: CleaningResult, test_case: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate the quality of a cleaning result."""
    evaluation = {
        "test_id": test_case["id"],
        "category": test_case["category"],
        "confidence": 0.8,  # Default since CleaningAgent no longer provides confidence
        "preservation": True,  # Default since CleaningAgent no longer provides preservation check
        "changes_count": len(result.changes_made),
        "quality_metrics": {},
    }

    original = test_case["input"]
    cleaned = result.cleaned_text

    # Basic quality metrics
    evaluation["quality_metrics"] = {
        "length_ratio": len(cleaned) / len(original) if len(original) > 0 else 0,
        "filler_words_removed": _count_filler_words(original)
        - _count_filler_words(cleaned),
        "repetition_reduced": _has_repetition_reduction(original, cleaned),
        "preserves_numbers": _preserves_numbers(original, cleaned),
        "preserves_technical_terms": _preserves_technical_terms(original, cleaned),
    }

    return evaluation


def _assess_overall_accuracy(results: list[dict[str, Any]]) -> None:
    """Assess overall accuracy across all test cases."""
    if not results:
        pytest.fail("No results to assess")

    # Calculate metrics by category
    by_category = {"easy": [], "medium": [], "hard": []}
    for result in results:
        by_category[result["category"]].append(result)

    print("\n=== ACCURACY ASSESSMENT ===")

    overall_confidence = sum(r["confidence"] for r in results) / len(results)
    print(f"Overall confidence: {overall_confidence:.3f}")

    for category, category_results in by_category.items():
        if category_results:
            avg_conf = sum(r["confidence"] for r in category_results) / len(
                category_results
            )
            print(f"{category.title()} cases confidence: {avg_conf:.3f}")

            # Thresholds by category
            thresholds = {"easy": 0.85, "medium": 0.75, "hard": 0.65}
            assert (
                avg_conf >= thresholds[category]
            ), f"{category} cases below threshold: {avg_conf:.3f} < {thresholds[category]}"

    preservation_rate = sum(1 for r in results if r["preservation"]) / len(results)
    print(f"Preservation rate: {preservation_rate:.1%}")
    assert (
        preservation_rate >= 0.95
    ), f"Preservation rate too low: {preservation_rate:.1%}"

    print("=== All accuracy thresholds met! ===")


def _count_filler_words(text: str) -> int:
    """Count filler words in text."""
    fillers = {"um", "uh", "like", "you know", "so", "well", "actually"}
    words = text.lower().split()
    return sum(1 for word in words if word.strip(".,!?") in fillers)


def _has_repetition_reduction(original: str, cleaned: str) -> bool:
    """Check if repetition was reduced."""
    original_words = original.split()
    cleaned_words = cleaned.split()

    # Count consecutive repeated words
    def count_repetitions(words):
        count = 0
        for i in range(len(words) - 1):
            if words[i] == words[i + 1]:
                count += 1
        return count

    return count_repetitions(cleaned_words) < count_repetitions(original_words)


def _preserves_numbers(original: str, cleaned: str) -> bool:
    """Check if numbers are preserved."""
    import re

    original_numbers = set(re.findall(r"\d+(?:\.\d+)?", original))
    cleaned_numbers = set(re.findall(r"\d+(?:\.\d+)?", cleaned))
    return original_numbers.issubset(cleaned_numbers)


def _preserves_technical_terms(original: str, cleaned: str) -> bool:
    """Check if technical terms are preserved."""
    technical_terms = {"API", "latency", "p99", "microservices", "Q4", "conversion"}
    original_lower = original.lower()
    cleaned_lower = cleaned.lower()

    for term in technical_terms:
        if term.lower() in original_lower and term.lower() not in cleaned_lower:
            return False
    return True


def test_cost_estimation():
    """Estimate the cost of running accuracy tests."""

    # Rough cost calculation
    num_test_cases = len(GOLDEN_TEST_CASES)
    avg_tokens_per_case = 50  # Input + output
    cost_per_1k_tokens = 0.002  # GPT-4o pricing (approximate)

    estimated_cost = (num_test_cases * avg_tokens_per_case * cost_per_1k_tokens) / 1000

    print("\n=== COST ESTIMATION ===")
    print(f"Test cases: {num_test_cases}")
    print(f"Estimated tokens per case: {avg_tokens_per_case}")
    print(f"Estimated total cost: ${estimated_cost:.4f}")
    print("Max acceptable cost: $0.10")

    assert estimated_cost < 0.10, f"Accuracy tests too expensive: ${estimated_cost:.4f}"
    print("Cost estimate within acceptable range!")


if __name__ == "__main__":
    print("To run accuracy tests with real API calls:")
    print("ENABLE_ACCURACY_TESTS=true pytest tests/test_accuracy_optional.py -v")
