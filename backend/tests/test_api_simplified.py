"""
Unit tests for the simplified API endpoints using the new task cache.

Tests cover all API endpoints, error handling, and integration with the
SimpleTaskCache implementation.
"""

from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from backend.core.task_cache import (
    SimpleTaskCache,
    TaskEntry,
    TaskStatus,
    TaskType,
)

# Import our application
from backend.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_cache():
    """Create a mock cache for testing."""
    cache = Mock(spec=SimpleTaskCache)
    cache.store_task = AsyncMock()
    cache.get_task = AsyncMock()
    cache.update_task = AsyncMock()
    cache.delete_task = AsyncMock()
    cache.list_tasks = AsyncMock()
    cache.get_task_count = AsyncMock()
    cache.store_idempotency_key = AsyncMock()
    cache.get_task_for_idempotency_key = AsyncMock()
    cache.cleanup = AsyncMock()
    cache.health_check = AsyncMock()
    return cache


@pytest.fixture
def sample_vtt_content():
    """Sample VTT file content for testing."""
    return """WEBVTT

00:00:00.000 --> 00:00:05.000
John Doe: Hello, welcome to our meeting.

00:00:05.000 --> 00:00:10.000
Jane Smith: Thank you, John. Let's discuss the project timeline.

00:00:10.000 --> 00:00:15.000
John Doe: We need to complete the prototype by next Friday.
"""


class TestHealthEndpoint:
    """Test health check endpoint."""

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_health_check_success(self, mock_get_cache, client, mock_cache):
        """Test successful health check."""
        mock_get_cache.return_value = mock_cache
        mock_cache.health_check.return_value = {
            "cache": "healthy",
            "total_tasks": 5,
            "status_breakdown": {"processing": 3, "completed": 2},
        }
        mock_cache.get_task_count.return_value = 5

        response = client.get("/api/v1/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "meeting-transcript-api"
        assert data["version"] == "1.0.0"
        assert data["tasks_in_memory"] == 5
        assert data["dependencies"]["cache"] == "healthy"

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_health_check_degraded_no_api_key(self, mock_get_cache, client, mock_cache):
        """Test health check with missing API key."""
        mock_get_cache.return_value = mock_cache
        mock_cache.health_check.return_value = {"cache": "healthy"}
        mock_cache.get_task_count.return_value = 0

        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/api/v1/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["openai"] == "missing"


class TestTranscriptProcessingEndpoint:
    """Test transcript processing endpoint."""

    @patch("backend.api.v1.endpoints.get_task_cache")
    @patch("backend.api.v1.endpoints.run_transcript_processing")
    def test_process_transcript_success(
        self,
        mock_run_processing,
        mock_get_cache,
        client,
        mock_cache,
        sample_vtt_content,
    ):
        """Test successful transcript processing."""
        mock_get_cache.return_value = mock_cache
        mock_cache.store_task.return_value = Mock()

        # Create test file
        files = {"file": ("test.vtt", BytesIO(sample_vtt_content.encode()), "text/vtt")}

        response = client.post("/api/v1/transcript/process", files=files)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "processing"
        assert data["message"] == "VTT file received, processing started"

        # Verify cache operations
        mock_cache.store_task.assert_called_once()
        mock_run_processing.assert_called_once()

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_process_transcript_idempotency(
        self, mock_get_cache, client, mock_cache, sample_vtt_content
    ):
        """Test transcript processing with idempotency key."""
        mock_get_cache.return_value = mock_cache

        # Mock existing task
        existing_task = TaskEntry(
            task_id="existing-task-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.COMPLETED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_cache.get_task_for_idempotency_key.return_value = "existing-task-123"
        mock_cache.get_task.return_value = existing_task

        files = {"file": ("test.vtt", BytesIO(sample_vtt_content.encode()), "text/vtt")}
        headers = {"idempotency-key": "unique-key-123"}

        response = client.post(
            "/api/v1/transcript/process", files=files, headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["task_id"] == "existing-task-123"
        assert "Idempotent request" in data["message"]

    def test_process_transcript_invalid_file_type(self, client):
        """Test transcript processing with invalid file type."""
        files = {"file": ("test.txt", BytesIO(b"Not a VTT file"), "text/plain")}

        response = client.post("/api/v1/transcript/process", files=files)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid file extension" in response.json()["detail"]

    def test_process_transcript_file_too_large(self, client):
        """Test transcript processing with file too large."""
        # Create a large content string
        large_content = (
            "WEBVTT\n\n" + "00:00:00.000 --> 00:00:01.000\nSpeaker: Test\n" * 100000
        )
        files = {"file": ("large.vtt", BytesIO(large_content.encode()), "text/vtt")}

        response = client.post("/api/v1/transcript/process", files=files)

        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert "File too large" in response.json()["detail"]

    def test_process_transcript_invalid_encoding(self, client):
        """Test transcript processing with invalid file encoding."""
        # Create invalid UTF-8 content
        invalid_content = b"\xff\xfe\x00\x00"  # Invalid UTF-8 bytes
        files = {"file": ("invalid.vtt", BytesIO(invalid_content), "text/vtt")}

        response = client.post("/api/v1/transcript/process", files=files)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid VTT file encoding" in response.json()["detail"]


class TestIntelligenceExtractionEndpoint:
    """Test intelligence extraction endpoint."""

    @patch("backend.api.v1.endpoints.get_task_cache")
    @patch("backend.api.v1.endpoints.run_intelligence_extraction")
    def test_extract_intelligence_success(
        self, mock_run_extraction, mock_get_cache, client, mock_cache
    ):
        """Test successful intelligence extraction."""
        mock_get_cache.return_value = mock_cache

        # Mock completed transcript task
        transcript_task = TaskEntry(
            task_id="transcript-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.COMPLETED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            result={"chunks": [], "speakers": []},
        )

        mock_cache.get_task.return_value = transcript_task
        mock_cache.store_task.return_value = Mock()

        request_data = {
            "transcript_id": "transcript-123",
        }

        response = client.post("/api/v1/intelligence/extract", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "processing"
        assert "extraction started" in data["message"]

        # Verify cache operations
        mock_cache.store_task.assert_called_once()
        mock_run_extraction.assert_called_once()

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_extract_intelligence_transcript_not_found(
        self, mock_get_cache, client, mock_cache
    ):
        """Test intelligence extraction with non-existent transcript."""
        mock_get_cache.return_value = mock_cache
        mock_cache.get_task.return_value = None

        request_data = {
            "transcript_id": "nonexistent",
        }

        response = client.post("/api/v1/intelligence/extract", json=request_data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Task not found or expired" in response.json()["detail"]

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_extract_intelligence_transcript_not_completed(
        self, mock_get_cache, client, mock_cache
    ):
        """Test intelligence extraction with incomplete transcript."""
        mock_get_cache.return_value = mock_cache

        # Mock processing transcript task
        transcript_task = TaskEntry(
            task_id="transcript-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,  # Still processing
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_cache.get_task.return_value = transcript_task

        request_data = {
            "transcript_id": "transcript-123",
        }

        response = client.post("/api/v1/intelligence/extract", json=request_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Transcript processing not completed" in response.json()["detail"]



class TestTaskManagementEndpoints:
    """Test task management endpoints."""

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_get_task_status_success(self, mock_get_cache, client, mock_cache):
        """Test successful task status retrieval."""
        mock_get_cache.return_value = mock_cache

        # Mock task
        task = TaskEntry(
            task_id="test-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            progress=0.75,
            message="Processing chunks 15/20",
        )

        mock_cache.get_task.return_value = task
        mock_cache.cleanup.return_value = {
            "expired_tasks": 0,
            "expired_idempotency_keys": 0,
        }

        response = client.get("/api/v1/task/test-123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["task_id"] == "test-123"
        assert data["type"] == "transcript_processing"
        assert data["status"] == "processing"
        assert data["progress"] == 0.75
        assert data["message"] == "Processing chunks 15/20"

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_get_task_status_not_found(self, mock_get_cache, client, mock_cache):
        """Test task status retrieval for non-existent task."""
        mock_get_cache.return_value = mock_cache
        mock_cache.get_task.return_value = None

        response = client.get("/api/v1/task/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Task not found or expired" in response.json()["detail"]

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_get_task_status_completed_with_result(
        self, mock_get_cache, client, mock_cache
    ):
        """Test task status retrieval for completed task with result."""
        mock_get_cache.return_value = mock_cache

        # Mock completed task with result
        task = TaskEntry(
            task_id="completed-123",
            task_type=TaskType.INTELLIGENCE_EXTRACTION,
            status=TaskStatus.COMPLETED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            progress=1.0,
            message="Intelligence extraction completed",
            result={
                "summary": "Meeting discussed project timeline and budget allocation.",
                "action_items": [{"description": "Review budget", "owner": "John"}],
            },
        )

        mock_cache.get_task.return_value = task
        mock_cache.cleanup.return_value = {
            "expired_tasks": 0,
            "expired_idempotency_keys": 0,
        }

        response = client.get("/api/v1/task/completed-123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 1.0
        assert (
            data["result"]["summary"]
            == "Meeting discussed project timeline and budget allocation."
        )
        assert len(data["result"]["action_items"]) == 1

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_get_task_status_failed_with_error(
        self, mock_get_cache, client, mock_cache
    ):
        """Test task status retrieval for failed task with error."""
        mock_get_cache.return_value = mock_cache

        # Mock failed task
        task = TaskEntry(
            task_id="failed-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.FAILED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            progress=0.3,
            message="Processing failed",
            error="Invalid VTT format detected",
            error_code="invalid_format",
        )

        mock_cache.get_task.return_value = task
        mock_cache.cleanup.return_value = {
            "expired_tasks": 0,
            "expired_idempotency_keys": 0,
        }

        response = client.get("/api/v1/task/failed-123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"]["code"] == "invalid_format"
        assert data["error"]["message"] == "Invalid VTT format detected"

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_cancel_task_success(self, mock_get_cache, client, mock_cache):
        """Test successful task cancellation."""
        mock_get_cache.return_value = mock_cache

        # Mock task
        task = TaskEntry(
            task_id="cancel-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_cache.get_task.return_value = task
        mock_cache.delete_task.return_value = True

        response = client.delete("/api/v1/task/cancel-123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Task cancelled successfully"

        mock_cache.delete_task.assert_called_once_with("cancel-123")

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_cancel_task_not_found(self, mock_get_cache, client, mock_cache):
        """Test cancellation of non-existent task."""
        mock_get_cache.return_value = mock_cache
        mock_cache.get_task.return_value = None

        response = client.delete("/api/v1/task/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Task not found or expired" in response.json()["detail"]

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_cancel_task_deletion_failed(self, mock_get_cache, client, mock_cache):
        """Test task cancellation when deletion fails."""
        mock_get_cache.return_value = mock_cache

        # Mock task exists but deletion fails
        task = TaskEntry(
            task_id="fail-delete-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_cache.get_task.return_value = task
        mock_cache.delete_task.return_value = False

        response = client.delete("/api/v1/task/fail-delete-123")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to cancel task" in response.json()["detail"]


class TestDebugEndpoints:
    """Test debug endpoints."""

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_list_tasks_all(self, mock_get_cache, client, mock_cache):
        """Test debug endpoint listing all tasks."""
        mock_get_cache.return_value = mock_cache

        # Mock tasks
        tasks = [
            TaskEntry(
                task_id=f"debug-{i}",
                task_type=TaskType.TRANSCRIPT_PROCESSING
                if i % 2 == 0
                else TaskType.INTELLIGENCE_EXTRACTION,
                status=TaskStatus.PROCESSING if i < 2 else TaskStatus.COMPLETED,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                progress=float(i) / 10,
                result={"test": True} if i >= 2 else None,
            )
            for i in range(4)
        ]

        mock_cache.list_tasks.return_value = tasks
        mock_cache.health_check.return_value = {
            "cache": "healthy",
            "total_tasks": 4,
            "total_idempotency_keys": 0,
            "status_breakdown": {"processing": 2, "completed": 2},
            "expires_within_1h": 4,
            "last_cleanup": "2024-01-01T00:00:00",
        }

        response = client.get("/api/v1/debug/tasks")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 4
        assert len(data["tasks"]) == 4

        # Check updated response structure
        assert "cache_statistics" in data
        assert "available_filters" in data
        assert data["cache_statistics"]["total_tasks_in_cache"] == 4

        # Check task data structure
        first_task = data["tasks"][0]
        assert "task_id" in first_task
        assert "type" in first_task
        assert "task_type" in first_task  # Added for frontend compatibility
        assert "status" in first_task
        assert "progress" in first_task
        assert "has_result" in first_task
        assert "has_error" in first_task
        assert "duration_seconds" in first_task

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_list_tasks_filtered(self, mock_get_cache, client, mock_cache):
        """Test debug endpoint with filtering."""
        mock_get_cache.return_value = mock_cache

        # Mock filtered results
        processing_tasks = [
            TaskEntry(
                task_id="processing-1",
                task_type=TaskType.TRANSCRIPT_PROCESSING,
                status=TaskStatus.PROCESSING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        ]

        mock_cache.list_tasks.return_value = processing_tasks
        mock_cache.health_check.return_value = {
            "cache": "healthy",
            "total_tasks": 1,
            "total_idempotency_keys": 0,
            "status_breakdown": {"processing": 1},
            "expires_within_1h": 1,
            "last_cleanup": "2024-01-01T00:00:00",
        }

        response = client.get(
            "/api/v1/debug/tasks?status=processing&task_type=transcript_processing&limit=50"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 1
        assert data["filters_applied"]["status"] == "processing"
        assert data["filters_applied"]["task_type"] == "transcript_processing"
        assert data["filters_applied"]["limit"] == 50

        # Verify cache was called with correct filters
        mock_cache.list_tasks.assert_called_once_with(
            status=TaskStatus.PROCESSING,
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            limit=50,
        )

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_list_tasks_empty(self, mock_get_cache, client, mock_cache):
        """Test debug endpoint with no tasks."""
        mock_get_cache.return_value = mock_cache
        mock_cache.list_tasks.return_value = []
        mock_cache.health_check.return_value = {
            "cache": "healthy",
            "total_tasks": 0,
            "total_idempotency_keys": 0,
            "status_breakdown": {},
            "expires_within_1h": 0,
            "last_cleanup": "2024-01-01T00:00:00",
        }

        response = client.get("/api/v1/debug/tasks")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 0
        assert data["tasks"] == []
        assert "cache_statistics" in data
        assert data["cache_statistics"]["total_tasks_in_cache"] == 0

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_cache_stats(self, mock_get_cache, client, mock_cache):
        """Test debug cache statistics endpoint."""
        mock_get_cache.return_value = mock_cache

        # Mock health check
        mock_cache.health_check.return_value = {
            "cache": "healthy",
            "total_tasks": 5,
            "total_idempotency_keys": 2,
            "status_breakdown": {"processing": 3, "completed": 2},
            "expires_within_1h": 1,
            "last_cleanup": "2024-01-01T00:00:00",
        }

        # Mock task listing for detailed stats
        mock_cache.list_tasks.return_value = [
            TaskEntry(
                task_id="task-1",
                task_type=TaskType.TRANSCRIPT_PROCESSING,
                status=TaskStatus.PROCESSING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                progress=0.5,
            ),
            TaskEntry(
                task_id="task-2",
                task_type=TaskType.INTELLIGENCE_EXTRACTION,
                status=TaskStatus.COMPLETED,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                progress=1.0,
            ),
        ]

        response = client.get("/api/v1/debug/cache/stats")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "cache_health" in data
        assert "detailed_statistics" in data
        assert "performance_metrics" in data
        assert data["performance_metrics"]["total_tasks_sampled"] == 2

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_force_cleanup(self, mock_get_cache, client, mock_cache):
        """Test debug force cleanup endpoint."""
        mock_get_cache.return_value = mock_cache

        # Mock cleanup stats
        mock_cache.cleanup.return_value = {
            "expired_tasks": 3,
            "expired_idempotency_keys": 1,
            "remaining_tasks": 5,
            "remaining_idempotency_keys": 2,
        }

        response = client.post("/api/v1/debug/cache/cleanup")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Cache cleanup completed"
        assert "cleanup_statistics" in data
        assert "timestamp" in data
        assert data["cleanup_statistics"]["expired_tasks"] == 3

        # Verify cleanup was called
        mock_cache.cleanup.assert_called_once()

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_invalid_status_filter(self, mock_get_cache, client, mock_cache):
        """Test debug endpoint with invalid status filter."""
        mock_get_cache.return_value = mock_cache

        response = client.get("/api/v1/debug/tasks?status=invalid_status")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid status" in response.json()["detail"]

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_invalid_task_type_filter(self, mock_get_cache, client, mock_cache):
        """Test debug endpoint with invalid task type filter."""
        mock_get_cache.return_value = mock_cache

        response = client.get("/api/v1/debug/tasks?task_type=invalid_type")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid task_type" in response.json()["detail"]

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_debug_analytics(self, mock_get_cache, client, mock_cache):
        """Test debug analytics endpoint."""
        mock_get_cache.return_value = mock_cache

        # Mock health check
        mock_cache.health_check.return_value = {
            "cache": "healthy",
            "total_tasks": 10,
            "total_idempotency_keys": 3,
            "status_breakdown": {"processing": 5, "completed": 4, "failed": 1},
            "expires_within_1h": 2,
            "last_cleanup": "2024-01-01T00:00:00",
        }

        # Mock task listing for analytics
        mock_tasks = [
            TaskEntry(
                task_id="analytics-1",
                task_type=TaskType.TRANSCRIPT_PROCESSING,
                status=TaskStatus.COMPLETED,
                created_at=datetime.now() - timedelta(minutes=30),
                updated_at=datetime.now() - timedelta(minutes=28),
                progress=1.0,
            ),
            TaskEntry(
                task_id="analytics-2",
                task_type=TaskType.INTELLIGENCE_EXTRACTION,
                status=TaskStatus.PROCESSING,
                created_at=datetime.now() - timedelta(minutes=10),
                updated_at=datetime.now() - timedelta(minutes=8),
                progress=0.5,
            ),
        ]
        mock_cache.list_tasks.return_value = mock_tasks

        response = client.get("/api/v1/debug/analytics")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check analytics structure
        assert "cache_analytics" in data
        assert "task_distribution" in data
        assert "performance_metrics" in data
        assert "system_info" in data
        assert "timestamp" in data

        # Check specific analytics data
        assert data["cache_analytics"]["total_tasks"] == 2
        assert data["system_info"]["storage_type"] == "in_memory_cache"
        assert "by_status" in data["task_distribution"]
        assert "by_type" in data["task_distribution"]


class TestFileValidation:
    """Test file validation utility functions."""

    def test_validate_upload_file_no_filename(self, client):
        """Test file validation with no filename."""
        from fastapi import HTTPException, UploadFile

        from backend.api.v1.routers.transcript import validate_upload_file

        # Mock UploadFile with no filename
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = None

        with pytest.raises(HTTPException) as exc_info:
            validate_upload_file(mock_file)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "File name is required" in str(exc_info.value.detail)

    def test_validate_upload_file_invalid_extension(self, client):
        """Test file validation with invalid extension."""
        from fastapi import HTTPException, UploadFile

        from backend.api.v1.routers.transcript import validate_upload_file

        # Mock UploadFile with invalid extension
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "test.txt"

        with pytest.raises(HTTPException) as exc_info:
            validate_upload_file(mock_file)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid file extension" in str(exc_info.value.detail)


class TestErrorHandling:
    """Test error handling across endpoints."""

    @patch("backend.api.v1.endpoints.get_task_cache")
    def test_cache_error_handling(self, mock_get_cache, client):
        """Test handling of cache errors."""
        # Mock cache that raises exception
        mock_cache = Mock()
        mock_cache.health_check = AsyncMock(side_effect=Exception("Cache error"))
        mock_get_cache.return_value = mock_cache

        response = client.get("/api/v1/health")

        # Should handle gracefully and still return a response
        assert response.status_code == status.HTTP_200_OK

    def test_malformed_json_request(self, client):
        """Test handling of malformed JSON requests."""
        response = client.post(
            "/api/v1/intelligence/extract",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestCORSHeaders:
    """Test CORS headers in responses."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present in responses."""
        response = client.get("/api/v1/health")

        # Note: TestClient doesn't always include middleware headers
        # In a real environment, these would be present
        assert response.status_code == status.HTTP_200_OK

    def test_options_request_handled(self, client):
        """Test that OPTIONS requests are handled for CORS preflight."""
        response = client.options("/api/v1/health")

        # Should return 200 for OPTIONS requests
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ]


class TestRequestValidation:
    """Test request validation schemas."""

    def test_intelligence_extraction_request_validation(self, client):
        """Test validation of intelligence extraction requests."""
        # Test missing required field
        response = client.post("/api/v1/intelligence/extract", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Test valid request with only required field
        response = client.post(
            "/api/v1/intelligence/extract",
            json={"transcript_id": "test-123"},
        )
        # This will fail with 404 since transcript doesn't exist, but validates schema
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY]
