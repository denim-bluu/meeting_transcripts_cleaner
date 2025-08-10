"""
Clean pytest configuration and fixtures for the Meeting Transcript Cleaner test suite.

This module provides:
- Essential fixtures for testing components
- Test configuration and setup
- Mock data generators
"""

import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock

from faker import Faker
import pytest

# Set test API key before importing config
os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing-only-do-not-use-in-production"

# Add project root to path for testing
test_dir = Path(__file__).parent
project_root = test_dir.parent
sys.path.insert(0, str(project_root))

# Import after setting up environment
from config import reset_config  # noqa: E402
from core.cleaning_agent import CleaningAgent  # noqa: E402
from core.confidence_categorizer import ConfidenceCategorizer  # noqa: E402
from core.document_processor import DocumentProcessor  # noqa: E402
from core.review_agent import ReviewAgent  # noqa: E402
from models.schemas import (  # noqa: E402
    CleaningResult,
    DocumentSegment,
    ReviewDecision,
    ReviewDecisionEnum,
)

# Initialize Faker for test data generation
fake = Faker()
fake.seed_instance(42)  # Deterministic fake data


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment with mock API responses."""
    # Reset configuration cache before each test
    reset_config()

    os.environ["USE_MOCK_RESPONSES"] = "true"
    os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing-only"
    os.environ["LOG_LEVEL"] = "WARNING"  # Reduce noise in tests
    os.environ["PROCESSING__MIN_SEGMENT_TOKENS"] = "5"
    os.environ["PROCESSING__MAX_SECTION_TOKENS"] = "500"
    os.environ["PROCESSING__TOKEN_OVERLAP"] = "20"
    os.environ["DEVELOPMENT__TEST_MODE"] = "true"

    yield

    # Cleanup after test
    for key in ["USE_MOCK_RESPONSES", "PROCESSING__MIN_SEGMENT_TOKENS",
                "PROCESSING__MAX_SECTION_TOKENS", "PROCESSING__TOKEN_OVERLAP",
                "DEVELOPMENT__TEST_MODE"]:
        os.environ.pop(key, None)
    reset_config()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_transcript_text() -> str:
    """Generate sample transcript text with common issues."""
    return """
    John Smith: Um, so welcome everyone to, uh, the quarterly meeting. I know we're all, you know, really excited to get started on this new initiative.

    Sarah Johnson: Thanks John. Yeah, I'm really, uh, looking forward to working on this project. We've been, um, preparing for this moment and I think we're ready to, you know, tackle the challenges ahead.

    Mike Davis: Absolutely. The requirements that we discussed last week are, um, they're pretty clear. We need to implement the new user authentication system and also, you know, improve the database performance significantly.
    """.strip()


@pytest.fixture
def sample_clean_text() -> str:
    """Generate sample cleaned text."""
    return """
    John Smith: Welcome everyone to the quarterly meeting. I know we're all really excited to get started on this new initiative.

    Sarah Johnson: Thanks John. I'm really looking forward to working on this project. We've been preparing for this moment and I think we're ready to tackle the challenges ahead.

    Mike Davis: Absolutely. The requirements that we discussed last week are pretty clear. We need to implement the new user authentication system and also improve the database performance significantly.
    """.strip()


@pytest.fixture
def sample_document_segment(sample_transcript_text: str) -> DocumentSegment:
    """Create a sample document segment for testing."""
    return DocumentSegment(
        content=sample_transcript_text[:200],
        token_count=50,
        start_index=0,
        end_index=200,
        sequence_number=1,
    )


@pytest.fixture
def sample_cleaning_result(
    sample_document_segment: DocumentSegment, sample_clean_text: str
) -> CleaningResult:
    """Create a sample cleaning result for testing."""
    return CleaningResult(
        segment_id=sample_document_segment.id,
        cleaned_text=sample_clean_text[:200],
        changes_made=[
            "Removed filler words: 'Um', 'uh', 'you know'",
            "Improved grammar",
        ],
        processing_time_ms=1250.5,
        model_used="o3-mini",
    )


@pytest.fixture
def sample_review_decision(sample_document_segment: DocumentSegment) -> ReviewDecision:
    """Create a sample review decision for testing."""
    return ReviewDecision(
        segment_id=sample_document_segment.id,
        decision=ReviewDecisionEnum.ACCEPT,
        confidence=0.95,
        issues_found=[],
        reasoning="Clean removal of filler words while preserving meaning and context.",
        processing_time_ms=850.3,
        model_used="o3-mini",
    )


@pytest.fixture
def document_processor() -> DocumentProcessor:
    """Create a document processor instance with test-friendly settings."""
    processor = DocumentProcessor()
    processor.min_tokens = 5
    processor.max_tokens = 500
    return processor


@pytest.fixture
def mock_cleaning_agent() -> MagicMock:
    """Create a mock cleaning agent for testing."""
    agent = MagicMock(spec=CleaningAgent)
    agent.clean_segment = AsyncMock()
    agent.model = "o3-mini"
    agent.temperature = 0.2
    agent.max_tokens = 4000
    return agent


@pytest.fixture
def mock_review_agent() -> MagicMock:
    """Create a mock review agent for testing."""
    agent = MagicMock(spec=ReviewAgent)
    agent.review_cleaning = AsyncMock()
    agent.model = "o3-mini"
    agent.temperature = 0.0
    agent.max_tokens = 4000
    return agent


@pytest.fixture
def confidence_categorizer() -> ConfidenceCategorizer:
    """Create a confidence categorizer instance."""
    return ConfidenceCategorizer()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: mark test as slow")
    config.addinivalue_line("markers", "integration: mark test as integration test")


class TestMetrics:
    """Utility class for calculating test metrics."""

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def count_filler_words(text: str) -> int:
        """Count common filler words in text."""
        filler_words = ["um", "uh", "er", "ah", "like", "you know", "so", "well"]
        text_lower = text.lower()
        count = 0

        for filler in filler_words:
            count += text_lower.count(filler)

        return count


@pytest.fixture
def test_metrics() -> TestMetrics:
    """Provide test metrics utility."""
    return TestMetrics()
