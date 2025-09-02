"""Shared test configuration and fixtures for all tests."""

from collections.abc import Generator
import os
import tempfile
from unittest.mock import Mock

import pytest
import requests

# Mock environment variables for testing
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["BACKEND_URL"] = "http://localhost:8000"

@pytest.fixture
def sample_vtt_content() -> str:
    """Sample VTT content for testing."""
    return """WEBVTT

1
00:00:00.000 --> 00:00:05.000
<v John>Hello everyone, let's start the meeting.

2
00:00:05.000 --> 00:00:10.000
<v Sarah>Thanks John. I have the budget proposal ready.

3
00:00:10.000 --> 00:00:15.000
<v Mike>Great, I reviewed the technical requirements.
"""

@pytest.fixture
def sample_vtt_file(sample_vtt_content: str) -> Generator[str, None, None]:
    """Create a temporary VTT file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.vtt', delete=False) as f:
        f.write(sample_vtt_content)
        f.flush()
        yield f.name
    os.unlink(f.name)

@pytest.fixture
def mock_transcript_data() -> dict:
    """Mock processed transcript data."""
    return {
        "entries": [
            {"cue_id": "1", "start_time": 0.0, "end_time": 5.0, "speaker": "John", "text": "Hello everyone"},
            {"cue_id": "2", "start_time": 5.0, "end_time": 10.0, "speaker": "Sarah", "text": "Thanks John"}
        ],
        "chunks": [
            {"chunk_id": 0, "entries": [], "token_count": 50}
        ],
        "speakers": ["John", "Sarah"],
        "duration": 10.0
    }

@pytest.fixture
def mock_intelligence_data() -> dict:
    """Mock intelligence extraction result."""
    return {
        "summary": "# Meeting Summary\n\nThis was a test meeting with budget discussions.",
        "action_items": [
            {"description": "Review budget proposal", "owner": "John", "due_date": "Friday"}
        ],
        "processing_stats": {
            "vtt_chunks": 1,
            "semantic_chunks": 1,
            "api_calls": 2,
            "time_ms": 5000
        }
    }

@pytest.fixture
def mock_requests() -> Mock:
    """Mock requests session for API testing."""
    mock_session = Mock(spec=requests.Session)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "healthy"}
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_session.post.return_value = mock_response
    mock_session.delete.return_value = mock_response
    return mock_session
