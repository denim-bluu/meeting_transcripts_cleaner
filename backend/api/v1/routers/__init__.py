"""
Domain-specific API routers for Meeting Transcript Cleaner.

This module organizes API endpoints by domain instead of having a monolithic endpoints file:
- health: System monitoring and dependency health checks
- transcript: VTT file upload and processing
- intelligence: Meeting analysis and insight extraction
- tasks: Task status polling and lifecycle management
- debug: System debugging and analytics

Each router is focused on a specific domain with clear responsibilities.
"""