"""
Simplified DuckDB implementation of the repository pattern.

Provides persistent storage using DuckDB with a pragmatic approach:
- Shared connection with proper locking
- Basic error handling
- Essential features only
"""

import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import Any, cast

import duckdb
import structlog

from backend_service.api.v1.schemas import TaskStatus, TaskType
from backend_service.repositories.base import (
    IdempotencyRepository,
    TaskEntity,
    TaskRepository,
)

logger = structlog.get_logger(__name__)


class DuckDBRepository:
    """Base class for DuckDB repositories with shared connection logic."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Single lock for all database operations to prevent concurrency issues
        self._db_lock = asyncio.Lock()

    async def _execute(self, query: str, params: tuple = ()) -> None:
        """Execute query with proper locking to prevent concurrency issues."""
        async with self._db_lock:

            def _run():
                with duckdb.connect(str(self.db_path)) as conn:
                    conn.execute(query, params)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _run)

    async def _fetch_one(self, query: str, params: tuple = ()) -> tuple | None:
        """Execute query and return one row with proper locking."""
        async with self._db_lock:

            def _run():
                with duckdb.connect(str(self.db_path)) as conn:
                    return conn.execute(query, params).fetchone()

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _run)

    async def _fetch_all(self, query: str, params: tuple = ()) -> list[tuple]:
        """Execute query and return all rows with proper locking."""
        async with self._db_lock:

            def _run():
                with duckdb.connect(str(self.db_path)) as conn:
                    return conn.execute(query, params).fetchall()

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _run)


class DuckDBTaskRepository(DuckDBRepository, TaskRepository):
    """DuckDB implementation of TaskRepository."""

    def __init__(self, db_path: str = "data/tasks.duckdb"):
        super().__init__(db_path)
        logger.info("DuckDB task repository initialized", db_path=str(self.db_path))

    async def _init_db(self) -> None:
        """Initialize database schema."""
        await self._execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR PRIMARY KEY,
                task_type VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                progress DOUBLE DEFAULT 0.0,
                message VARCHAR DEFAULT '',
                result JSON,
                error VARCHAR,
                error_code VARCHAR,
                metadata JSON
            )
        """)

        # Essential indexes only
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)"
        )

    async def create_task(self, task: TaskEntity) -> TaskEntity:
        """Create a new task."""
        await self._init_db()

        await self._execute(
            """
            INSERT INTO tasks (
                task_id, task_type, status, created_at, updated_at,
                progress, message, result, error, error_code, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task.task_id,
                task.task_type.value,
                task.status.value,
                task.created_at,
                task.updated_at,
                task.progress,
                task.message,
                json.dumps(task.result) if task.result else None,
                task.error,
                task.error_code,
                json.dumps(task.metadata),
            ),
        )

        logger.info(
            "Task created", task_id=task.task_id, task_type=task.task_type.value
        )
        return task

    async def get_task(self, task_id: str) -> TaskEntity | None:
        """Get a task by ID."""
        await self._init_db()

        row = await self._fetch_one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        return self._row_to_entity(row) if row else None

    async def update_task(self, task: TaskEntity) -> TaskEntity:
        """Update an existing task."""
        await self._init_db()

        task.updated_at = datetime.now()

        await self._execute(
            """
            UPDATE tasks SET
                status = ?, updated_at = ?, progress = ?, message = ?,
                result = ?, error = ?, error_code = ?, metadata = ?
            WHERE task_id = ?
        """,
            (
                task.status.value,
                task.updated_at,
                task.progress,
                task.message,
                json.dumps(task.result) if task.result else None,
                task.error,
                task.error_code,
                json.dumps(task.metadata),
                task.task_id,
            ),
        )

        logger.debug("Task updated", task_id=task.task_id, status=task.status.value)
        return task

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        await self._init_db()

        # Simple approach: check if exists, then delete
        existing = await self.get_task(task_id)
        if not existing:
            return False

        await self._execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))

        # Verify deletion
        deleted_task = await self.get_task(task_id)
        success = deleted_task is None

        if success:
            logger.info("Task deleted", task_id=task_id)
        return success

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskEntity]:
        """List tasks with optional filtering."""
        await self._init_db()

        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if task_type:
            query += " AND task_type = ?"
            params.append(task_type.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self._fetch_all(query, tuple(params))
        return [self._row_to_entity(row) for row in rows]

    async def cleanup_old_tasks(self, older_than: datetime) -> int:
        """Clean up tasks older than the specified datetime."""
        await self._init_db()

        # Count first, then delete
        count_result = await self._fetch_one(
            "SELECT COUNT(*) FROM tasks WHERE created_at < ?", (older_than,)
        )
        count = count_result[0] if count_result else 0

        if count > 0:
            await self._execute("DELETE FROM tasks WHERE created_at < ?", (older_than,))
            logger.info("Old tasks cleaned up", count=count)

        return count

    async def get_task_count(self) -> int:
        """Get total number of tasks."""
        await self._init_db()

        row = await self._fetch_one("SELECT COUNT(*) FROM tasks")
        return cast(int, row[0]) if row else 0

    async def health_check(self) -> dict[str, Any]:
        """Check repository health."""
        try:
            await self._init_db()
            task_count = await self.get_task_count()

            version_row = await self._fetch_one("SELECT version()")
            version = cast(str, version_row[0]) if version_row else "unknown"

            return {
                "database": "healthy",
                "type": "duckdb",
                "version": version,
                "path": str(self.db_path),
                "task_count": task_count,
                "file_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2)
                if self.db_path.exists()
                else 0,
            }
        except Exception as e:
            logger.error("Repository health check failed", error=str(e))
            return {"database": "unhealthy", "error": str(e)}

    def _row_to_entity(self, row: tuple) -> TaskEntity:
        """Convert DuckDB row to TaskEntity."""
        return TaskEntity(
            task_id=row[0],
            task_type=TaskType(row[1]),
            status=TaskStatus(row[2]),
            created_at=row[3],
            updated_at=row[4],
            progress=row[5],
            message=row[6],
            result=json.loads(row[7]) if row[7] else None,
            error=row[8],
            error_code=row[9],
            metadata=json.loads(row[10]) if row[10] else {},
        )

    async def get_analytics_summary(self) -> dict[str, Any]:
        """Get basic analytics summary."""
        await self._init_db()

        rows = await self._fetch_all("""
            SELECT
                task_type,
                status,
                COUNT(*) as count,
                AVG(progress) as avg_progress
            FROM tasks
            GROUP BY task_type, status
            ORDER BY task_type, status
        """)

        return {
            "summary": [
                {
                    "task_type": row[0],
                    "status": row[1],
                    "count": row[2],
                    "avg_progress": round(row[3], 2) if row[3] else 0,
                }
                for row in rows
            ]
        }


class DuckDBIdempotencyRepository(DuckDBRepository, IdempotencyRepository):
    """DuckDB implementation of IdempotencyRepository."""

    def __init__(self, db_path: str = "data/tasks.duckdb"):
        super().__init__(db_path)

    async def _init_db(self) -> None:
        """Initialize database schema."""
        await self._execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key VARCHAR PRIMARY KEY,
                task_id VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
        """)

        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at ON idempotency_keys(expires_at)"
        )

    async def store_idempotency_key(
        self, key: str, task_id: str, expires_at: datetime
    ) -> bool:
        """Store an idempotency key with associated task ID."""
        await self._init_db()

        try:
            await self._execute(
                """
                INSERT INTO idempotency_keys (key, task_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (key, task_id, datetime.now(), expires_at),
            )

            logger.debug("Idempotency key stored", key=key, task_id=task_id)
            return True
        except Exception as e:
            # Key already exists
            if "Constraint Error" in str(e) or "PRIMARY KEY" in str(e):
                logger.debug("Idempotency key already exists", key=key)
                return False
            raise e

    async def get_task_for_key(self, key: str) -> str | None:
        """Get task ID for an idempotency key if it exists and hasn't expired."""
        await self._init_db()

        row = await self._fetch_one(
            """
            SELECT task_id FROM idempotency_keys
            WHERE key = ? AND expires_at > ?
        """,
            (key, datetime.now()),
        )

        return cast(str, row[0]) if row else None

    async def cleanup_expired_keys(self) -> int:
        """Clean up expired idempotency keys."""
        await self._init_db()

        # Count first, then delete
        count_result = await self._fetch_one(
            "SELECT COUNT(*) FROM idempotency_keys WHERE expires_at < ?",
            (datetime.now(),),
        )
        count = count_result[0] if count_result else 0

        if count > 0:
            await self._execute(
                "DELETE FROM idempotency_keys WHERE expires_at < ?", (datetime.now(),)
            )
            logger.info("Expired idempotency keys cleaned up", count=count)

        return count
