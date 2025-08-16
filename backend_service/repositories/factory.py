"""
Repository factory for dependency injection and configuration.

Simplified factory that supports DuckDB for development and Snowflake for production.
"""

import os

import structlog

from backend_service.repositories.base import IdempotencyRepository, TaskRepository
from backend_service.repositories.duckdb_repository import (
    DuckDBIdempotencyRepository,
    DuckDBTaskRepository,
)

logger = structlog.get_logger(__name__)


class RepositoryFactory:
    """Factory for creating repository instances."""

    @staticmethod
    def create_repositories() -> tuple[TaskRepository, IdempotencyRepository]:
        """
        Create repository instances based on environment configuration.

        Returns:
            Tuple of (TaskRepository, IdempotencyRepository)
        """
        repository_type = os.getenv("REPOSITORY_TYPE", "duckdb").lower()

        if repository_type == "duckdb":
            return RepositoryFactory._create_duckdb_repositories()
        elif repository_type == "snowflake":
            return RepositoryFactory._create_snowflake_repositories()
        else:
            logger.warning(
                "Unknown repository type, falling back to DuckDB",
                repository_type=repository_type,
            )
            return RepositoryFactory._create_duckdb_repositories()

    @staticmethod
    def _create_duckdb_repositories() -> tuple[TaskRepository, IdempotencyRepository]:
        """Create DuckDB repository instances."""
        db_path = os.getenv("DUCKDB_DB_PATH", "data/tasks.duckdb")

        logger.info("Creating DuckDB repositories", db_path=db_path)

        task_repo = DuckDBTaskRepository(db_path)
        idempotency_repo = DuckDBIdempotencyRepository(db_path)

        return task_repo, idempotency_repo

    @staticmethod
    def _create_snowflake_repositories() -> (
        tuple[TaskRepository, IdempotencyRepository]
    ):
        """Create Snowflake repository instances."""
        # TODO: Implement Snowflake repositories for production
        logger.info("Creating Snowflake repositories")

        try:
            from backend_service.repositories.snowflake_repository import (  # type: ignore
                SnowflakeIdempotencyRepository,
                SnowflakeTaskRepository,
            )

            task_repo = SnowflakeTaskRepository()
            idempotency_repo = SnowflakeIdempotencyRepository()

            return task_repo, idempotency_repo

        except ImportError:
            logger.warning(
                "Snowflake repositories not implemented, falling back to DuckDB"
            )
            return RepositoryFactory._create_duckdb_repositories()


# Global repository instances (initialized once at startup)
_task_repository: TaskRepository | None = None
_idempotency_repository: IdempotencyRepository | None = None


def get_task_repository() -> TaskRepository:
    """Get the global task repository instance."""
    global _task_repository
    if _task_repository is None:
        _task_repository, _ = RepositoryFactory.create_repositories()
    return _task_repository


def get_idempotency_repository() -> IdempotencyRepository:
    """Get the global idempotency repository instance."""
    global _idempotency_repository
    if _idempotency_repository is None:
        _, _idempotency_repository = RepositoryFactory.create_repositories()
    return _idempotency_repository


def initialize_repositories():
    """Initialize repositories at application startup."""
    global _task_repository, _idempotency_repository

    logger.info("Initializing repositories")
    _task_repository, _idempotency_repository = RepositoryFactory.create_repositories()

    logger.info(
        "Repositories initialized",
        task_repo=type(_task_repository).__name__,
        idempotency_repo=type(_idempotency_repository).__name__,
    )
