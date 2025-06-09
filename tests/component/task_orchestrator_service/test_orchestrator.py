import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC, timedelta
from uuid import uuid4

from shared.message_schemas.task_schemas import Task, TaskStatus, TaskPriority, TaskMetadata
from services.task_orchestrator_service.src.orchestrator import TaskOrchestratorService

pytestmark = pytest.mark.asyncio

@pytest.mark.asyncio
async def test_service_initialization(orchestrator_service):
    """Test service initialization."""
    assert orchestrator_service.service_name == "test-orchestrator"
    assert orchestrator_service.version == "1.0.0"
    assert len(orchestrator_service.active_tasks) == 0
    assert len(orchestrator_service._priority_queues) == 4  # LOW, MEDIUM, HIGH, CRITICAL

@pytest.mark.asyncio
async def test_service_start(orchestrator_service, mock_db_interface, mock_rabbitmq_client):
    """Test service start."""
    await orchestrator_service.start()
    
    # Verify database connection
    mock_db_interface.connect.assert_called_once()
    
    # Verify RabbitMQ setup
    assert mock_rabbitmq_client.start_consuming.call_count == 2  # One for tasks, one for user responses

@pytest.mark.asyncio
async def test_service_stop(orchestrator_service, mock_db_interface, mock_rabbitmq_client):
    """Test service stop."""
    await orchestrator_service.stop()
    
    # Verify connections are closed
    mock_db_interface.close.assert_called_once()
    mock_rabbitmq_client.close.assert_called_once()

@pytest.mark.asyncio
async def test_handle_new_task(
    orchestrator_service,
    mock_db_interface,
    mock_rabbitmq_client,
    mock_context_manager,
    mock_saga_manager,
    sample_task
):
    """Test handling a new task."""
    # Create a mock message with proper async context manager
    message = MagicMock()
    message.body = sample_task.model_dump_json().encode()
    process_mock = AsyncMock()
    process_mock.__aenter__ = AsyncMock()
    process_mock.__aexit__ = AsyncMock()
    message.process = MagicMock(return_value=process_mock)
    message.nack = AsyncMock()

    # Mock create_task to return the sample task
    mock_db_interface.create_task.return_value = sample_task

    # Handle the message
    await orchestrator_service._handle_new_task(message)

    # Verify database call
    mock_db_interface.create_task.assert_called_once_with(sample_task)

    # Verify saga creation
    mock_saga_manager.create_saga.assert_called_once()
    mock_saga_manager.execute_saga.assert_called_once()

    # Verify message publishing
    assert mock_rabbitmq_client.publish_message.call_count == 2  # One for planning, one for event

    # Verify message acknowledgment
    message.process.assert_called_once()
    process_mock.__aenter__.assert_called_once()
    process_mock.__aexit__.assert_called_once()

@pytest.mark.asyncio
async def test_is_task_timed_out(orchestrator_service, sample_task):
    """Test task timeout check."""
    # Test task that hasn't timed out
    sample_task.metadata.created_at = datetime.now(UTC)
    sample_task.metadata.timeout = 3600  # 1 hour timeout
    assert not orchestrator_service._is_task_timed_out(sample_task)
    
    # Test task that has timed out
    sample_task.metadata.created_at = datetime.now(UTC) - timedelta(hours=2)
    assert orchestrator_service._is_task_timed_out(sample_task)

@pytest.mark.asyncio
async def test_handle_task_timeout(
    orchestrator_service,
    mock_db_interface,
    mock_context_manager,
    sample_task
):
    """Test handling task timeout."""
    # Add task to active tasks
    orchestrator_service.active_tasks[sample_task.task_id] = sample_task
    
    # Set task creation time to 2 hours ago and timeout to 1 hour
    sample_task.metadata.created_at = datetime.now(UTC) - timedelta(hours=2)
    sample_task.metadata.timeout = 3600  # 1 hour timeout
    
    # Mock the total_seconds method to return a value greater than timeout
    time_elapsed = datetime.now(UTC) - sample_task.metadata.created_at
    sample_task.metadata.timeout = 3600  # 1 hour timeout
    
    # Handle timeout
    await orchestrator_service._handle_task_timeout(sample_task.task_id)
    
    # Verify task is marked as failed
    mock_db_interface.update_task.assert_called_once()
    update_call = mock_db_interface.update_task.call_args[0][0]
    assert update_call.status == TaskStatus.FAILED
    assert "timed out after" in update_call.result.get("error", "")
    
    # Verify context is updated
    mock_context_manager.update_context.assert_called_once()
    context_update = mock_context_manager.update_context.call_args[0][1]
    assert context_update["status"] == "failed"
    assert "timed out after" in context_update["error"]
    
    # Verify task is removed from active tasks
    assert sample_task.task_id not in orchestrator_service.active_tasks

@pytest.mark.asyncio
async def test_handle_task_not_timed_out(
    orchestrator_service,
    mock_db_interface,
    mock_context_manager,
    sample_task
):
    """Test handling task that hasn't timed out."""
    # Add task to active tasks
    orchestrator_service.active_tasks[sample_task.task_id] = sample_task
    
    # Set task creation time to 30 minutes ago and timeout to 1 hour
    sample_task.metadata.created_at = datetime.now(UTC) - timedelta(minutes=30)
    sample_task.metadata.timeout = 3600  # 1 hour timeout
    
    # Mock the total_seconds method to return a value less than timeout
    time_elapsed = datetime.now(UTC) - sample_task.metadata.created_at
    sample_task.metadata.timeout = 3600  # 1 hour timeout
    
    # Handle timeout
    await orchestrator_service._handle_task_timeout(sample_task.task_id)
    
    # Verify task is not updated
    mock_db_interface.update_task.assert_not_called()
    mock_context_manager.update_context.assert_not_called()
    assert sample_task.task_id in orchestrator_service.active_tasks

@pytest.mark.asyncio
async def test_update_task_status(
    orchestrator_service,
    mock_db_interface,
    mock_rabbitmq_client,
    sample_task
):
    """Test updating task status."""
    # Add task to active tasks
    orchestrator_service.active_tasks[sample_task.task_id] = sample_task
    
    # Update status
    await orchestrator_service._update_task_status(
        sample_task.task_id,
        TaskStatus.COMPLETED,
        {"result": "success"}
    )
    
    # Verify task is updated in database
    mock_db_interface.update_task.assert_called_once()
    
    # Verify task is removed from active tasks
    assert sample_task.task_id not in orchestrator_service.active_tasks

@pytest.mark.asyncio
async def test_plan_task(
    orchestrator_service,
    mock_context_manager,
    mock_rabbitmq_client,
    sample_task
):
    """Test planning a task."""
    # Plan task
    data = {"task": sample_task.model_dump()}
    result = await orchestrator_service._plan_task(data)
    
    # Verify context is updated
    mock_context_manager.update_context.assert_called_once()
    context_update = mock_context_manager.update_context.call_args[0][1]
    assert context_update["status"] == "planning"
    assert context_update["priority"] == sample_task.metadata.priority
    
    # Verify message is published
    mock_rabbitmq_client.publish_message.assert_called_once()
    assert result["status"] == "success"
    assert result["task_id"] == sample_task.task_id

@pytest.mark.asyncio
async def test_execute_task(
    orchestrator_service,
    mock_context_manager,
    mock_rabbitmq_client,
    sample_task
):
    """Test executing a task."""
    # Execute task
    data = {"task": sample_task.model_dump()}
    result = await orchestrator_service._execute_task(data)
    
    # Verify context is updated
    mock_context_manager.update_context.assert_called_once()
    context_update = mock_context_manager.update_context.call_args[0][1]
    assert context_update["status"] == "executing"
    assert context_update["priority"] == sample_task.metadata.priority
    
    # Verify message is published
    mock_rabbitmq_client.publish_message.assert_called_once()
    assert result["status"] == "success"
    assert result["task_id"] == sample_task.task_id 