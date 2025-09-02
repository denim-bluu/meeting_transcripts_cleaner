"""Integration tests for API client and frontend integration."""

import os
import sys
from unittest.mock import Mock, patch

import requests

# Add frontend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../frontend'))


class TestAPIClientIntegration:
    """Test API client integration with backend."""

    def setup_method(self):
        from api_client import BackendAPIClient
        self.api_client = BackendAPIClient("http://test-backend:8000")

    @patch('requests.Session.get')
    @patch('requests.Session.post')
    def test_complete_api_workflow_success(self, mock_post, mock_get, sample_vtt_content):
        """Test complete API workflow from upload to intelligence extraction."""
        # Mock transcript upload response
        upload_response = Mock()
        upload_response.status_code = 200
        upload_response.json.return_value = {"task_id": "transcript-task-123"}
        upload_response.raise_for_status.return_value = None

        # Mock intelligence extraction response
        intelligence_response = Mock()
        intelligence_response.status_code = 200
        intelligence_response.json.return_value = {"task_id": "intelligence-task-123"}
        intelligence_response.raise_for_status.return_value = None

        # Mock task status responses for polling
        transcript_status_responses = [
            {"status": "processing", "progress": 0.5, "message": "Processing transcript..."},
            {"status": "completed", "progress": 1.0, "message": "Transcript completed",
             "result": {"chunks": [{"text": "test"}], "stats": {"total_chunks": 1}}}
        ]

        intelligence_status_responses = [
            {"status": "processing", "progress": 0.3, "message": "Extracting insights..."},
            {"status": "processing", "progress": 0.7, "message": "Synthesizing intelligence..."},
            {"status": "completed", "progress": 1.0, "message": "Intelligence extraction completed",
             "result": {"summary": "Test summary", "action_items": []}}
        ]

        # Setup mock responses
        mock_post.side_effect = [upload_response, intelligence_response]

        status_responses = []
        for response_data in transcript_status_responses + intelligence_status_responses:
            status_response = Mock()
            status_response.status_code = 200
            status_response.json.return_value = response_data
            status_response.raise_for_status.return_value = None
            status_responses.append(status_response)

        mock_get.side_effect = status_responses

        # Test workflow
        with patch('time.sleep'):  # Speed up polling
            # Step 1: Upload and process transcript
            content_bytes = sample_vtt_content.encode('utf-8')
            success, task_id, message = self.api_client.upload_and_process_transcript(
                content_bytes, "test.vtt"
            )

            assert success is True
            assert task_id == "transcript-task-123"

            # Step 2: Poll until transcript processing completes
            success, transcript_result = self.api_client.poll_until_complete(
                task_id, poll_interval=0.1, timeout=5.0
            )

            assert success is True
            assert transcript_result["status"] == "completed"
            assert "result" in transcript_result

            # Step 3: Extract intelligence
            success, intel_task_id, message = self.api_client.extract_intelligence(
                task_id, "comprehensive"
            )

            assert success is True
            assert intel_task_id == "intelligence-task-123"

            # Step 4: Poll until intelligence extraction completes
            success, intelligence_result = self.api_client.poll_until_complete(
                intel_task_id, poll_interval=0.1, timeout=5.0
            )

            assert success is True
            assert intelligence_result["status"] == "completed"
            assert "result" in intelligence_result
            assert "summary" in intelligence_result["result"]

    @patch('requests.Session.get')
    @patch('requests.Session.post')
    def test_api_workflow_with_failures(self, mock_post, mock_get):
        """Test API workflow handles failures gracefully."""
        # Mock transcript upload failure
        mock_post.side_effect = requests.exceptions.HTTPError("Upload failed")

        content_bytes = b"test content"
        success, error_msg, message = self.api_client.upload_and_process_transcript(
            content_bytes, "test.vtt"
        )

        assert success is False
        assert "Upload failed" in error_msg

        # Mock intelligence extraction failure
        mock_post.side_effect = requests.exceptions.HTTPError("Extraction failed")

        success, error_msg, message = self.api_client.extract_intelligence(
            "transcript-123", "comprehensive"
        )

        assert success is False
        assert "Extraction failed" in error_msg

        # Mock task status failure
        mock_get.side_effect = requests.exceptions.HTTPError("Task not found")

        success, error_data = self.api_client.get_task_status("non-existent-task")

        assert success is False
        assert "error" in error_data


class TestStreamlitFrontendIntegration:
    """Test Streamlit frontend integration with backend API."""

    @patch('api_client.BackendAPIClient')
    def test_upload_page_integration(self, mock_api_client_class):
        """Test upload page integration with backend API."""
        # Mock API client
        mock_client = Mock()
        mock_api_client_class.return_value = mock_client

        # Mock successful health check
        mock_client.health_check.return_value = (True, {"status": "healthy"})

        # Mock successful upload
        mock_client.upload_and_process_transcript.return_value = (
            True, "transcript-task-123", "Upload successful"
        )

        # Mock successful polling
        mock_client.poll_until_complete.return_value = (
            True, {
                "status": "completed",
                "result": {
                    "chunks": [{"text": "Meeting content"}],
                    "stats": {"total_chunks": 1, "total_speakers": 2}
                }
            }
        )

        # Test API client integration

        # Verify health check works
        is_healthy, health_data = mock_client.health_check()
        assert is_healthy is True
        assert health_data["status"] == "healthy"

        # Verify upload works
        success, task_id, message = mock_client.upload_and_process_transcript(
            b"test content", "test.vtt"
        )
        assert success is True
        assert task_id == "transcript-task-123"

        # Verify polling works
        success, result = mock_client.poll_until_complete(task_id)
        assert success is True
        assert result["status"] == "completed"

    @patch('api_client.BackendAPIClient')
    def test_intelligence_page_integration(self, mock_api_client_class):
        """Test intelligence page integration with backend API."""
        # Mock API client
        mock_client = Mock()
        mock_api_client_class.return_value = mock_client

        # Mock successful intelligence extraction
        mock_client.extract_intelligence.return_value = (
            True, "intelligence-task-123", "Extraction started"
        )

        # Mock successful polling
        mock_client.poll_until_complete.return_value = (
            True, {
                "status": "completed",
                "result": {
                    "summary": "# Meeting Summary\n\nThis was a productive meeting.",
                    "action_items": [
                        {"description": "Follow up on project", "owner": "John", "due_date": "Friday"}
                    ],
                    "processing_stats": {"extraction_time": 5.2, "synthesis_time": 2.1}
                }
            }
        )

        # Test intelligence extraction workflow
        success, task_id, message = mock_client.extract_intelligence(
            "transcript-task-123", "comprehensive"
        )
        assert success is True
        assert task_id == "intelligence-task-123"

        # Test polling for results
        success, result = mock_client.poll_until_complete(task_id)
        assert success is True
        assert "summary" in result["result"]
        assert "action_items" in result["result"]
        assert len(result["result"]["action_items"]) > 0


class TestErrorHandlingIntegration:
    """Test error handling across the API client."""

    @patch('requests.Session.get')
    def test_api_client_network_error_handling(self, mock_get):
        """Test API client handles network errors gracefully."""
        from api_client import BackendAPIClient

        client = BackendAPIClient("http://unreachable-backend:8000")

        # Mock network error
        mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        # Test health check
        is_healthy, health_data = client.health_check()
        assert is_healthy is False
        assert "error" in health_data
        assert "Network unreachable" in health_data["error"]

        # Test task status check
        success, error_data = client.get_task_status("test-task")
        assert success is False
        assert "error" in error_data
