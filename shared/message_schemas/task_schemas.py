from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid

@dataclass
class NewTaskMessage:
    """
    Message sent to initiate a new task.
    """
    user_id: str
    task_description: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class TaskStatusUpdateMessage:
    """
    Message to provide updates on a task's status.
    """
    task_id: str
    status: str # e.g., RECEIVED, PLANNING, EXECUTING_STEP_N, COMPLETED, FAILED
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

@dataclass
class UserResponseMessage:
    """
    Message containing a user's response when agent is AWAITING_USER_INPUT.
    """
    task_id: str
    response_content: Any
    user_id: str

# Add more task-related schemas here as needed, e.g.,
# - TaskCompletionMessage
# - TaskFailedMessage
# - QuestionForUserMessage