from datetime import datetime, UTC
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, JSON, Integer, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

Base = declarative_base()


class Task(Base):
    """SQLAlchemy model for tasks."""

    __tablename__ = "tasks"

    task_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False)
    task_description = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    details = Column(JSON)
    execution_plan_id = Column(String(36))
    saga_state = Column(String(50), nullable=False, default="NOT_STARTED")
    metadata_json = Column("metadata", JSON)
    priority = Column(Integer, default=1)

    # Relationships
    history = relationship(
        "TaskHistory", back_populates="task", cascade="all, delete-orphan"
    )


class TaskHistory(Base):
    """SQLAlchemy model for task history."""

    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id"), nullable=False)
    status = Column(String(50), nullable=False)
    details = Column(JSON)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    task = relationship("Task", back_populates="history")


# Pydantic models for API and message handling
class TaskRecord(BaseModel):
    """Pydantic model for task records."""

    task_id: str
    user_id: str
    task_description: str
    status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: Optional[Dict[str, Any]] = None
    execution_plan_id: Optional[str] = None
    saga_state: str = "NOT_STARTED"
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class TaskHistoryRecord(BaseModel):
    """Pydantic model for task history records."""

    id: int
    task_id: str
    status: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Config:
        from_attributes = True
