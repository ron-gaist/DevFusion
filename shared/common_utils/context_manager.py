from typing import Dict, Any, Optional
from datetime import datetime, UTC
import asyncio

from shared.common_utils import logger


class ContextManager:
    """Manages context for tasks and operations."""

    def __init__(self):
        """Initialize the context manager."""
        self._contexts: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def establish_context(self, task_id: str, initial_context: Dict[str, Any]) -> None:
        """Establish a new context for a task."""
        async with self._lock:
            if task_id in self._contexts:
                logger.warning(f"Context already exists for task {task_id}, updating instead")
                self._contexts[task_id].update(initial_context)
            else:
                self._contexts[task_id] = {
                    **initial_context,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            logger.info(f"Context established for task {task_id}")

    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the context for a task."""
        async with self._lock:
            context = self._contexts.get(task_id)
            if context:
                logger.debug(f"Retrieved context for task {task_id}")
                return context
            logger.warning(f"No context found for task {task_id}")
            return None

    async def update_context(self, task_id: str, updates: Dict[str, Any]) -> None:
        """Update the context for a task."""
        async with self._lock:
            if task_id not in self._contexts:
                logger.warning(f"No context found for task {task_id}, creating new one")
                await self.establish_context(task_id, updates)
                return

            self._contexts[task_id].update(updates)
            self._contexts[task_id]["updated_at"] = datetime.now(UTC)
            logger.info(f"Context updated for task {task_id}")

    async def clear_context(self, task_id: str) -> None:
        """Clear the context for a task."""
        async with self._lock:
            if task_id in self._contexts:
                del self._contexts[task_id]
                logger.info(f"Context cleared for task {task_id}")
            else:
                logger.warning(f"No context found to clear for task {task_id}")

    async def get_all_contexts(self) -> Dict[str, Dict[str, Any]]:
        """Get all contexts."""
        async with self._lock:
            return self._contexts.copy()

    async def get_context_history(self, task_id: str) -> Optional[list]:
        """Get context update history for a task."""
        context = await self.get_context(task_id)
        return context["history"] if context else None
