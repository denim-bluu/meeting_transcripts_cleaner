"""Repository implementation wrapping existing task cache."""

from .cache import get_task_cache
from .models import TaskEntry


class InMemoryTaskRepository:
    """Repository implementation using in-memory cache."""

    def __init__(self):
        self._cache = get_task_cache()

    async def store_task(self, task: TaskEntry) -> None:
        await self._cache.store_task(task)

    async def get_task(self, task_id: str) -> TaskEntry | None:
        return await self._cache.get_task(task_id)

    async def update_task(self, task_id: str, **updates) -> None:
        task = await self._cache.get_task(task_id)
        if task:
            # Update task attributes
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            await self._cache.update_task(task)
