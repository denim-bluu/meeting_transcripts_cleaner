"""Centralized backend API communication service."""

import os
import requests
import streamlit as st
from typing import Dict, Any, Optional, Tuple
from utils.constants import API_ENDPOINTS, TIMEOUTS, HTTP_STATUS

class BackendService:
    """Handles all backend API communication with consistent patterns."""
    
    def __init__(self, base_url: Optional[str] = None):
        # Use environment variable first, then default
        if base_url is None:
            base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.base_url = base_url.rstrip('/')
        
    def check_health(self) -> Tuple[bool, Dict[str, Any]]:
        """Check backend health status.
        
        Logic:
        1. Make health check request with timeout
        2. Parse response for service status
        3. Return success flag and health data
        
        Returns: (is_healthy, health_data)
        """
        try:
            response = requests.get(
                f"{self.base_url}{API_ENDPOINTS.HEALTH}",
                timeout=TIMEOUTS.HEALTH_CHECK
            )
            if response.status_code == HTTP_STATUS.OK:
                data = response.json()
                return data.get("status") == "healthy", data
            return False, {"error": f"HTTP {response.status_code}"}
        except requests.RequestException as e:
            return False, {"error": str(e)}
    
    def upload_file(self, file_content: bytes, filename: str) -> Tuple[bool, Dict[str, Any]]:
        """Upload VTT file for processing.
        
        Logic:
        1. Prepare multipart file upload
        2. Post to transcript processing endpoint
        3. Extract task_id from response
        4. Return success status and task information
        """
        try:
            files = {"file": (filename, file_content, "text/vtt")}
            response = requests.post(
                f"{self.base_url}{API_ENDPOINTS.TRANSCRIPT_PROCESS}",
                files=files,
                timeout=TIMEOUTS.FILE_UPLOAD
            )
            return response.status_code == HTTP_STATUS.OK, response.json()
        except requests.RequestException as e:
            return False, {"error": str(e)}
    
    def get_task_status(self, task_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Get task status and results.
        
        Logic:
        1. Request task status from backend
        2. Parse response for status, progress, results
        3. Handle different task states consistently
        """
        try:
            url = f"{self.base_url}{API_ENDPOINTS.TASK_STATUS.format(task_id=task_id)}"
            response = requests.get(url, timeout=TIMEOUTS.STATUS_CHECK)
            return response.status_code == HTTP_STATUS.OK, response.json()
        except requests.RequestException as e:
            return False, {"error": str(e)}
    
    def extract_intelligence(self, transcript_id: str, detail_level: str, 
                           custom_instructions: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Extract meeting intelligence.
        
        Logic:
        1. Prepare intelligence extraction request
        2. Post to intelligence extraction endpoint  
        3. Return task information for polling
        """
        try:
            payload = {
                "transcript_id": transcript_id,
                "detail_level": detail_level
            }
            if custom_instructions:
                payload["custom_instructions"] = custom_instructions
                
            response = requests.post(
                f"{self.base_url}{API_ENDPOINTS.INTELLIGENCE_EXTRACT}",
                json=payload,
                timeout=TIMEOUTS.INTELLIGENCE_START
            )
            return response.status_code == HTTP_STATUS.OK, response.json()
        except requests.RequestException as e:
            return False, {"error": str(e)}