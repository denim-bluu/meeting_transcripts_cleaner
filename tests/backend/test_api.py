"""Test the FastAPI backend endpoints."""

import os
import sys
from unittest.mock import Mock, patch
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

# Add backend_service to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend_service'))

from main import app


class TestHealthEndpoint:
    """Test the health check endpoint."""
    
    def setup_method(self):
        self.client = TestClient(app)
    
    def test_health_check_success(self):
        """Test health endpoint returns healthy status."""
        response = self.client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "meeting-transcript-api"
        assert "tasks_in_memory" in data
        assert "timestamp" in data


class TestTranscriptEndpoints:
    """Test transcript processing endpoints."""
    
    def setup_method(self):
        self.client = TestClient(app)
    
    def test_process_transcript_invalid_file_type(self):
        """Test processing non-VTT file returns error."""
        files = {"file": ("test.txt", BytesIO(b"not a vtt file"), "text/plain")}
        response = self.client.post("/api/v1/transcript/process", files=files)
        
        assert response.status_code == 400
        assert "Only VTT files are supported" in response.json()["detail"]
    
    def test_process_transcript_invalid_encoding(self):
        """Test processing file with invalid encoding returns error."""
        invalid_content = b'\xff\xfe\x00\x00'  # Invalid UTF-8
        files = {"file": ("test.vtt", BytesIO(invalid_content), "text/vtt")}
        response = self.client.post("/api/v1/transcript/process", files=files)
        
        assert response.status_code == 400
        assert "Invalid VTT file encoding" in response.json()["detail"]
    
    @patch('main.run_transcript_processing')
    def test_process_transcript_success(self, mock_process, sample_vtt_content):
        """Test successful VTT file processing."""
        files = {"file": ("test.vtt", BytesIO(sample_vtt_content.encode()), "text/vtt")}
        response = self.client.post("/api/v1/transcript/process", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "processing"
        assert data["message"] == "VTT file received, processing started"
        
        # Verify background task was scheduled
        mock_process.assert_called_once()


class TestIntelligenceEndpoints:
    """Test intelligence extraction endpoints."""
    
    def setup_method(self):
        self.client = TestClient(app)
    
    def test_extract_intelligence_missing_transcript_id(self):
        """Test intelligence extraction without transcript_id returns error."""
        response = self.client.post("/api/v1/intelligence/extract", json={})
        
        assert response.status_code == 400
        assert "transcript_id is required" in response.json()["detail"]
    
    def test_extract_intelligence_transcript_not_found(self):
        """Test intelligence extraction with non-existent transcript returns error."""
        data = {"transcript_id": "non-existent-id"}
        response = self.client.post("/api/v1/intelligence/extract", json=data)
        
        assert response.status_code == 404
        assert "Transcript not found" in response.json()["detail"]
    
    def test_extract_intelligence_transcript_not_completed(self):
        """Test intelligence extraction with incomplete transcript returns error."""
        # First create an incomplete task
        from main import tasks
        task_id = "test-transcript-id"
        tasks[task_id] = {"status": "processing", "type": "transcript_processing"}
        
        data = {"transcript_id": task_id}
        response = self.client.post("/api/v1/intelligence/extract", json=data)
        
        assert response.status_code == 400
        assert "Transcript processing not completed" in response.json()["detail"]
    
    @patch('main.run_intelligence_extraction')
    def test_extract_intelligence_success(self, mock_extract, mock_transcript_data):
        """Test successful intelligence extraction."""
        # Setup completed transcript task
        from main import tasks
        transcript_id = "test-transcript-id"
        tasks[transcript_id] = {
            "status": "completed",
            "type": "transcript_processing",
            "result": mock_transcript_data
        }
        
        data = {"transcript_id": transcript_id, "detail_level": "comprehensive"}
        response = self.client.post("/api/v1/intelligence/extract", json=data)
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "processing"
        assert data["detail_level"] == "comprehensive"
        
        # Verify background task was scheduled
        mock_extract.assert_called_once()


class TestTaskEndpoints:
    """Test task management endpoints."""
    
    def setup_method(self):
        self.client = TestClient(app)
    
    def test_get_task_status_not_found(self):
        """Test getting status of non-existent task returns error."""
        response = self.client.get("/api/v1/task/non-existent-id")
        
        assert response.status_code == 404
        assert "Task not found or expired" in response.json()["detail"]
    
    def test_get_task_status_success(self):
        """Test getting status of existing task."""
        from main import tasks
        from datetime import datetime
        
        task_id = "test-task-id"
        tasks[task_id] = {
            "type": "transcript_processing",
            "status": "processing",
            "progress": 0.5,
            "message": "Processing in progress",
            "created_at": datetime.now()
        }
        
        response = self.client.get(f"/api/v1/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["type"] == "transcript_processing"
        assert data["status"] == "processing"
        assert data["progress"] == 0.5
        assert data["message"] == "Processing in progress"
        assert "created_at" in data
    
    def test_get_task_status_completed_with_result(self):
        """Test getting status of completed task returns result."""
        from main import tasks
        from datetime import datetime
        
        task_id = "test-task-id"
        result_data = {"test": "data"}
        tasks[task_id] = {
            "type": "transcript_processing",
            "status": "completed",
            "progress": 1.0,
            "message": "Completed",
            "created_at": datetime.now(),
            "result": result_data
        }
        
        response = self.client.get(f"/api/v1/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"] == result_data
    
    def test_get_task_status_failed_with_error(self):
        """Test getting status of failed task returns error."""
        from main import tasks
        from datetime import datetime
        
        task_id = "test-task-id"
        tasks[task_id] = {
            "type": "transcript_processing",
            "status": "failed",
            "created_at": datetime.now(),
            "error": "Processing failed"
        }
        
        response = self.client.get(f"/api/v1/task/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Processing failed"
    
    def test_cancel_task_not_found(self):
        """Test cancelling non-existent task returns error."""
        response = self.client.delete("/api/v1/task/non-existent-id")
        
        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]
    
    def test_cancel_task_success(self):
        """Test successful task cancellation."""
        from main import tasks
        from datetime import datetime
        
        task_id = "test-task-id"
        tasks[task_id] = {
            "type": "transcript_processing",
            "status": "processing",
            "created_at": datetime.now()
        }
        
        response = self.client.delete(f"/api/v1/task/{task_id}")
        
        assert response.status_code == 200
        assert response.json()["message"] == "Task cancelled"
        
        # Verify task was removed
        assert task_id not in tasks


class TestTaskCleanup:
    """Test task cleanup functionality."""
    
    def setup_method(self):
        self.client = TestClient(app)
    
    def test_cleanup_old_tasks(self):
        """Test that old tasks are cleaned up automatically."""
        from main import tasks, cleanup_old_tasks
        from datetime import datetime, timedelta
        
        # Create old and new tasks
        old_task_id = "old-task"
        new_task_id = "new-task"
        
        old_time = datetime.now() - timedelta(hours=2)
        new_time = datetime.now()
        
        tasks[old_task_id] = {"created_at": old_time, "status": "completed"}
        tasks[new_task_id] = {"created_at": new_time, "status": "processing"}
        
        # Run cleanup
        cleanup_old_tasks()
        
        # Old task should be removed, new task should remain
        assert old_task_id not in tasks
        assert new_task_id in tasks
    
    def test_cleanup_on_task_status_check(self):
        """Test that cleanup runs when checking task status."""
        from main import tasks
        from datetime import datetime, timedelta
        
        # Create old task
        old_task_id = "old-task"
        old_time = datetime.now() - timedelta(hours=2)
        tasks[old_task_id] = {"created_at": old_time, "status": "completed"}
        
        # Check status of non-existent task (triggers cleanup)
        response = self.client.get("/api/v1/task/non-existent-id")
        assert response.status_code == 404
        
        # Old task should be cleaned up
        assert old_task_id not in tasks