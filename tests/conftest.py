"""
Pytest configuration and fixtures for the VTT transcript processing system.

This module provides:
- Essential fixtures for testing VTT processing components
- Test configuration and setup
- Mock VTT data generators
- OpenAI API mocking
"""

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set test API key before importing config
os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing-only-do-not-use-in-production"

# Add project root to path for testing
test_dir = Path(__file__).parent
project_root = test_dir.parent
sys.path.insert(0, str(project_root))

# Import after setting up environment
from core.ai_agents import TranscriptCleaner, TranscriptReviewer  # noqa: E402
from core.vtt_processor import VTTProcessor  # noqa: E402
from models.vtt import VTTChunk, VTTEntry  # noqa: E402
from services.transcript_service import TranscriptService  # noqa: E402


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up clean test environment."""
    # Set test-specific environment variables
    os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing-only"

    yield

    # Cleanup after test if needed


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_vtt_content() -> str:
    """Generate realistic sample VTT content for testing."""
    return """WEBVTT

d700e97e-1c7f-4753-9597-54e5e43b4642/1-0
00:00:01.000 --> 00:00:05.000
<v John Smith>Um, so welcome everyone to, uh, the quarterly meeting.</v>

d700e97e-1c7f-4753-9597-54e5e43b4642/2-0
00:00:05.000 --> 00:00:10.000
<v John Smith>I know we're all, you know, really excited to get started on this.</v>

d700e97e-1c7f-4753-9597-54e5e43b4642/3-0
00:00:10.000 --> 00:00:15.000
<v Sarah Johnson>Thanks John. Yeah, I'm really, uh, looking forward to this project.</v>

d700e97e-1c7f-4753-9597-54e5e43b4642/4-0
00:00:15.000 --> 00:00:20.000
<v Sarah Johnson>We've been, um, preparing for this moment and I think we're ready.</v>

d700e97e-1c7f-4753-9597-54e5e43b4642/5-0
00:00:20.000 --> 00:00:25.000
<v Mike Davis>Absolutely. The requirements are, um, they're pretty clear.</v>

d700e97e-1c7f-4753-9597-54e5e43b4642/6-0
00:00:25.000 --> 00:00:30.000
<v Mike Davis>We need to implement the new authentication system, you know.</v>"""


@pytest.fixture
def simple_vtt_content() -> str:
    """Generate minimal VTT content for basic testing."""
    return """WEBVTT

1
00:00:01.000 --> 00:00:05.000
<v Speaker1>Hello world.</v>

2
00:00:05.000 --> 00:00:10.000
<v Speaker2>How are you?</v>"""


@pytest.fixture
def sample_vtt_entry() -> VTTEntry:
    """Create a sample VTT entry for testing."""
    return VTTEntry(
        cue_id="test-entry-1",
        start_time=1.0,
        end_time=5.0,
        speaker="John Smith",
        text="Um, so welcome everyone to, uh, the quarterly meeting.",
    )


@pytest.fixture
def sample_vtt_entries() -> list[VTTEntry]:
    """Create a list of sample VTT entries for testing."""
    return [
        VTTEntry(
            cue_id="1",
            start_time=1.0,
            end_time=5.0,
            speaker="John Smith",
            text="Welcome everyone to the quarterly meeting.",
        ),
        VTTEntry(
            cue_id="2",
            start_time=5.0,
            end_time=10.0,
            speaker="John Smith",
            text="I know we're all excited to get started.",
        ),
        VTTEntry(
            cue_id="3",
            start_time=10.0,
            end_time=15.0,
            speaker="Sarah Johnson",
            text="Thanks John. I'm looking forward to this project.",
        ),
    ]


@pytest.fixture
def sample_vtt_chunk(sample_vtt_entries) -> VTTChunk:
    """Create a sample VTT chunk for testing."""
    return VTTChunk(chunk_id=0, entries=sample_vtt_entries, token_count=150)


@pytest.fixture
def vtt_processor() -> VTTProcessor:
    """Create a VTT processor instance."""
    return VTTProcessor()


@pytest.fixture
def mock_openai_response():
    """Mock successful OpenAI API response."""
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "cleaned_text": "Welcome everyone to the quarterly meeting. I know we're all excited to get started.",
                            "confidence": 0.95,
                            "changes_made": ["Removed filler words", "Fixed grammar"],
                        }
                    )
                }
            }
        ]
    }


@pytest.fixture
def mock_openai_review_response():
    """Mock successful OpenAI review response."""
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"quality_score": 0.85, "issues": [], "accept": True}
                    )
                }
            }
        ]
    }


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client


@pytest.fixture
def transcript_cleaner(mock_openai_client) -> TranscriptCleaner:
    """Create a TranscriptCleaner with mocked OpenAI client."""
    cleaner = TranscriptCleaner("test-api-key", "o3-mini")
    cleaner.client = mock_openai_client
    return cleaner


@pytest.fixture
def transcript_reviewer(mock_openai_client) -> TranscriptReviewer:
    """Create a TranscriptReviewer with mocked OpenAI client."""
    reviewer = TranscriptReviewer("test-api-key", "o3-mini")
    reviewer.client = mock_openai_client
    return reviewer


@pytest.fixture
def transcript_service() -> TranscriptService:
    """Create a TranscriptService instance."""
    return TranscriptService("test-api-key", max_concurrent=2, rate_limit=10)


@pytest.fixture
def mock_transcript_service():
    """Create a mock TranscriptService."""
    service = MagicMock(spec=TranscriptService)
    service.process_vtt = MagicMock()
    service.clean_transcript = AsyncMock()
    service.export = MagicMock()
    return service


# Test utilities
class VTTTestUtils:
    """Utility class for VTT testing helpers."""

    @staticmethod
    def count_speakers(entries: list[VTTEntry]) -> int:
        """Count unique speakers in VTT entries."""
        return len(set(entry.speaker for entry in entries))

    @staticmethod
    def total_duration(entries: list[VTTEntry]) -> float:
        """Calculate total duration from VTT entries."""
        if not entries:
            return 0.0
        return max(entry.end_time for entry in entries)

    @staticmethod
    def count_filler_words(text: str) -> int:
        """Count common filler words in text."""
        filler_words = ["um", "uh", "er", "ah", "like", "you know", "so", "well"]
        text_lower = text.lower()
        count = 0
        for filler in filler_words:
            count += text_lower.count(filler)
        return count

    @staticmethod
    def assert_vtt_entry_valid(entry: VTTEntry):
        """Assert that a VTT entry is valid."""
        assert entry.cue_id is not None
        assert entry.start_time >= 0
        assert entry.end_time > entry.start_time
        assert entry.speaker is not None
        assert entry.text is not None

    @staticmethod
    def assert_chunk_valid(chunk: VTTChunk):
        """Assert that a VTT chunk is valid."""
        assert chunk.chunk_id >= 0
        assert len(chunk.entries) > 0
        assert chunk.token_count > 0
        for entry in chunk.entries:
            VTTTestUtils.assert_vtt_entry_valid(entry)


@pytest.fixture
def vtt_test_utils() -> VTTTestUtils:
    """Provide VTT testing utilities."""
    return VTTTestUtils()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: mark test as slow")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "async_test: mark test as async test")


# Event loop fixture for async tests
@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
