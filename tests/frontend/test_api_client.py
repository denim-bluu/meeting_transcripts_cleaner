"""Test the frontend API client."""

import os
import sys
from unittest.mock import Mock, patch
import time

import pytest
import requests

# Add frontend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../frontend'))

from api_client import BackendAPIClient


class TestBackendAPIClient:
    """Test the BackendAPIClient class."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    def test_init_with_base_url(self):
        """Test client initialization with custom base URL."""
        client = BackendAPIClient("http://custom-backend:9000")
        assert client.base_url == "http://custom-backend:9000"
    
    def test_init_with_env_var(self):
        """Test client initialization using environment variable."""
        with patch.dict(os.environ, {"BACKEND_URL": "http://env-backend:8000"}):
            client = BackendAPIClient()
            assert client.base_url == "http://env-backend:8000"
    
    def test_init_default_url(self):
        """Test client initialization with default URL."""
        with patch.dict(os.environ, {}, clear=True):
            client = BackendAPIClient()
            assert client.base_url == "http://localhost:8000"


class TestHealthCheck:
    """Test health check functionality."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    @patch('requests.Session.get')
    def test_health_check_success(self, mock_get):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "service": "test"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        is_healthy, health_data = self.client.health_check()
        
        assert is_healthy is True
        assert health_data["status"] == "healthy"
        assert health_data["service"] == "test"
        mock_get.assert_called_once_with("http://test-backend:8000/api/v1/health", timeout=5)
    
    @patch('requests.Session.get')
    def test_health_check_failure(self, mock_get):
        """Test health check with backend failure."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Backend unavailable")
        
        is_healthy, health_data = self.client.health_check()
        
        assert is_healthy is False
        assert "error" in health_data
        assert "Backend unavailable" in health_data["error"]


class TestTranscriptUpload:
    """Test transcript upload functionality."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    @patch('requests.Session.post')
    def test_upload_transcript_success(self, mock_post, sample_vtt_content):
        """Test successful VTT upload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"task_id": "test-task-123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        content_bytes = sample_vtt_content.encode('utf-8')
        success, task_id, message = self.client.upload_and_process_transcript(
            content_bytes, "test.vtt"
        )
        
        assert success is True
        assert task_id == "test-task-123"
        assert "successful" in message
        
        # Verify the POST request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://test-backend:8000/api/v1/transcript/process"
        assert call_args[1]["timeout"] == 30
        
        # Verify file was sent correctly
        files = call_args[1]["files"]
        assert "file" in files
        assert files["file"][0] == "test.vtt"
        assert files["file"][1] == content_bytes
        assert files["file"][2] == "text/vtt"
    
    @patch('requests.Session.post')
    def test_upload_transcript_failure(self, mock_post):
        """Test VTT upload with backend error."""
        mock_post.side_effect = requests.exceptions.HTTPError("Upload failed")
        
        success, error_msg, message = self.client.upload_and_process_transcript(
            b"test content", "test.vtt"
        )
        
        assert success is False
        assert "Upload failed" in error_msg
        assert "Upload failed" in message


class TestIntelligenceExtraction:
    """Test intelligence extraction functionality."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    @patch('requests.Session.post')
    def test_extract_intelligence_success(self, mock_post):
        """Test successful intelligence extraction."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"task_id": "intel-task-123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        success, task_id, message = self.client.extract_intelligence(
            "transcript-123", "comprehensive"
        )
        
        assert success is True
        assert task_id == "intel-task-123"
        assert "comprehensive" in message
        
        # Verify the POST request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://test-backend:8000/api/v1/intelligence/extract"
        
        # Verify JSON payload
        json_data = call_args[1]["json"]
        assert json_data["transcript_id"] == "transcript-123"
        assert json_data["detail_level"] == "comprehensive"
    
    @patch('requests.Session.post')
    def test_extract_intelligence_failure(self, mock_post):
        """Test intelligence extraction with backend error."""
        mock_post.side_effect = requests.exceptions.HTTPError("Extraction failed")
        
        success, error_msg, message = self.client.extract_intelligence(
            "transcript-123", "comprehensive"
        )
        
        assert success is False
        assert "Extraction failed" in error_msg
        assert "Intelligence extraction failed" in message


class TestTaskStatusChecking:
    """Test task status checking functionality."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    @patch('requests.Session.get')
    def test_get_task_status_success(self, mock_get):
        """Test successful task status retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task_id": "test-task-123",
            "status": "processing",
            "progress": 0.75,
            "message": "Processing chunks..."
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        success, task_data = self.client.get_task_status("test-task-123")
        
        assert success is True
        assert task_data["task_id"] == "test-task-123"
        assert task_data["status"] == "processing"
        assert task_data["progress"] == 0.75
        assert task_data["message"] == "Processing chunks..."
        
        mock_get.assert_called_once_with(
            "http://test-backend:8000/api/v1/task/test-task-123",
            timeout=10
        )
    
    @patch('requests.Session.get')
    def test_get_task_status_failure(self, mock_get):
        """Test task status retrieval with backend error."""
        mock_get.side_effect = requests.exceptions.HTTPError("Task not found")
        
        success, error_data = self.client.get_task_status("non-existent-task")
        
        assert success is False
        assert "error" in error_data
        assert "Task not found" in error_data["error"]


class TestTaskCancellation:
    """Test task cancellation functionality."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    @patch('requests.Session.delete')
    def test_cancel_task_success(self, mock_delete):
        """Test successful task cancellation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_delete.return_value = mock_response
        
        success, message = self.client.cancel_task("test-task-123")
        
        assert success is True
        assert "cancelled successfully" in message
        
        mock_delete.assert_called_once_with(
            "http://test-backend:8000/api/v1/task/test-task-123",
            timeout=10
        )
    
    @patch('requests.Session.delete')
    def test_cancel_task_failure(self, mock_delete):
        """Test task cancellation with backend error."""
        mock_delete.side_effect = requests.exceptions.HTTPError("Cancellation failed")
        
        success, error_msg = self.client.cancel_task("test-task-123")
        
        assert success is False
        assert "Failed to cancel task" in error_msg


class TestPollingUntilComplete:
    """Test polling functionality."""
    
    def setup_method(self):
        self.client = BackendAPIClient("http://test-backend:8000")
    
    @patch('requests.Session.get')
    @patch('time.sleep')  # Mock sleep to speed up tests
    def test_poll_until_complete_success(self, mock_sleep, mock_get):
        """Test polling until task completion."""
        # Mock sequence: processing -> processing -> completed
        responses = [
            {"status": "processing", "progress": 0.3, "message": "Starting..."},
            {"status": "processing", "progress": 0.7, "message": "Almost done..."},
            {"status": "completed", "progress": 1.0, "message": "Done!", "result": {"data": "test"}}
        ]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = responses
        mock_get.return_value = mock_response
        
        # Mock progress callback
        progress_callback = Mock()
        
        success, final_data = self.client.poll_until_complete(
            "test-task-123",
            progress_callback=progress_callback,
            poll_interval=0.1,  # Fast polling for test
            timeout=10.0
        )
        
        assert success is True
        assert final_data["status"] == "completed"
        assert final_data["result"]["data"] == "test"
        
        # Verify progress callback was called
        assert progress_callback.call_count == 3
        progress_callback.assert_any_call(0.3, "Starting...")
        progress_callback.assert_any_call(0.7, "Almost done...")
        progress_callback.assert_any_call(1.0, "Done!")
    
    @patch('requests.Session.get')
    @patch('time.sleep')
    def test_poll_until_complete_failure(self, mock_sleep, mock_get):
        """Test polling when task fails."""
        # Mock sequence: processing -> failed
        responses = [
            {"status": "processing", "progress": 0.5, "message": "Processing..."},
            {"status": "failed", "progress": 0.5, "message": "Failed", "error": "Something went wrong"}
        ]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = responses
        mock_get.return_value = mock_response
        
        success, final_data = self.client.poll_until_complete(
            "test-task-123",
            poll_interval=0.1,
            timeout=10.0
        )
        
        assert success is False
        assert final_data["status"] == "failed"
        assert final_data["error"] == "Something went wrong"
    
    @patch('requests.Session.get')
    @patch('time.sleep')
    @patch('time.time')
    def test_poll_until_complete_timeout(self, mock_time, mock_sleep, mock_get):
        """Test polling timeout."""
        # Mock time to simulate timeout
        mock_time.side_effect = [0, 5, 10, 15]  # Simulate time progression past timeout
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"status": "processing", "progress": 0.5}
        mock_get.return_value = mock_response
        
        success, final_data = self.client.poll_until_complete(
            "test-task-123",
            poll_interval=0.1,
            timeout=10.0
        )
        
        assert success is False
        assert "timeout" in final_data["error"]
    
    @patch('requests.Session.get')
    def test_poll_until_complete_api_error(self, mock_get):
        """Test polling when API request fails."""
        mock_get.side_effect = requests.exceptions.ConnectionError("API unavailable")
        
        success, error_data = self.client.poll_until_complete(
            "test-task-123",
            timeout=1.0
        )
        
        assert success is False
        assert "error" in error_data