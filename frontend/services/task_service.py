"""Task management and polling service."""

import time
import streamlit as st
from typing import Dict, Any, Callable, Optional
from services.backend_service import BackendService
from utils.constants import TASK_STATUS, POLLING_CONFIG

class TaskService:
    """Handles task polling and status management."""
    
    def __init__(self, backend_service: BackendService):
        self.backend = backend_service
    
    def poll_task_with_ui(self, task_id: str, status_placeholder: Any, 
                         progress_placeholder: Any,
                         success_callback: Optional[Callable] = None,
                         error_callback: Optional[Callable] = None) -> bool:
        """Poll task with UI updates.
        
        Logic:
        1. Start polling loop with configured intervals
        2. Update UI placeholders with current status
        3. Handle completed, failed, and processing states
        4. Call appropriate callbacks on completion
        5. Return success/failure status
        """
        start_time = time.time()
        max_wait_time = POLLING_CONFIG.MAX_WAIT_SECONDS
        
        while time.time() - start_time < max_wait_time:
            success, data = self.backend.get_task_status(task_id)
            
            if not success:
                if error_callback:
                    error_callback(f"Failed to check task status: {data.get('error', 'Unknown error')}")
                return False
            
            status = data.get("status")
            progress = data.get("progress", 0)
            message = data.get("message", "Processing...")
            
            # Update UI
            status_placeholder.text(f"Status: {status}")
            progress_placeholder.progress(progress / 100.0 if progress > 1 else progress)
            
            if status == TASK_STATUS.COMPLETED:
                if success_callback:
                    success_callback(data)
                return True
            elif status == TASK_STATUS.FAILED:
                error_msg = data.get("error", {})
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", "Task failed")
                else:
                    error_msg = str(error_msg) if error_msg else "Task failed"
                if error_callback:
                    error_callback(error_msg)
                return False
            
            time.sleep(POLLING_CONFIG.INTERVAL_SECONDS)
        
        # Timeout
        if error_callback:
            error_callback("Task timed out")
        return False
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get completed task result.
        
        Logic:
        1. Request task status from backend
        2. Verify task is completed
        3. Return result data or None
        """
        success, data = self.backend.get_task_status(task_id)
        if success and data.get("status") == TASK_STATUS.COMPLETED:
            return data.get("result")
        return None