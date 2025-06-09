import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, UTC

from shared.message_schemas.task_schemas import Task, TaskStatus, TaskPriority, TaskMetadata
from services.task_orchestrator_service.src.orchestrator import TaskOrchestratorService

pytestmark = pytest.mark.asyncio

@pytest.mark.asyncio
async def test_handle_invalid_message(orchestrator_service, mock_rabbitmq_client):
    """Test handling invalid message."""
    # Create an invalid message
    message = MagicMock()
    message.body = b"invalid json"
    message.nack = AsyncMock()
    
    # Handle the message
    await orchestrator_service._handle_new_task(message)
    
    # Verify message was nacked
    message.nack.assert_called_once_with(requeue=False)

@pytest.mark.asyncio
async def test_handle_max_tasks_reached(
    orchestrator_service,
    mock_db_interface,
    mock_rabbitmq_client,
    sample_task
):
    """Test handling when maximum tasks are reached."""
    # Set max tasks to 0
    orchestrator_service.max_concurrent_tasks = 0
    
    # Create a mock message
    message = MagicMock()
    message.body = sample_task.model_dump_json().encode()
    message.nack = AsyncMock()
    
    # Handle the message
    await orchestrator_service._handle_new_task(message)
    
    # Verify message was nacked
    message.nack.assert_called_once_with(requeue=True)

@pytest.mark.asyncio
async def test_handle_database_error(
    orchestrator_service,
    mock_db_interface,
    mock_rabbitmq_client,
    sample_task
):
    """Test handling database error."""
    # Make database create_task raise an exception
    mock_db_interface.create_task.side_effect = Exception("Database error")
    
    # Create a mock message
    message = MagicMock()
    message.body = sample_task.model_dump_json().encode()
    message.nack = AsyncMock()
    
    # Handle the message
    await orchestrator_service._handle_new_task(message)
    
    # Verify message was nacked
    message.nack.assert_called_once_with(requeue=True)

@pytest.mark.asyncio
async def test_handle_planning_failure(
    orchestrator_service,
    mock_context_manager,
    mock_rabbitmq_client,
    sample_task
):
    """Test handling planning failure."""
    # Make RabbitMQ publish_message raise an exception
    mock_rabbitmq_client.publish_message.side_effect = Exception("Publish error")

    # Plan task
    data = {"task": sample_task.model_dump()}
    with pytest.raises(Exception) as exc_info:
        await orchestrator_service._plan_task(data)
    
    assert "Publish error" in str(exc_info.value)
    
    # Verify saga compensation was called
    mock_context_manager.update_context.assert_called_once()
    context_update = mock_context_manager.update_context.call_args[0][1]
    assert "error" in context_update
    assert "Publish error" in context_update["error"]

@pytest.mark.asyncio
async def test_handle_execution_failure(
    orchestrator_service,
    mock_context_manager,
    mock_rabbitmq_client,
    sample_task
):
    """Test handling execution failure."""
    # Make RabbitMQ publish_message raise an exception
    mock_rabbitmq_client.publish_message.side_effect = Exception("Publish error")

    # Execute task
    data = {"task": sample_task.model_dump()}
    with pytest.raises(Exception) as exc_info:
        await orchestrator_service._execute_task(data)
    
    assert "Publish error" in str(exc_info.value)
    
    # Verify saga compensation was called
    mock_context_manager.update_context.assert_called_once()
    context_update = mock_context_manager.update_context.call_args[0][1]
    assert "error" in context_update
    assert "Publish error" in context_update["error"]

@pytest.mark.asyncio
async def test_update_nonexistent_task(
    orchestrator_service,
    mock_db_interface,
    mock_rabbitmq_client
):
    """Test updating status of nonexistent task."""
    # Update status of nonexistent task
    with pytest.raises(ValueError) as exc_info:
        await orchestrator_service._update_task_status(
            "nonexistent-task",
            TaskStatus.COMPLETED,
            {"result": "success"}
        )
    
    assert "Task nonexistent-task not found" in str(exc_info.value)
    
    # Verify no database update was attempted
    mock_db_interface.update_task.assert_not_called()
    
    # Verify no message was published
    mock_rabbitmq_client.publish_message.assert_not_called() 