"""
API client for communicating with the FastAPI backend.

Handles all HTTP communication, error handling, and provides
simple methods for the Streamlit frontend to use.
"""

import os
import time
from typing import Any

import requests
import structlog

logger = structlog.get_logger(__name__)


class BackendAPIClient:
    """Simple HTTP client for the FastAPI backend."""

    def __init__(self, base_url: str | None = None):
        """Initialize the API client.

        Args:
            base_url: Backend URL. If None, reads from BACKEND_URL env var.
        """
        self.base_url = base_url or os.getenv("BACKEND_URL", "http://localhost:8000")
        self.session = requests.Session()

        logger.info("API client initialized", base_url=self.base_url)

    def _make_request(
        self, method: str, endpoint: str, **kwargs
    ) -> dict[str, Any] | None:
        """Generic request method for debug endpoints.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without /api/v1 prefix)
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON data or None if failed
        """
        try:
            url = f"{self.base_url}/api/v1{endpoint}"
            response = self.session.request(method, url, timeout=10, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(
                "API request failed", method=method, endpoint=endpoint, error=str(e)
            )
            return None

    def health_check(self) -> tuple[bool, dict[str, Any]]:
        """Check if backend is healthy.

        Returns:
            (is_healthy, health_data)
        """
        try:
            response = self.session.get(f"{self.base_url}/api/v1/health", timeout=5)
            response.raise_for_status()
            return True, response.json()
        except Exception as e:
            logger.warning("Backend health check failed", error=str(e))
            return False, {"error": str(e)}

    def upload_and_process_transcript(
        self, file_content: bytes, filename: str
    ) -> tuple[bool, str, str]:
        """Upload VTT file and start processing.

        Args:
            file_content: VTT file content as bytes
            filename: Original filename

        Returns:
            (success, task_id_or_error, message)
        """
        try:
            files = {"file": (filename, file_content, "text/vtt")}
            headers = {}

            logger.info(
                "Uploading VTT file", filename=filename, size_bytes=len(file_content)
            )

            response = self.session.post(
                f"{self.base_url}/api/v1/transcript/process",
                files=files,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()
            task_id = data["task_id"]

            logger.info("VTT upload successful", task_id=task_id)
            return True, task_id, "Upload successful, processing started"

        except requests.exceptions.RequestException as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error("VTT upload failed", error=str(e))
            return False, error_msg, error_msg

    def extract_intelligence(
        self,
        transcript_id: str,
        detail_level: str = "comprehensive",
    ) -> tuple[bool, str, str]:
        """Start intelligence extraction.

        Args:
            transcript_id: Task ID from completed transcript processing
            detail_level: One of "comprehensive", "standard", "technical_focus"

        Returns:
            (success, task_id_or_error, message)
        """
        try:
            data = {"transcript_id": transcript_id, "detail_level": detail_level}

            logger.info(
                "Starting intelligence extraction",
                transcript_id=transcript_id,
                detail_level=detail_level,
            )

            headers = {"Content-Type": "application/json"}

            response = self.session.post(
                f"{self.base_url}/api/v1/intelligence/extract",
                json=data,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            result = response.json()
            task_id = result["task_id"]

            logger.info("Intelligence extraction started", task_id=task_id)
            return (
                True,
                task_id,
                f"Intelligence extraction started with {detail_level} detail level",
            )

        except requests.exceptions.RequestException as e:
            error_msg = f"Intelligence extraction failed: {str(e)}"
            logger.error("Intelligence extraction failed", error=str(e))
            return False, error_msg, error_msg

    def get_task_status(self, task_id: str) -> tuple[bool, dict[str, Any]]:
        """Get current task status and results.

        Args:
            task_id: Task ID to check

        Returns:
            (success, task_data)
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/task/{task_id}", timeout=10
            )
            response.raise_for_status()

            data = response.json()
            return True, data

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to get task status: {str(e)}"
            logger.error("Task status check failed", task_id=task_id, error=str(e))
            return False, {"error": error_msg}

    def cancel_task(self, task_id: str) -> tuple[bool, str]:
        """Cancel a running task.

        Args:
            task_id: Task ID to cancel

        Returns:
            (success, message)
        """
        try:
            response = self.session.delete(
                f"{self.base_url}/api/v1/task/{task_id}", timeout=10
            )
            response.raise_for_status()

            return True, "Task cancelled successfully"

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to cancel task: {str(e)}"
            logger.error("Task cancellation failed", task_id=task_id, error=str(e))
            return False, error_msg

    def poll_until_complete(
        self,
        task_id: str,
        progress_callback=None,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> tuple[bool, dict[str, Any]]:
        """Poll task until completion or timeout.

        Args:
            task_id: Task ID to poll
            progress_callback: Function called with (progress, message) on updates
            poll_interval: Seconds between polls
            timeout: Maximum seconds to wait

        Returns:
            (success, final_task_data)
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            success, task_data = self.get_task_status(task_id)

            if not success:
                return False, task_data

            # Call progress callback if provided
            if progress_callback:
                progress = task_data.get("progress", 0)
                message = task_data.get("message", "Processing...")
                progress_callback(progress, message)

            status = task_data.get("status")

            if status == "completed":
                logger.info("Task completed successfully", task_id=task_id)
                return True, task_data
            elif status == "failed":
                error = task_data.get("error", "Unknown error")
                logger.error("Task failed", task_id=task_id, error=error)
                return False, task_data

            # Sleep before next poll
            time.sleep(poll_interval)

        # Timeout reached
        logger.warning("Task polling timeout", task_id=task_id, timeout=timeout)
        return False, {"error": f"Task timeout after {timeout} seconds"}


# Global client instance
api_client = BackendAPIClient()
