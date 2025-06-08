import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime

from shared.db_models.task_models import TaskRecord
from shared.common_utils import logger


class DatabaseInterface:
    """Interface for database operations."""

    def __init__(self, connection_params: Dict[str, Any]):
        """Initialize database interface."""
        self.connection_params = connection_params
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool."""
        try:
            self.pool = await asyncpg.create_pool(**self.connection_params)
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {str(e)}")
            raise

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def create_task(self, task: TaskRecord) -> TaskRecord:
        """Create a new task record."""
        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO tasks (
                    task_id, user_id, task_description, status,
                    created_at, updated_at, details, execution_plan_id,
                    saga_state, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
            """
            row = await conn.fetchrow(
                query,
                task.task_id,
                task.user_id,
                task.task_description,
                task.status,
                task.created_at,
                task.updated_at,
                task.details,
                task.execution_plan_id,
                task.saga_state,
                task.metadata,
            )
            return TaskRecord(**dict(row))

    async def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE task_id = $1", task_id)
            return TaskRecord(**dict(row)) if row else None

    async def update_task(self, task: TaskRecord) -> TaskRecord:
        """Update a task record."""
        async with self.pool.acquire() as conn:
            query = """
                UPDATE tasks
                SET status = $1, updated_at = $2, details = $3,
                    execution_plan_id = $4, saga_state = $5, metadata = $6
                WHERE task_id = $7
                RETURNING *
            """
            row = await conn.fetchrow(
                query,
                task.status,
                task.updated_at,
                task.details,
                task.execution_plan_id,
                task.saga_state,
                task.metadata,
                task.task_id,
            )
            return TaskRecord(**dict(row))

    async def get_active_tasks(self) -> List[TaskRecord]:
        """Get all active tasks."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM tasks WHERE status NOT IN ('COMPLETED', 'FAILED')"
            )
            return [TaskRecord(**dict(row)) for row in rows]

    async def get_tasks_by_user(self, user_id: str) -> List[TaskRecord]:
        """Get all tasks for a specific user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM tasks WHERE user_id = $1", user_id)
            return [TaskRecord(**dict(row)) for row in rows]
