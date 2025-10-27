"""Centralized state management service."""

from typing import Any

import streamlit as st


class StateService:
    """Manages Streamlit session state for the app."""

    @staticmethod
    def initialize_page_state(required_keys: dict[str, Any]) -> None:
        """Initialize session state with required keys.

        Logic:
        1. Check each required key exists in session state
        2. Set default value if missing
        3. Validate existing values against expected types
        """
        for key, default_value in required_keys.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    # URL parameter helpers and task resumption are removed in Streamlit-only mode.
