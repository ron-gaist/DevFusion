import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.append(str(Path(__file__).resolve().parents[2]))
sys.path.append(str(Path(__file__).resolve().parent))

from services.task_orchestrator_service.orchestrator import TaskOrchestratorService
from shared.db_models.task_models import TaskRecord


@pytest.fixture
def mock_rabbitmq_client():
    """Create a mock RabbitMQ client."""
    client = AsyncMock()
    client.start_consuming = AsyncMock()
    client.publish_message = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest_asyncio.fixture
async def service(mock_rabbitmq_client):
    """Create a service instance with mocked dependencies."""
    with patch(
        "services.task_orchestrator_service.orchestrator.RabbitMQClient",
        return_value=mock_rabbitmq_client,
    ), patch(
        "services.task_orchestrator_service.orchestrator.DatabaseInterface"
    ) as mock_db, patch(
        "services.task_orchestrator_service.orchestrator.ContextManager"
    ) as mock_ctx:
        db_instance = mock_db.return_value
        db_instance.connect = AsyncMock()
        db_instance.get_active_tasks = AsyncMock(return_value=[])
        db_instance.create_task = AsyncMock(side_effect=lambda task: task)
        db_instance.update_task = AsyncMock()
        db_instance.close = AsyncMock()
        ctx_instance = mock_ctx.return_value
        ctx_instance.establish_context = AsyncMock()
        ctx_instance.update_context = AsyncMock()
        ctx_instance.clear_context = AsyncMock()
        service = TaskOrchestratorService()
        service.db = db_instance
        service.context_manager = ctx_instance
        try:
            yield service
        finally:
            await service.stop()


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
        task_id="test_task_1",
        user_id="test_user",
        task_description="Test task",
        status="PLANNING",
        metadata={},
    )

    # Create a mock message
    mock_message = MagicMock()
    mock_message.body = task.json().encode()
    mock_message.processed = False

    class CM:
        async def __aenter__(self_inner):
            return None

        async def __aexit__(self_inner, exc_type, exc, tb):
            await mock_message.ack()

    mock_message.process = MagicMock(return_value=CM())
    mock_message.ack = AsyncMock()

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

    # Verify message was acknowledged
    mock_message.ack.assert_called_once()


@pytest.mark.asyncio
async def test_handle_new_task_error(service, mock_rabbitmq_client):
    """Test handling a new task with error."""
    # Create an invalid message
    mock_message = MagicMock()
    mock_message.body = b"invalid json"
    mock_message.processed = False

    class CM:
        async def __aenter__(self_inner):
            return None

        async def __aexit__(self_inner, exc_type, exc, tb):
            pass

    mock_message.process = MagicMock(return_value=CM())
    mock_message.nack = AsyncMock()

    # Handle the task
    await service._handle_new_task(mock_message)

    # Verify message was nacked
    mock_message.nack.assert_called_once_with(requeue=False)


@pytest.mark.asyncio
async def test_update_task_status(service, mock_rabbitmq_client):
    """Test updating task status."""
    # Create a test task
    task = TaskRecord(
        task_id="test_task_2",
        user_id="test_user",
        task_description="Test task",
        status="PLANNING",
        metadata={},
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
    message_body = call_args["message_body"]
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


@pytest.mark.asyncio
async def test_update_task_status_completed(service, mock_rabbitmq_client):
    """Verify that completion publishes additional message."""
    task = TaskRecord(
        task_id="test_task_3",
        user_id="test_user",
        task_description="Test task",
        status="EXECUTING",
        metadata={},
    )
    service.active_tasks[task.task_id] = task

    await service._update_task_status(task.task_id, "COMPLETED", {"result": "ok"})

    # Two messages should be published: status update and completion
    assert mock_rabbitmq_client.publish_message.call_count == 2
    status_call = mock_rabbitmq_client.publish_message.call_args_list[0][1]
    completion_call = mock_rabbitmq_client.publish_message.call_args_list[1][1]

    assert status_call["routing_key"] == "task.status"
    assert completion_call["routing_key"] == "task.completed"


@pytest.mark.asyncio
async def test_update_task_status_awaiting_input(service, mock_rabbitmq_client):
    """Verify that asking user publishes question message."""
    task = TaskRecord(
        task_id="test_task_4",
        user_id="test_user",
        task_description="Test task",
        status="EXECUTING",
        metadata={},
    )
    service.active_tasks[task.task_id] = task

    await service._update_task_status(
        task.task_id,
        "AWAITING_USER_INPUT",
        {"question": "Need more info"},
    )

    # Two messages should be published: status update and question for user
    assert mock_rabbitmq_client.publish_message.call_count == 2
    status_call = mock_rabbitmq_client.publish_message.call_args_list[0][1]
    question_call = mock_rabbitmq_client.publish_message.call_args_list[1][1]

    assert status_call["routing_key"] == "task.status"
    assert question_call["routing_key"] == "task.question_for_user"


@pytest.mark.asyncio
async def test_handle_user_response(service, mock_rabbitmq_client):
    """Ensure user response is forwarded and status updated."""
    task = TaskRecord(
        task_id="test_task_5",
        user_id="test_user",
        task_description="Test task",
        status="AWAITING_USER_INPUT",
        metadata={},
    )
    service.active_tasks[task.task_id] = task

    mock_message = MagicMock()
    response = {
        "task_id": task.task_id,
        "response_content": "Here you go",
        "user_id": "test_user",
    }
    mock_message.body = json.dumps(response).encode()

    class CM:
        async def __aenter__(self_inner):
            return None

        async def __aexit__(self_inner, exc_type, exc, tb):
            await mock_message.ack()

    mock_message.process = MagicMock(return_value=CM())
    mock_message.ack = AsyncMock()

    await service._handle_user_response(mock_message)

    # Two messages: forward to capabilities engine and status update
    assert mock_rabbitmq_client.publish_message.call_count == 2
    forward_call = mock_rabbitmq_client.publish_message.call_args_list[0][1]
    status_call = mock_rabbitmq_client.publish_message.call_args_list[1][1]

    assert forward_call["routing_key"] == "task.user_response"
    assert status_call["routing_key"] == "task.status"
