from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime, UTC
from enum import Enum
import asyncio
from dataclasses import dataclass

from shared.common_utils import logger


class SagaState(Enum):
    """States in the saga pattern."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"


@dataclass
class SagaStep:
    """Represents a step in a saga transaction."""
    name: str
    action: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
    compensation: Callable[[Dict[str, Any]], Awaitable[None]]


class SagaManager:
    """Manages distributed transactions using the saga pattern."""

    def __init__(self):
        """Initialize the saga manager."""
        self._sagas: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_saga(
        self, saga_id: str, steps: List[SagaStep], initial_data: Dict[str, Any]
    ) -> None:
        """Create a new saga."""
        async with self._lock:
            if saga_id in self._sagas:
                raise ValueError(f"Saga {saga_id} already exists")

            self._sagas[saga_id] = {
                "steps": steps,
                "current_step": 0,
                "data": initial_data,
                "status": "NOT_STARTED",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            logger.info(f"Saga {saga_id} created with {len(steps)} steps")

    async def execute_saga(self, saga_id: str) -> None:
        """Execute a saga."""
        async with self._lock:
            if saga_id not in self._sagas:
                raise ValueError(f"Saga {saga_id} not found")

            saga = self._sagas[saga_id]
            saga["status"] = "IN_PROGRESS"
            saga["updated_at"] = datetime.now(UTC)

        try:
            while saga["current_step"] < len(saga["steps"]):
                step = saga["steps"][saga["current_step"]]
                logger.info(f"Executing step {step.name} for saga {saga_id}")

                try:
                    # Execute step
                    result = await step.action(saga["data"])
                    saga["data"].update(result)
                    saga["current_step"] += 1
                    saga["updated_at"] = datetime.now(UTC)

                except Exception as e:
                    logger.error(f"Step {step.name} failed: {str(e)}")
                    await self._compensate_saga(saga_id)
                    raise

            # Saga completed successfully
            async with self._lock:
                saga["status"] = "COMPLETED"
                saga["updated_at"] = datetime.now(UTC)
            logger.info(f"Saga {saga_id} completed successfully")

        except Exception as e:
            logger.error(f"Saga {saga_id} failed: {str(e)}")
            async with self._lock:
                saga["status"] = "FAILED"
                saga["updated_at"] = datetime.now(UTC)
            raise

    async def _compensate_saga(self, saga_id: str) -> None:
        """Compensate a failed saga."""
        async with self._lock:
            if saga_id not in self._sagas:
                raise ValueError(f"Saga {saga_id} not found")

            saga = self._sagas[saga_id]
            saga["status"] = "COMPENSATING"
            saga["updated_at"] = datetime.now(UTC)

        try:
            # Compensate steps in reverse order
            for i in range(saga["current_step"] - 1, -1, -1):
                step = saga["steps"][i]
                logger.info(f"Compensating step {step.name} for saga {saga_id}")

                try:
                    await step.compensation(saga["data"])
                except Exception as e:
                    logger.error(f"Compensation for step {step.name} failed: {str(e)}")
                    # Continue with other compensations even if one fails

            async with self._lock:
                saga["status"] = "COMPENSATED"
                saga["updated_at"] = datetime.now(UTC)
            logger.info(f"Saga {saga_id} compensated successfully")

        except Exception as e:
            logger.error(f"Saga {saga_id} compensation failed: {str(e)}")
            async with self._lock:
                saga["status"] = "COMPENSATION_FAILED"
                saga["updated_at"] = datetime.now(UTC)
            raise

    async def get_saga_status(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a saga."""
        async with self._lock:
            saga = self._sagas.get(saga_id)
            if saga:
                return {
                    "status": saga["status"],
                    "current_step": saga["current_step"],
                    "total_steps": len(saga["steps"]),
                    "updated_at": saga["updated_at"],
                }
            return None

    async def get_all_sagas(self) -> Dict[str, Dict[str, Any]]:
        """Get all sagas."""
        async with self._lock:
            return {
                saga_id: {
                    "status": saga["status"],
                    "current_step": saga["current_step"],
                    "total_steps": len(saga["steps"]),
                    "updated_at": saga["updated_at"],
                }
                for saga_id, saga in self._sagas.items()
            }
