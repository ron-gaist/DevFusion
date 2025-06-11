import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from shared.db_models.task_models import TaskRecord, TaskModel, TaskEventModel, Task, TaskMetadata
from shared.common_utils import logger


class DatabaseInterface:
    """Interface for database operations."""

    def __init__(self, connection_params: dict):
        """Initialize database interface."""
        self.connection_params = connection_params
        self.pool = None
        self.engine = None
        self.session_factory = None
        self.session = None

    async def connect(self):
        """Create database connection pool"""
        try:
            # Create async engine
            database_url = f"postgresql+asyncpg://{self.connection_params['user']}:{self.connection_params['password']}@{self.connection_params['host']}:{self.connection_params['port']}/{self.connection_params.get('database', self.connection_params.get('name', 'postgres'))}"
            self.engine = create_async_engine(
                database_url,
                pool_size=5,
                max_overflow=10,
                echo=False
            )
            self.async_session = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {str(e)}")
            raise

    async def close(self):
        """Close database connection pool"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            
            if self.engine:
                await self.engine.dispose()
                self.engine = None
                
            logger.info("Database connection pool closed successfully")
        except Exception as e:
            logger.error(f"Failed to close database connection pool: {str(e)}")
            raise

    async def __aenter__(self):
        """Context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.close()

    async def create_task(self, task: Task) -> TaskModel:
        """Create a new task in the database."""
        try:
            task_model = TaskModel(
                id=task.task_id,
                description=task.description,
                task_metadata=task.metadata.model_dump(),
                status=task.status,
                context=task.context,
                result=task.result,
                error=task.error
            )
            self.session.add(task_model)
            await self.session.commit()
            return task_model
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating task: {str(e)}")
            raise

    async def get_task(self, task_id: str) -> Optional[TaskModel]:
        """Get a task by ID."""
        try:
            result = await self.session.execute(
                select(TaskModel).where(TaskModel.id == task_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting task: {str(e)}")
            raise

    async def update_task(self, task: Task) -> Optional[TaskModel]:
        """Update a task in the database."""
        try:
            task_model = await self.get_task(task.task_id)
            if task_model:
                task_model.description = task.description
                task_model.task_metadata = task.metadata.model_dump()
                task_model.status = task.status
                task_model.context = task.context
                task_model.result = task.result
                task_model.error = task.error
                await self.session.commit()
            return task_model
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating task: {str(e)}")
            raise

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task from the database."""
        try:
            task_model = await self.get_task(task_id)
            if task_model:
                await self.session.delete(task_model)
                await self.session.commit()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting task: {str(e)}")
            raise

    async def list_tasks(self, limit: int = 100, offset: int = 0) -> List[TaskModel]:
        """List tasks with pagination."""
        try:
            result = await self.session.execute(
                select(TaskModel)
                .order_by(TaskModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error listing tasks: {str(e)}")
            raise

    async def create_task_event(self, task_id: str, event_type: str, details: dict) -> TaskEventModel:
        """Create a new task event."""
        try:
            event = TaskEventModel(
                task_id=task_id,
                event_type=event_type,
                details=details
            )
            self.session.add(event)
            await self.session.commit()
            return event
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating task event: {str(e)}")
            raise

    async def get_task_events(self, task_id: str) -> List[TaskEventModel]:
        """Get all events for a task."""
        try:
            result = await self.session.execute(
                select(TaskEventModel)
                .where(TaskEventModel.task_id == task_id)
                .order_by(TaskEventModel.timestamp.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting task events: {str(e)}")
            raise

    async def get_active_tasks(self) -> List[TaskModel]:
        """Get all active tasks."""
        try:
            result = await self.session.execute(
                select(TaskModel)
                .where(TaskModel.status.in_(["PENDING", "PLANNING", "EXECUTING"]))
                .order_by(TaskModel.created_at.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting active tasks: {str(e)}")
            raise

    async def get_tasks_by_user(self, user_id: str) -> List[TaskRecord]:
        """Get all tasks for a specific user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM tasks WHERE user_id = $1", user_id)
            return [TaskRecord(**dict(row)) for row in rows]
