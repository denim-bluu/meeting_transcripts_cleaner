"""
DuckDB-backed task cache with ACID compliance and multi-user concurrent access.

Responsibilities:
- Store tasks with automatic TTL expiration and efficient indexing
- Handle concurrent read/write operations with thread-local connections
- Provide ACID-compliant transactions for task state consistency
- Support idempotency keys with automatic expiration management
- Perform efficient cleanup with expired task removal and database vacuum

Expected Behavior:
- __init__ creates database file and tables if not exist, sets up indexes
- store_task() uses INSERT OR REPLACE for task updates, sets expires_at automatically
- get_task() returns None for missing or expired tasks, concurrent-read safe
- update_task() sets updated_at timestamp, maintains task expiration
- cleanup() removes expired tasks and idempotency keys, runs VACUUM for space reclaim
- health_check() returns cache stats including db_size_mb and task counts
- Thread-local connections prevent concurrent access issues
- All operations wrapped in asyncio.to_thread() for async compatibility
"""

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import threading
from typing import Any

import structlog

try:
    import duckdb
except ImportError:
    raise ImportError("DuckDB not installed. Install with: pip install duckdb")

from .models import TaskEntry, TaskStatus, TaskType

logger = structlog.get_logger(__name__)


class DuckDBTaskCache:
    """
    DuckDB-backed task cache with ACID compliance and multi-user support.

    This cache provides persistent storage for containerized deployments where:
    - Tasks need to survive container restarts
    - Multiple workers access the same task database
    - ACID compliance is required for data consistency
    - Efficient querying and cleanup are important
    """

    def __init__(self, db_path: str = "/app/data/tasks.duckdb"):
        """
        Initialize DuckDB cache with database schema and indexes.

        Args:
            db_path: Path to DuckDB file (created if not exists)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread-local connections for concurrent access
        self._local = threading.local()

        # Initialize database schema
        self._init_db()

        logger.info("DuckDB task cache initialized", db_path=str(self.db_path))

    def _get_conn(self):
        """Get thread-local connection for safe concurrent access."""
        if not hasattr(self._local, "conn"):
            self._local.conn = duckdb.connect(str(self.db_path))
        return self._local.conn

    def _init_db(self):
        """Initialize database schema with tasks and idempotency_keys tables."""
        conn = duckdb.connect(str(self.db_path))

        try:
            # Create tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id VARCHAR PRIMARY KEY,
                    task_type VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    task_data JSON NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """)

            # Create indexes for efficient querying
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_expires_at ON tasks (expires_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks (task_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks (created_at)"
            )

            # Create idempotency keys table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key VARCHAR PRIMARY KEY,
                    task_id VARCHAR NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for idempotency key cleanup
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys (expires_at)"
            )

            conn.commit()

        except Exception as e:
            logger.error("Failed to initialize DuckDB schema", error=str(e))
            raise
        finally:
            conn.close()

    async def store_task(self, task: TaskEntry) -> TaskEntry:
        """
        Store or update task in DuckDB with automatic expiration.

        Args:
            task: TaskEntry to store

        Returns:
            Stored TaskEntry with expires_at set if was None
        """

        def _store():
            conn = self._get_conn()

            # Set expiration if not provided
            if task.expires_at is None:
                task.expires_at = datetime.now() + timedelta(hours=1)

            # Set updated_at
            task.updated_at = datetime.now()

            # Serialize task data
            task_data = task.to_dict()

            try:
                # Use INSERT OR REPLACE for upsert behavior
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks
                    (task_id, task_type, status, task_data, created_at, updated_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        task.task_id,
                        task.task_type.value,
                        task.status.value,
                        json.dumps(
                            task_data, default=str
                        ),  # Handle datetime serialization
                        task.created_at,
                        task.updated_at,
                        task.expires_at,
                    ),
                )
                conn.commit()

                logger.debug(
                    "Task stored in DuckDB",
                    task_id=task.task_id,
                    status=task.status.value,
                )

            except Exception as e:
                logger.error(
                    "Failed to store task in DuckDB", task_id=task.task_id, error=str(e)
                )
                raise

        await asyncio.to_thread(_store)
        return task

    async def get_task(self, task_id: str) -> TaskEntry | None:
        """
        Retrieve non-expired task from DuckDB.

        Args:
            task_id: Unique task identifier

        Returns:
            TaskEntry if found and not expired, None otherwise
        """

        def _get():
            conn = self._get_conn()

            try:
                result = conn.execute(
                    """
                    SELECT task_data
                    FROM tasks
                    WHERE task_id = ?
                    AND expires_at > CURRENT_TIMESTAMP
                """,
                    (task_id,),
                ).fetchone()

                if result:
                    task_data = json.loads(result[0])
                    return TaskEntry(**task_data)
                return None

            except Exception as e:
                logger.error(
                    "Failed to get task from DuckDB", task_id=task_id, error=str(e)
                )
                return None

        return await asyncio.to_thread(_get)

    async def update_task(self, task: TaskEntry) -> TaskEntry:
        """Update existing task with current timestamp."""
        task.updated_at = datetime.now()
        return await self.store_task(task)

    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task from the cache.

        Args:
            task_id: Task to delete

        Returns:
            True if task was deleted, False if not found
        """

        def _delete():
            conn = self._get_conn()

            try:
                cursor = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                conn.commit()

                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug("Task deleted from DuckDB", task_id=task_id)
                return deleted

            except Exception as e:
                logger.error(
                    "Failed to delete task from DuckDB", task_id=task_id, error=str(e)
                )
                return False

        return await asyncio.to_thread(_delete)

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        limit: int = 100,
    ) -> list[TaskEntry]:
        """
        List tasks with optional filtering.

        Args:
            status: Filter by task status
            task_type: Filter by task type
            limit: Maximum number of tasks to return

        Returns:
            List of matching tasks, sorted by creation time (newest first)
        """

        def _list():
            conn = self._get_conn()

            try:
                # Build query with filters
                query = """
                    SELECT task_data FROM tasks
                    WHERE expires_at > CURRENT_TIMESTAMP
                """
                params = []

                if status:
                    query += " AND status = ?"
                    params.append(status.value)

                if task_type:
                    query += " AND task_type = ?"
                    params.append(task_type.value)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                results = conn.execute(query, params).fetchall()

                tasks = []
                for row in results:
                    task_data = json.loads(row[0])
                    tasks.append(TaskEntry(**task_data))

                return tasks

            except Exception as e:
                logger.error("Failed to list tasks from DuckDB", error=str(e))
                return []

        return await asyncio.to_thread(_list)

    async def get_task_count(self) -> int:
        """Get total number of active tasks."""

        def _count():
            conn = self._get_conn()

            try:
                result = conn.execute("""
                    SELECT COUNT(*) FROM tasks
                    WHERE expires_at > CURRENT_TIMESTAMP
                """).fetchone()

                return result[0] if result else 0

            except Exception as e:
                logger.error("Failed to count tasks in DuckDB", error=str(e))
                return 0

        return await asyncio.to_thread(_count)

    async def store_idempotency_key(
        self, key: str, task_id: str, expires_at: datetime
    ) -> bool:
        """
        Store an idempotency key mapping.

        Args:
            key: Idempotency key
            task_id: Associated task ID
            expires_at: When this mapping expires

        Returns:
            True if stored, False if key already exists
        """

        def _store_key():
            conn = self._get_conn()

            try:
                conn.execute(
                    """
                    INSERT INTO idempotency_keys (key, task_id, expires_at)
                    VALUES (?, ?, ?)
                """,
                    (key, task_id, expires_at),
                )
                conn.commit()

                logger.debug(
                    "Idempotency key stored in DuckDB", key=key, task_id=task_id
                )
                return True

            except Exception:  # Key already exists (PRIMARY KEY violation)
                return False

        return await asyncio.to_thread(_store_key)

    async def get_task_for_idempotency_key(self, key: str) -> str | None:
        """
        Get task ID for an idempotency key if not expired.

        Args:
            key: Idempotency key

        Returns:
            Task ID if key exists and not expired, None otherwise
        """

        def _get_key():
            conn = self._get_conn()

            try:
                result = conn.execute(
                    """
                    SELECT task_id FROM idempotency_keys
                    WHERE key = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                    (key,),
                ).fetchone()

                return result[0] if result else None

            except Exception as e:
                logger.error(
                    "Failed to get idempotency key from DuckDB", key=key, error=str(e)
                )
                return None

        return await asyncio.to_thread(_get_key)

    async def cleanup(self) -> dict[str, int]:
        """
        Remove expired tasks and keys, vacuum database for space reclaim.

        Returns:
            Dict with cleanup statistics (expired_tasks, expired_keys, remaining counts)
        """

        def _cleanup():
            conn = self._get_conn()

            try:
                # Count expired entries before cleanup
                expired_tasks = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE expires_at <= CURRENT_TIMESTAMP"
                ).fetchone()[0]

                expired_keys = conn.execute(
                    "SELECT COUNT(*) FROM idempotency_keys WHERE expires_at <= CURRENT_TIMESTAMP"
                ).fetchone()[0]

                # Delete expired entries
                conn.execute("DELETE FROM tasks WHERE expires_at <= CURRENT_TIMESTAMP")
                conn.execute(
                    "DELETE FROM idempotency_keys WHERE expires_at <= CURRENT_TIMESTAMP"
                )
                conn.commit()

                # Vacuum to reclaim space
                conn.execute("VACUUM")

                # Count remaining entries
                remaining_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[
                    0
                ]
                remaining_keys = conn.execute(
                    "SELECT COUNT(*) FROM idempotency_keys"
                ).fetchone()[0]

                stats = {
                    "expired_tasks": expired_tasks,
                    "expired_idempotency_keys": expired_keys,
                    "remaining_tasks": remaining_tasks,
                    "remaining_idempotency_keys": remaining_keys,
                }

                if expired_tasks > 0 or expired_keys > 0:
                    logger.info("DuckDB cache cleanup completed", **stats)

                return stats

            except Exception as e:
                logger.error("Failed to cleanup DuckDB cache", error=str(e))
                return {
                    "expired_tasks": 0,
                    "expired_idempotency_keys": 0,
                    "remaining_tasks": 0,
                    "remaining_idempotency_keys": 0,
                }

        return await asyncio.to_thread(_cleanup)

    async def health_check(self) -> dict[str, Any]:
        """
        Get cache health statistics and metrics.

        Returns:
            Dict with cache health info, task counts, and database size
        """

        def _health():
            conn = self._get_conn()

            try:
                # Get task statistics
                stats = conn.execute("""
                    SELECT
                        COUNT(*) as total_tasks,
                        COUNT(DISTINCT status) as status_types,
                        COUNT(CASE WHEN expires_at <= datetime('now', '+1 hour') THEN 1 END) as expires_soon
                    FROM tasks
                    WHERE expires_at > CURRENT_TIMESTAMP
                """).fetchone()

                # Get idempotency key count
                key_count = conn.execute("""
                    SELECT COUNT(*) FROM idempotency_keys
                    WHERE expires_at > CURRENT_TIMESTAMP
                """).fetchone()[0]

                # Get database file size
                db_size_mb = 0
                if self.db_path.exists():
                    db_size_mb = round(self.db_path.stat().st_size / 1024 / 1024, 2)

                # Get status breakdown
                status_results = conn.execute("""
                    SELECT status, COUNT(*) FROM tasks
                    WHERE expires_at > CURRENT_TIMESTAMP
                    GROUP BY status
                """).fetchall()

                status_breakdown = {row[0]: row[1] for row in status_results}

                return {
                    "cache": "healthy",
                    "backend": "duckdb",
                    "total_tasks": stats[0],
                    "total_idempotency_keys": key_count,
                    "status_breakdown": status_breakdown,
                    "status_types": stats[1],
                    "expires_within_1h": stats[2],
                    "db_size_mb": db_size_mb,
                    "db_path": str(self.db_path),
                    "memory_usage": "persistent",
                }

            except Exception as e:
                logger.error("Failed to get DuckDB health check", error=str(e))
                return {
                    "cache": "unhealthy",
                    "backend": "duckdb",
                    "error": str(e),
                    "total_tasks": 0,
                    "total_idempotency_keys": 0,
                }

        return await asyncio.to_thread(_health)
