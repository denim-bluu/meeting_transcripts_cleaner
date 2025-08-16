"""
Debug Page - Simple system monitoring and database inspection.

Provides basic debugging capabilities for viewing system health, task history,
and database contents without over-engineering.
"""

from datetime import datetime

from api_client import api_client
from config import configure_structlog
import streamlit as st
import structlog

# Configure structured logging
configure_structlog()
logger = structlog.get_logger(__name__)

logger.info("Debug page initialized", streamlit_page=True, mode="api_client")

# Page configuration
st.set_page_config(
    page_title="Debug",
    page_icon="🔧",
    layout="wide",
)

st.title("🔧 Debug")
st.markdown("System monitoring and database inspection")

# Check backend health first
with st.spinner("Checking backend connection..."):
    is_healthy, health_data = api_client.health_check()

if not is_healthy:
    st.error(
        "❌ Backend unavailable. Please check that the backend service is running."
    )
    st.stop()

# Main debug sections
tab1, tab2, tab3 = st.tabs(["🏥 Health", "📊 Database", "📋 Tasks"])

with tab1:
    st.subheader("System Health")

    # Display health status
    st.json(health_data)

    # Health metrics
    col1, col2, col3, col4 = st.columns(4)
    if health_data:
        col1.metric("Status", health_data.get("status", "unknown"))
        col2.metric("Tasks", health_data.get("tasks_in_memory", 0))
        col3.metric(
            "Database", health_data.get("dependencies", {}).get("database", "unknown")
        )
        col4.metric(
            "OpenAI", health_data.get("dependencies", {}).get("openai", "unknown")
        )

    # Auto-refresh option
    if st.button("🔄 Refresh Health"):
        st.rerun()

with tab2:
    st.subheader("Database Analytics")

    if st.button("📊 Load Database Analytics"):
        with st.spinner("Loading analytics..."):
            try:
                response = api_client._make_request("GET", "/debug/analytics")
                if response:
                    st.success("✅ Analytics loaded")

                    # Database health
                    db_health = response.get("database_health", {})
                    st.write("**Database Health:**")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Type", db_health.get("type", "unknown"))
                    col2.metric("Status", db_health.get("database", "unknown"))
                    col3.metric("Task Count", db_health.get("task_count", 0))
                    col4.metric("File Size (MB)", db_health.get("file_size_mb", 0))

                    # Analytics summary
                    analytics = response.get("analytics", {}).get("summary", [])
                    if analytics:
                        st.write("**Task Analytics:**")
                        for item in analytics:
                            st.write(
                                f"- {item['task_type']} ({item['status']}): {item['count']} tasks, {item['avg_progress']:.1%} avg progress"
                            )
                    else:
                        st.info("No analytics data available")
                else:
                    st.error("Failed to load analytics")
            except Exception as e:
                st.error(f"Error: {str(e)}")

with tab3:
    st.subheader("Task History")

    # Simple filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Status", ["All", "processing", "completed", "failed"]
        )
    with col2:
        type_filter = st.selectbox(
            "Type", ["All", "transcript_processing", "intelligence_extraction"]
        )
    with col3:
        hours_back = st.number_input("Hours Back", min_value=1, max_value=168, value=24)

    if st.button("📋 Load Tasks"):
        with st.spinner("Loading tasks..."):
            try:
                # Build query
                params = f"?hours_back={hours_back}&limit=50"
                if status_filter != "All":
                    params += f"&status={status_filter}"
                if type_filter != "All":
                    params += f"&task_type={type_filter}"

                response = api_client._make_request("GET", f"/debug/tasks{params}")
                if response:
                    tasks = response.get("tasks", [])

                    if tasks:
                        st.success(f"✅ Found {len(tasks)} tasks")

                        # Simple task list
                        for task in tasks:
                            with st.expander(
                                f"{task['task_type']} - {task['status']} ({task['task_id'][:8]}...)"
                            ):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Status:** {task['status']}")
                                    st.write(f"**Progress:** {task['progress']:.1%}")
                                    st.write(f"**Created:** {task['created_at']}")
                                with col2:
                                    st.write(f"**Message:** {task['message']}")
                                    if task.get("error"):
                                        st.write(f"**Error:** {task['error']}")
                                    if task.get("metadata"):
                                        st.write("**Metadata:**")
                                        st.json(task["metadata"])
                    else:
                        st.info("No tasks found")
                else:
                    st.error("Failed to load tasks")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Sidebar info
st.sidebar.markdown("---")
st.sidebar.subheader("🔧 Debug Info")
st.sidebar.write(f"**Page Load:** {datetime.now().strftime('%H:%M:%S')}")
st.sidebar.write(f"**Backend:** {api_client.base_url}")

if st.sidebar.button("🔄 Refresh Page"):
    st.rerun()
