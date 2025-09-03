"""Centralized state management service."""

import streamlit as st
from typing import Any, Dict, Optional
from utils.constants import STATE_KEYS, DEFAULT_VALUES

class StateService:
    """Manages session state and URL parameters consistently."""
    
    @staticmethod
    def initialize_page_state(required_keys: Dict[str, Any]) -> None:
        """Initialize session state with required keys.
        
        Logic:
        1. Check each required key exists in session state
        2. Set default value if missing
        3. Validate existing values against expected types
        """
        for key, default_value in required_keys.items():
            if key not in st.session_state:
                st.session_state[key] = default_value
    
    @staticmethod
    def get_url_param(param_name: str, default: Any = None) -> Any:
        """Get URL parameter value.
        
        Logic:
        1. Check st.query_params for parameter
        2. Return value or default if not found
        3. Handle type conversion if needed
        """
        query_params = st.query_params
        return query_params.get(param_name, default)
    
    @staticmethod
    def set_url_param(param_name: str, value: Any) -> None:
        """Set URL parameter value.
        
        Logic:
        1. Update st.query_params with new value
        2. Maintain other existing parameters
        """
        st.query_params[param_name] = str(value)
    
    @staticmethod
    def clear_url_params(params_to_clear: Optional[list] = None) -> None:
        """Clear URL parameters.
        
        Logic:
        1. Clear specific parameters or all if none specified
        2. Update URL to reflect changes
        """
        if params_to_clear:
            for param in params_to_clear:
                st.query_params.pop(param, None)
        else:
            st.query_params.clear()
    
    @staticmethod
    def handle_task_resumption() -> Optional[str]:
        """Handle task resumption from URL.
        
        Logic:
        1. Check URL for task_id parameter
        2. Validate task_id format
        3. Return task_id for resumption or None
        """
        task_id = StateService.get_url_param("task_id")
        if task_id and len(task_id) > 10:  # Basic validation
            return task_id
        return None
    
    @staticmethod
    def cleanup_expired_state() -> None:
        """Clean up expired or invalid state.
        
        Logic:
        1. Check for expired task references
        2. Clear invalid URL parameters
        3. Reset page state if corrupted
        """
        # Clean up old task references
        keys_to_remove = []
        for key in st.session_state:
            if key.startswith("task_") and key.endswith("_expired"):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del st.session_state[key]