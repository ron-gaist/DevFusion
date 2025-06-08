from typing import Dict, Any, Optional
from datetime import datetime, UTC

from shared.common_utils import logger


class ContextManager:
    """Manages task context and state."""

    def __init__(self):
        """Initialize context manager."""
        self._contexts: Dict[str, Dict[str, Any]] = {}

    async def establish_context(
        self, task_id: str, initial_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Establish context for a new task."""
        try:
            context = {
                "task_id": task_id,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "state": "INITIALIZED",
                "data": initial_context,
                "history": [],
            }
            self._contexts[task_id] = context
            logger.info(f"Context established for task {task_id}")
            return context
        except Exception as e:
            logger.error(f"Failed to establish context for task {task_id}: {str(e)}")
            raise

    async def update_context(
        self, task_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update context for a task."""
        if task_id not in self._contexts:
            raise KeyError(f"No context found for task {task_id}")

        try:
            context = self._contexts[task_id]
            context["data"].update(updates)
            context["updated_at"] = datetime.now(UTC)
            context["history"].append(
                {"timestamp": datetime.now(UTC), "updates": updates}
            )
            logger.info(f"Context updated for task {task_id}")
            return context
        except Exception as e:
            logger.error(f"Failed to update context for task {task_id}: {str(e)}")
            raise

    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve context for a task."""
        return self._contexts.get(task_id)

    async def clear_context(self, task_id: str):
        """Clear context for a task."""
        if task_id in self._contexts:
            del self._contexts[task_id]
            logger.info(f"Context cleared for task {task_id}")

    async def get_context_history(self, task_id: str) -> Optional[list]:
        """Get context update history for a task."""
        context = await self.get_context(task_id)
        return context["history"] if context else None
