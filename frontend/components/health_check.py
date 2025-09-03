"""Minimal backend health check component."""

from services.backend_service import BackendService
import streamlit as st


def require_healthy_backend(backend_service: BackendService) -> bool:
    """Check backend health. Show simple error if unavailable.

    Logic:
    1. Check backend health (no caching, no refresh buttons)
    2. If unhealthy, show minimal error and stop
    3. If healthy, continue silently
    """
    is_healthy, health_data = backend_service.check_health()

    if not is_healthy:
        st.error(
            "❌ Backend service is not available. Please start the backend server."
        )
        st.stop()

    return is_healthy
