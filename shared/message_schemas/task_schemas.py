from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from datetime import datetime, UTC
import uuid
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from .task_status import TaskStatus
from .task_priority import TaskPriority


class TaskMetadata(BaseModel):
    """Metadata for a task."""
    model_config = ConfigDict(from_attributes=True)
    
    priority: TaskPriority = TaskPriority.MEDIUM
    timeout: int = 3600  # Default timeout in seconds
    max_retries: int = 3
    tags: List[str] = Field(default_factory=list)
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Task(BaseModel):
    """Task model."""
    model_config = ConfigDict(from_attributes=True)
    
    task_id: str
    description: str
    metadata: TaskMetadata
    status: TaskStatus = TaskStatus.PENDING
    context: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class NewTaskMessage(BaseModel):
    """Message for creating a new task."""
    model_config = ConfigDict(from_attributes=True)
    
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    metadata: TaskMetadata
    context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskStatusUpdateMessage(BaseModel):
    """Message for task status updates."""
    task_id: str
    status: TaskStatus
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class TaskResultMessage(BaseModel):
    """Message for task results."""
    task_id: str
    result: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class TaskErrorMessage(BaseModel):
    """Message for task errors."""
    task_id: str
    error: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class QuestionForUserMessage(BaseModel):
    """Message for requesting user input."""
    model_config = ConfigDict(from_attributes=True)
    
    task_id: str
    question: str
    context: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserResponseMessage(BaseModel):
    """Message for user responses."""
    task_id: str
    response: Any
    context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class TaskEventMessage(BaseModel):
    """Message for structured task events."""
    task_id: str
    event_type: str  # e.g., "PLAN_GENERATED", "STEP_INITIATED", "TOOL_INVOKED"
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class TaskMetricsMessage(BaseModel):
    """Message for task metrics."""
    task_id: str
    metrics: Dict[str, Any]  # e.g., {"processing_time": 1.5, "memory_usage": 100}
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


@dataclass
class TaskCompletedMessage:
    """Message published when a task finishes successfully."""

    task_id: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class TaskFailedMessage:
    """Message published when a task fails."""

    task_id: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class QuestionForUserMessage:
    """Message asking the user for additional input."""

    task_id: str
    question: str
    user_id: str


# Additional task-related schemas can be defined here as needed, e.g.,
# ``QuestionForUserMessage`` for interactive workflows.
