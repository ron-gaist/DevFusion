from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class LLMRequestMessage:
    """
    Message for requesting an action from the LLM Abstraction Layer.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    task_id: Optional[str] = None  # To correlate with the overarching agent task
    model_preferences: Optional[Dict[str, Any]] = (
        None  # e.g., {"provider": "ollama", "model": "llama3"}
    )
    context_hints: Optional[Dict[str, Any]] = None  # E.g. RAG results, history
    reply_to_topic: Optional[str] = None  # For message broker routing


@dataclass
class LLMResponseMessage:
    """
    Message containing the response from the LLM Abstraction Layer.
    """

    request_id: str  # Correlates with LLMRequestMessage.request_id
    content: str
    task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = (
        None  # e.g., tokens_used, confidence, model_used
    )
    error_details: Optional[str] = None
    alternative_outputs: Optional[List[str]] = None


# Add more LLM-related schemas as needed
