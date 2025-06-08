from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime, UTC
from enum import Enum

from shared.common_utils import logger


class SagaState(Enum):
    """States in the saga pattern."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"


class SagaStep:
    """Represents a step in a saga."""

    def __init__(
        self,
        name: str,
        action: Callable[[Dict[str, Any]], Awaitable[Any]],
        compensation: Optional[Callable[[Dict[str, Any]], Awaitable[Any]]] = None,
    ):
        self.name = name
        self.action = action
        self.compensation = compensation
        self.status = "PENDING"
        self.result = None
        self.error = None


class SagaManager:
    """Manages saga pattern implementation for distributed transactions."""

    def __init__(self):
        """Initialize saga manager."""
        self._sagas: Dict[str, Dict[str, Any]] = {}

    async def create_saga(
        self, task_id: str, steps: List[SagaStep], initial_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new saga."""
        saga = {
            "task_id": task_id,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "state": SagaState.NOT_STARTED,
            "steps": steps,
            "current_step": 0,
            "data": initial_data,
            "history": [],
        }
        self._sagas[task_id] = saga
        logger.info(f"Saga created for task {task_id}")
        return saga

    async def execute_saga(self, task_id: str) -> Dict[str, Any]:
        """Execute a saga."""
        if task_id not in self._sagas:
            raise KeyError(f"No saga found for task {task_id}")

        saga = self._sagas[task_id]
        saga["state"] = SagaState.IN_PROGRESS

        try:
            while saga["current_step"] < len(saga["steps"]):
                step = saga["steps"][saga["current_step"]]
                step.status = "IN_PROGRESS"

                try:
                    # Execute step
                    result = await step.action(saga["data"])
                    step.status = "COMPLETED"
                    step.result = result

                    # Update saga state
                    saga["current_step"] += 1
                    saga["updated_at"] = datetime.now(UTC)
                    saga["history"].append(
                        {
                            "timestamp": datetime.now(UTC),
                            "step": step.name,
                            "status": "COMPLETED",
                            "result": result,
                        }
                    )

                except Exception as e:
                    step.status = "FAILED"
                    step.error = str(e)
                    await self._compensate_saga(task_id)
                    raise

            saga["state"] = SagaState.COMPLETED
            logger.info(f"Saga completed successfully for task {task_id}")
            return saga

        except Exception as e:
            saga["state"] = SagaState.FAILED
            logger.error(f"Saga failed for task {task_id}: {str(e)}")
            raise

    async def _compensate_saga(self, task_id: str):
        """Compensate a failed saga."""
        saga = self._sagas[task_id]
        saga["state"] = SagaState.COMPENSATING

        # Compensate steps in reverse order
        for step in reversed(saga["steps"][: saga["current_step"]]):
            if step.compensation:
                try:
                    await step.compensation(saga["data"])
                    saga["history"].append(
                        {
                            "timestamp": datetime.now(UTC),
                            "step": step.name,
                            "status": "COMPENSATED",
                        }
                    )
                except Exception as e:
                    logger.error(f"Compensation failed for step {step.name}: {str(e)}")
                    # Continue with other compensations even if one fails

    async def get_saga_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a saga."""
        return self._sagas.get(task_id)

    async def get_saga_history(self, task_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get history of a saga."""
        saga = self._sagas.get(task_id)
        return saga["history"] if saga else None
