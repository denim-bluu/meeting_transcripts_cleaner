"""Task domain protocols - defines interfaces for task management."""

from typing import Protocol, runtime_checkable

from .models import TaskEntry


@runtime_checkable
class TaskRepository(Protocol):
    """Protocol for task persistence operations."""

    async def store_task(self, task: TaskEntry) -> None:
        """Store a new task.
        
        Args:
            task: Task to store
        """
        ...

    async def get_task(self, task_id: str) -> TaskEntry | None:
        """Retrieve a task by ID.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Task if found, None otherwise
        """
        ...

    async def update_task(self, task_id: str, **updates) -> None:
        """Update task attributes.
        
        Args:
            task_id: Task to update
            **updates: Attribute updates to apply
        """
        ...