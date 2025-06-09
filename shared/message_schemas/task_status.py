from enum import Enum


class TaskStatus(str, Enum):
    """Status of a task in the system."""
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    AWAITING_USER_INPUT = "AWAITING_USER_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED" 