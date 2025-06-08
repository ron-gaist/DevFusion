import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from orchestrator import TaskOrchestratorService, TaskRecord, TaskStatusUpdate


@pytest.fixture
def mock_rabbitmq_client():
    """Create a mock RabbitMQ client."""
    client = AsyncMock()
    client.start_consuming = AsyncMock()
    client.publish_message = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def service(mock_rabbitmq_client):
    """Create a service instance with mocked dependencies."""
    with patch("orchestrator.RabbitMQClient", return_value=mock_rabbitmq_client):
        service = TaskOrchestratorService()
        return service


@pytest.mark.asyncio
async def test_service_initialization(service):
    """Test service initialization."""
    assert service.service_name == "task_orchestrator_service"
    assert service.version == "1.0.0"
    assert isinstance(service.active_tasks, dict)
    assert len(service.active_tasks) == 0


@pytest.mark.asyncio
async def test_service_start(service, mock_rabbitmq_client):
    """Test service start."""
    await service.start()
    mock_rabbitmq_client.start_consuming.assert_called_once()
    call_args = mock_rabbitmq_client.start_consuming.call_args[1]
    assert call_args["queue_name"] == "task_orchestrator_service.new_tasks"
    assert call_args["exchange_name"] == "devfusion.tasks"
    assert call_args["binding_keys"] == ["task.new"]


@pytest.mark.asyncio
async def test_service_stop(service, mock_rabbitmq_client):
    """Test service stop."""
    await service.stop()
    mock_rabbitmq_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_handle_new_task(service, mock_rabbitmq_client):
    """Test handling a new task."""
    # Create a test task
    task = TaskRecord(
        task_id="test_task_1", user_id="test_user", task_description="Test task"
    )

    # Create a mock message
    mock_message = MagicMock()
    mock_message.body = task.json().encode()
    mock_message.processed = False

    # Handle the task
    await service._handle_new_task(mock_message)

    # Verify task was stored
    assert task.task_id in service.active_tasks
    assert service.active_tasks[task.task_id].status == "PLANNING"

    # Verify status update was published
    mock_rabbitmq_client.publish_message.assert_called()
    status_call = mock_rabbitmq_client.publish_message.call_args_list[0]
    assert status_call[1]["exchange_name"] == "devfusion.tasks"
    assert status_call[1]["routing_key"] == "task.status"

    # Verify task was forwarded to capabilities engine
    capabilities_call = mock_rabbitmq_client.publish_message.call_args_list[1]
    assert capabilities_call[1]["exchange_name"] == "devfusion.capabilities"
    assert capabilities_call[1]["routing_key"] == "task.plan"

    # Verify message was acknowledged
    mock_message.ack.assert_called_once()


@pytest.mark.asyncio
async def test_handle_new_task_error(service, mock_rabbitmq_client):
    """Test handling a new task with error."""
    # Create an invalid message
    mock_message = MagicMock()
    mock_message.body = b"invalid json"
    mock_message.processed = False

    # Handle the task
    await service._handle_new_task(mock_message)

    # Verify message was nacked
    mock_message.nack.assert_called_once_with(requeue=False)


@pytest.mark.asyncio
async def test_update_task_status(service, mock_rabbitmq_client):
    """Test updating task status."""
    # Create a test task
    task = TaskRecord(
        task_id="test_task_2", user_id="test_user", task_description="Test task"
    )

    # Add task to active tasks
    service.active_tasks[task.task_id] = task

    # Update status
    await service._update_task_status(
        task.task_id, "EXECUTING", {"step": "1", "message": "Processing"}
    )

    # Verify task was updated
    assert service.active_tasks[task.task_id].status == "EXECUTING"

    # Verify status update was published
    mock_rabbitmq_client.publish_message.assert_called_once()
    call_args = mock_rabbitmq_client.publish_message.call_args[1]
    assert call_args["exchange_name"] == "devfusion.tasks"
    assert call_args["routing_key"] == "task.status"

    # Verify message content
    message_body = json.loads(call_args["message_body"])
    assert message_body["task_id"] == task.task_id
    assert message_body["status"] == "EXECUTING"
    assert message_body["details"]["step"] == "1"


@pytest.mark.asyncio
async def test_update_task_status_not_found(service, mock_rabbitmq_client):
    """Test updating status for non-existent task."""
    # Try to update non-existent task
    await service._update_task_status("non_existent", "EXECUTING")

    # Verify no message was published
    mock_rabbitmq_client.publish_message.assert_not_called()
