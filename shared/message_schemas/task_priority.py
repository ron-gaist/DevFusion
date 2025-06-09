from enum import Enum


class TaskPriority(str, Enum):
    """Priority levels for tasks."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL" 