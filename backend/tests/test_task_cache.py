"""
Comprehensive unit tests for the SimpleTaskCache implementation.

Tests cover core functionality, edge cases, and concurrent access patterns
to ensure reliability in production environments.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from backend.core.task_cache import (
    SimpleTaskCache,
    TaskEntry,
    TaskStatus,
    TaskType,
    get_task_cache,
    initialize_cache,
    reset_cache,
)


@pytest.fixture
def cache():
    """Create a fresh cache instance for each test."""
    return SimpleTaskCache(default_ttl_hours=1, cleanup_interval_minutes=1)


@pytest.fixture
def sample_task():
    """Create a sample task entry for testing."""
    return TaskEntry(
        task_id="test-123",
        task_type=TaskType.TRANSCRIPT_PROCESSING,
        status=TaskStatus.PROCESSING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        progress=0.5,
        message="Test task in progress",
        metadata={"test": True, "priority": "high"},
    )


class TestTaskEntry:
    """Test TaskEntry data class functionality."""

    def test_task_entry_creation(self):
        """Test basic task entry creation."""
        now = datetime.now()
        task = TaskEntry(
            task_id="test-001",
            task_type=TaskType.INTELLIGENCE_EXTRACTION,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        assert task.task_id == "test-001"
        assert task.task_type == TaskType.INTELLIGENCE_EXTRACTION
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0.0
        assert task.message == ""
        assert task.result is None
        assert task.error is None
        assert task.metadata is None

    def test_task_entry_to_dict(self, sample_task):
        """Test task entry serialization to dictionary."""
        task_dict = sample_task.to_dict()

        assert task_dict["task_id"] == "test-123"
        assert task_dict["type"] == "transcript_processing"
        assert task_dict["status"] == "processing"
        assert task_dict["progress"] == 0.5
        assert task_dict["message"] == "Test task in progress"
        assert task_dict["metadata"] == {"test": True, "priority": "high"}
        assert isinstance(task_dict["created_at"], datetime)
        assert isinstance(task_dict["updated_at"], datetime)

    def test_task_entry_with_result_and_error(self):
        """Test task entry with result and error data."""
        task = TaskEntry(
            task_id="test-002",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.FAILED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            result={"chunks": 42, "speakers": ["Alice", "Bob"]},
            error="Processing failed due to invalid format",
            error_code="invalid_format",
        )

        assert task.result == {"chunks": 42, "speakers": ["Alice", "Bob"]}
        assert task.error == "Processing failed due to invalid format"
        assert task.error_code == "invalid_format"


class TestSimpleTaskCache:
    """Test SimpleTaskCache core functionality."""

    @pytest.mark.asyncio
    async def test_cache_initialization(self):
        """Test cache initialization with custom parameters."""
        cache = SimpleTaskCache(default_ttl_hours=2, cleanup_interval_minutes=5)

        assert cache.default_ttl == timedelta(hours=2)
        assert cache.cleanup_interval == timedelta(minutes=5)
        assert len(cache._tasks) == 0
        assert len(cache._idempotency_keys) == 0

    @pytest.mark.asyncio
    async def test_store_and_retrieve_task(self, cache, sample_task):
        """Test basic task storage and retrieval."""
        # Store task
        stored_task = await cache.store_task(sample_task)
        assert stored_task.task_id == sample_task.task_id
        assert stored_task.expires_at is not None

        # Retrieve task
        retrieved_task = await cache.get_task("test-123")
        assert retrieved_task is not None
        assert retrieved_task.task_id == "test-123"
        assert retrieved_task.status == TaskStatus.PROCESSING
        assert retrieved_task.progress == 0.5

    @pytest.mark.asyncio
    async def test_store_duplicate_task_raises_error(self, cache, sample_task):
        """Test that storing duplicate task IDs raises an error."""
        await cache.store_task(sample_task)

        # Try to store same task ID again
        duplicate_task = TaskEntry(
            task_id="test-123",  # Same ID
            task_type=TaskType.INTELLIGENCE_EXTRACTION,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with pytest.raises(ValueError, match="Task test-123 already exists"):
            await cache.store_task(duplicate_task)

    @pytest.mark.asyncio
    async def test_update_task(self, cache, sample_task):
        """Test task updates."""
        # Store initial task
        await cache.store_task(sample_task)

        # Update task
        sample_task.status = TaskStatus.COMPLETED
        sample_task.progress = 1.0
        sample_task.message = "Task completed successfully"
        sample_task.result = {"status": "success", "output": "processed_data.json"}

        updated_task = await cache.update_task(sample_task)

        assert updated_task.status == TaskStatus.COMPLETED
        assert updated_task.progress == 1.0
        assert updated_task.message == "Task completed successfully"
        assert updated_task.result == {
            "status": "success",
            "output": "processed_data.json",
        }
        assert updated_task.updated_at > updated_task.created_at

    @pytest.mark.asyncio
    async def test_update_nonexistent_task_raises_error(self, cache):
        """Test that updating non-existent task raises an error."""
        nonexistent_task = TaskEntry(
            task_id="nonexistent",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with pytest.raises(ValueError, match="Task nonexistent not found"):
            await cache.update_task(nonexistent_task)

    @pytest.mark.asyncio
    async def test_delete_task(self, cache, sample_task):
        """Test task deletion."""
        # Store task
        await cache.store_task(sample_task)
        assert await cache.get_task("test-123") is not None

        # Delete task
        deleted = await cache.delete_task("test-123")
        assert deleted is True

        # Verify task is gone
        assert await cache.get_task("test-123") is None

        # Delete non-existent task
        deleted_again = await cache.delete_task("test-123")
        assert deleted_again is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_none(self, cache):
        """Test that retrieving non-existent task returns None."""
        task = await cache.get_task("nonexistent")
        assert task is None

    @pytest.mark.asyncio
    async def test_task_expiration(self, cache):
        """Test automatic task expiration."""
        # Create task that expires immediately
        expired_task = TaskEntry(
            task_id="expired-123",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=datetime.now() - timedelta(seconds=1),  # Already expired
        )

        await cache.store_task(expired_task)

        # Task should be automatically removed when accessed
        retrieved_task = await cache.get_task("expired-123")
        assert retrieved_task is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, cache):
        """Test task listing with filtering."""
        # Create multiple tasks
        tasks = [
            TaskEntry(
                task_id=f"task-{i}",
                task_type=TaskType.TRANSCRIPT_PROCESSING
                if i % 2 == 0
                else TaskType.INTELLIGENCE_EXTRACTION,
                status=TaskStatus.PROCESSING if i < 3 else TaskStatus.COMPLETED,
                created_at=datetime.now() - timedelta(minutes=i),
                updated_at=datetime.now() - timedelta(minutes=i),
            )
            for i in range(5)
        ]

        for task in tasks:
            await cache.store_task(task)

        # List all tasks
        all_tasks = await cache.list_tasks()
        assert len(all_tasks) == 5

        # List by status
        processing_tasks = await cache.list_tasks(status=TaskStatus.PROCESSING)
        assert len(processing_tasks) == 3

        # List by type
        transcript_tasks = await cache.list_tasks(
            task_type=TaskType.TRANSCRIPT_PROCESSING
        )
        assert len(transcript_tasks) == 3  # tasks 0, 2, 4

        # List with limit
        limited_tasks = await cache.list_tasks(limit=2)
        assert len(limited_tasks) == 2

        # Verify sorting (newest first)
        assert limited_tasks[0].task_id == "task-0"  # Most recent

    @pytest.mark.asyncio
    async def test_get_task_count(self, cache):
        """Test task count functionality."""
        assert await cache.get_task_count() == 0

        # Add some tasks
        for i in range(3):
            task = TaskEntry(
                task_id=f"count-{i}",
                task_type=TaskType.TRANSCRIPT_PROCESSING,
                status=TaskStatus.PROCESSING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            await cache.store_task(task)

        assert await cache.get_task_count() == 3


class TestIdempotencyKeys:
    """Test idempotency key functionality."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_idempotency_key(self, cache):
        """Test idempotency key storage and retrieval."""
        key = "unique-operation-123"
        task_id = "task-456"
        expires_at = datetime.now() + timedelta(hours=1)

        # Store key
        stored = await cache.store_idempotency_key(key, task_id, expires_at)
        assert stored is True

        # Retrieve key
        retrieved_task_id = await cache.get_task_for_idempotency_key(key)
        assert retrieved_task_id == task_id

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_key_returns_false(self, cache):
        """Test that storing duplicate idempotency key returns False."""
        key = "duplicate-key"
        task_id_1 = "task-001"
        task_id_2 = "task-002"
        expires_at = datetime.now() + timedelta(hours=1)

        # Store first key
        stored_1 = await cache.store_idempotency_key(key, task_id_1, expires_at)
        assert stored_1 is True

        # Try to store same key again
        stored_2 = await cache.store_idempotency_key(key, task_id_2, expires_at)
        assert stored_2 is False

        # Original mapping should still exist
        retrieved_task_id = await cache.get_task_for_idempotency_key(key)
        assert retrieved_task_id == task_id_1

    @pytest.mark.asyncio
    async def test_expired_idempotency_key_returns_none(self, cache):
        """Test that expired idempotency keys return None."""
        key = "expired-key"
        task_id = "task-789"
        expires_at = datetime.now() - timedelta(seconds=1)  # Already expired

        await cache.store_idempotency_key(key, task_id, expires_at)

        # Should return None for expired key
        retrieved_task_id = await cache.get_task_for_idempotency_key(key)
        assert retrieved_task_id is None

    @pytest.mark.asyncio
    async def test_nonexistent_idempotency_key_returns_none(self, cache):
        """Test that non-existent idempotency key returns None."""
        retrieved_task_id = await cache.get_task_for_idempotency_key("nonexistent")
        assert retrieved_task_id is None


class TestCleanup:
    """Test cache cleanup functionality."""

    @pytest.mark.asyncio
    async def test_manual_cleanup(self, cache):
        """Test manual cleanup of expired entries."""
        # Add some expired and non-expired tasks
        now = datetime.now()

        expired_task = TaskEntry(
            task_id="expired",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            expires_at=now - timedelta(minutes=1),
        )

        valid_task = TaskEntry(
            task_id="valid",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=1),
        )

        await cache.store_task(expired_task)
        await cache.store_task(valid_task)

        # Add expired idempotency key
        await cache.store_idempotency_key(
            "expired-key", "some-task", now - timedelta(minutes=1)
        )

        # Run cleanup
        stats = await cache.cleanup()

        assert stats["expired_tasks"] == 1
        assert stats["expired_idempotency_keys"] == 1
        assert stats["remaining_tasks"] == 1
        assert stats["remaining_idempotency_keys"] == 0

        # Verify valid task still exists
        assert await cache.get_task("valid") is not None
        assert await cache.get_task("expired") is None

    @pytest.mark.asyncio
    async def test_automatic_cleanup_during_operations(self, cache):
        """Test that cleanup runs automatically during certain operations."""
        # Set cleanup interval to 0 for immediate cleanup
        cache.cleanup_interval = timedelta(seconds=0)

        # Add expired task
        expired_task = TaskEntry(
            task_id="auto-expired",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=datetime.now() - timedelta(seconds=1),
        )

        await cache.store_task(expired_task)

        # This should trigger cleanup
        await cache.list_tasks()

        # Expired task should be gone
        assert await cache.get_task("auto-expired") is None


class TestConcurrency:
    """Test concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_task_storage(self, cache):
        """Test concurrent task storage doesn't cause race conditions."""

        async def store_task(task_id: str) -> bool:
            try:
                task = TaskEntry(
                    task_id=task_id,
                    task_type=TaskType.TRANSCRIPT_PROCESSING,
                    status=TaskStatus.PROCESSING,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                await cache.store_task(task)
                return True
            except ValueError:
                return False

        # Try to store 10 tasks concurrently
        tasks = [store_task(f"concurrent-{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed (different IDs)
        assert all(results)

        # Verify all tasks are stored
        stored_count = await cache.get_task_count()
        assert stored_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_task_updates(self, cache):
        """Test concurrent updates to the same task."""
        # Store initial task
        task = TaskEntry(
            task_id="update-test",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            progress=0.0,
        )
        await cache.store_task(task)

        async def update_progress(progress: float) -> None:
            current_task = await cache.get_task("update-test")
            if current_task:
                current_task.progress = progress
                current_task.message = f"Progress: {progress}"
                await cache.update_task(current_task)

        # Update task concurrently with different progress values
        updates = [update_progress(i * 0.1) for i in range(10)]
        await asyncio.gather(*updates)

        # Task should exist with some final progress
        final_task = await cache.get_task("update-test")
        assert final_task is not None
        assert 0.0 <= final_task.progress <= 0.9


class TestHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check(self, cache):
        """Test cache health check."""
        # Add some test data
        for i in range(3):
            task = TaskEntry(
                task_id=f"health-{i}",
                task_type=TaskType.TRANSCRIPT_PROCESSING,
                status=TaskStatus.PROCESSING if i < 2 else TaskStatus.COMPLETED,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(minutes=30 if i < 2 else 90),
            )
            await cache.store_task(task)

        await cache.store_idempotency_key(
            "health-key", "health-1", datetime.now() + timedelta(hours=1)
        )

        health = await cache.health_check()

        assert health["cache"] == "healthy"
        assert health["total_tasks"] == 3
        assert health["total_idempotency_keys"] == 1
        assert health["status_breakdown"]["processing"] == 2
        assert health["status_breakdown"]["completed"] == 1
        assert health["expires_within_1h"] == 2  # Two tasks expire in 30 minutes
        assert "last_cleanup" in health
        assert health["memory_usage"] == "lightweight"


class TestGlobalCacheFunctions:
    """Test global cache management functions."""

    def test_initialize_and_get_cache(self):
        """Test global cache initialization and retrieval."""
        # Initialize cache
        initialize_cache(ttl_hours=2, cleanup_interval_minutes=5)

        # Get cache instance
        cache = get_task_cache()
        assert isinstance(cache, SimpleTaskCache)
        assert cache.default_ttl == timedelta(hours=2)
        assert cache.cleanup_interval == timedelta(minutes=5)

    def test_get_cache_before_initialization_raises_error(self):
        """Test that getting cache before initialization raises error."""
        # Clear any existing cache using the reset function
        reset_cache()

        with pytest.raises(RuntimeError, match="Task cache not initialized"):
            get_task_cache()

    @pytest.mark.asyncio
    async def test_global_cleanup_function(self):
        """Test global cleanup function."""
        from backend.services.transcript.task_cache import cleanup_cache

        # Initialize cache
        initialize_cache()

        # Add expired task
        cache = get_task_cache()
        expired_task = TaskEntry(
            task_id="global-cleanup-test",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        await cache.store_task(expired_task)

        # Run global cleanup
        stats = await cleanup_cache()

        assert stats["expired_tasks"] == 1


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_cache_operations(self, cache):
        """Test operations on empty cache."""
        assert await cache.get_task_count() == 0
        assert await cache.list_tasks() == []
        assert await cache.get_task("nonexistent") is None
        assert await cache.delete_task("nonexistent") is False

        stats = await cache.cleanup()
        assert stats["expired_tasks"] == 0
        assert stats["expired_idempotency_keys"] == 0

    @pytest.mark.asyncio
    async def test_large_metadata_storage(self, cache):
        """Test storage of tasks with large metadata."""
        large_metadata = {
            "data": "x" * 10000,  # 10KB of data
            "nested": {"deep": {"structure": list(range(1000))}},
            "list_data": [{"item": i, "description": f"Item {i}"} for i in range(100)],
        }

        task = TaskEntry(
            task_id="large-metadata",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata=large_metadata,
        )

        await cache.store_task(task)
        retrieved_task = await cache.get_task("large-metadata")

        assert retrieved_task is not None
        assert retrieved_task.metadata == large_metadata

    @pytest.mark.asyncio
    async def test_task_with_none_values(self, cache):
        """Test task storage with None values."""
        task = TaskEntry(
            task_id="none-values",
            task_type=TaskType.TRANSCRIPT_PROCESSING,
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            progress=0.0,
            message="",
            result=None,
            error=None,
            error_code=None,
            metadata=None,
        )

        await cache.store_task(task)
        retrieved_task = await cache.get_task("none-values")

        assert retrieved_task is not None
        assert retrieved_task.result is None
        assert retrieved_task.error is None
        assert retrieved_task.error_code is None
        assert retrieved_task.metadata is None
