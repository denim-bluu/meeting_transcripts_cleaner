"""
Task cache factory with environment-based implementation selection.

Responsibilities:
- Select appropriate cache implementation based on CACHE_TYPE environment variable
- Provide unified interface for cache operations across implementations
- Initialize global cache instance for dependency injection
- Support development (in-memory) and production (DuckDB) configurations

Expected Behavior:
- get_cache_implementation() returns DuckDB cache if CACHE_TYPE=duckdb
- Falls back to SimpleTaskCache for development if CACHE_TYPE not set or != duckdb
- initialize_cache() sets up global _cache instance called during app startup
- get_task_cache() returns initialized cache or raises RuntimeError if not initialized
- Supports DUCKDB_PATH environment variable for custom database location
"""

import os
from typing import Union

# Global cache instance (initialized once at startup)
_cache = None


def get_cache_implementation():
    """
    Get cache implementation based on environment configuration.

    Returns:
        DuckDBTaskCache for production (CACHE_TYPE=duckdb)
        SimpleTaskCache for development (default)
    """
    cache_type = os.getenv("CACHE_TYPE", "memory").lower()

    if cache_type == "duckdb":
        from .cache_duckdb import DuckDBTaskCache
        db_path = os.getenv("DUCKDB_PATH", "/app/data/tasks.duckdb")
        return DuckDBTaskCache(db_path=db_path)
    else:
        # Fallback to in-memory for development
        from .cache import SimpleTaskCache
        return SimpleTaskCache()


def initialize_cache(ttl_hours: int = 1, cleanup_interval_minutes: int = 10) -> None:
    """
    Initialize global cache instance during application startup.
    
    Args:
        ttl_hours: Default TTL for tasks in hours (used by SimpleTaskCache)
        cleanup_interval_minutes: Cleanup interval in minutes (used by SimpleTaskCache)
    """
    global _cache
    
    cache_type = os.getenv("CACHE_TYPE", "memory").lower()
    
    if cache_type == "duckdb":
        from .cache_duckdb import DuckDBTaskCache
        db_path = os.getenv("DUCKDB_PATH", "/app/data/tasks.duckdb")
        _cache = DuckDBTaskCache(db_path=db_path)
    else:
        from .cache import SimpleTaskCache
        _cache = SimpleTaskCache(
            default_ttl_hours=ttl_hours,
            cleanup_interval_minutes=cleanup_interval_minutes
        )
    
    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("Global task cache initialized", cache_type=cache_type)


def get_task_cache():
    """
    Get initialized global cache instance.
    
    Returns:
        The global task cache instance
        
    Raises:
        RuntimeError: If cache not initialized
    """
    if _cache is None:
        raise RuntimeError("Task cache not initialized. Call initialize_cache() first.")
    return _cache


def reset_cache() -> None:
    """Reset the global cache (for testing)."""
    global _cache
    _cache = None