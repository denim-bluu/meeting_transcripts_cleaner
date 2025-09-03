"""Error display and handling components."""

from typing import Any

import streamlit as st
from utils.constants import ERROR_MESSAGES


def display_error(
    error_type: str,
    custom_message: str | None = None,
    details: dict[str, Any] | None = None,
    show_retry: bool = True,
) -> None:
    """Display standardized error message.

    Logic:
    1. Get appropriate error message from constants
    2. Display with consistent styling
    3. Include details if provided
    4. Show retry option if applicable
    """
    base_message = ERROR_MESSAGES.get(error_type, "An unexpected error occurred")
    display_message = custom_message or base_message

    st.error(f"❌ {display_message}")

    # Show details in expander if provided
    if details:
        with st.expander("Error Details", expanded=False):
            for key, value in details.items():
                st.code(f"{key}: {value}")

    # Show retry suggestion
    if show_retry:
        st.info("💡 Try refreshing the page or check your connection")


def display_warning(message: str, action_suggestion: str | None = None) -> None:
    """Display standardized warning message.

    Logic:
    1. Show warning with consistent styling
    2. Include action suggestion if provided
    """
    st.warning(f"⚠️ {message}")

    if action_suggestion:
        st.info(f"💡 {action_suggestion}")


def display_validation_errors(errors: list[str]) -> None:
    """Display multiple validation errors.

    Logic:
    1. Group validation errors in single container
    2. Format as bulleted list
    3. Use appropriate error styling
    """
    if not errors:
        return

    st.error("❌ Please fix the following issues:")

    for error in errors:
        st.markdown(f"• {error}")


def handle_api_error(response_data: dict[str, Any]) -> None:
    """Handle and display API error responses.

    Logic:
    1. Parse API error response
    2. Extract error details and context
    3. Display with appropriate formatting
    """
    error_info = response_data.get("error", {})

    if isinstance(error_info, dict):
        error_code = error_info.get("code", "unknown")
        error_message = error_info.get("message", "Unknown error occurred")
        error_field = error_info.get("field")

        display_error(
            error_type="api_error",
            custom_message=f"{error_message} (Code: {error_code})",
            details={"field": error_field} if error_field else None,
        )
    else:
        # Simple error string
        error_message = str(error_info) if error_info else "API request failed"
        display_error("api_error", error_message)


def require_data(
    data: Any, data_name: str, redirect_message: str | None = None
) -> None:
    """Require data exists or show error and stop.

    Logic:
    1. Check if required data exists
    2. If missing, show error and stop page execution
    3. Provide guidance for obtaining required data
    """
    if not data:
        error_msg = f"Required {data_name} is not available"
        guidance = redirect_message or f"Please ensure {data_name} is loaded first"

        display_error("missing_data", error_msg)
        st.info(f"💡 {guidance}")
        st.stop()
