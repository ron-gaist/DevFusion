import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, UTC
from uuid import uuid4

from shared.message_schemas.task_schemas import Task, TaskStatus, TaskPriority, TaskMetadata
from shared.db_models.db_interface import DatabaseInterface
from shared.common_utils import RabbitMQClient, ContextManager, SagaManager

from services.task_orchestrator_service.src.orchestrator import TaskOrchestratorService
from services.task_orchestrator_service.config.env_settings import settings


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    return MagicMock(
        SERVICE_NAME="test-orchestrator",
        SERVICE_VERSION="1.0.0",
        RABBITMQ_URL="amqp://guest:guest@localhost:5672/",
        DB_HOST="localhost",
        DB_PORT=5432,
        DB_NAME="test_db",
        DB_USER="test_user",
        DB_PASSWORD="test_password",
        RABBITMQ_QUEUE="test-queue",
        RABBITMQ_EXCHANGE="test-exchange",
        RABBITMQ_BINDING_KEYS=["test.*"],
        MAX_CONCURRENT_TASKS=10,
    )


@pytest.fixture
def mock_rabbitmq_client():
    """Mock RabbitMQ client for testing."""
    client = AsyncMock()
    client.start_consuming = AsyncMock()
    client.publish_message = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_db_interface():
    """Mock database interface for testing."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    db.create_task = AsyncMock()
    db.update_task = AsyncMock()
    db.get_active_tasks = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_context_manager():
    """Mock context manager for testing."""
    manager = AsyncMock()
    manager.establish_context = AsyncMock()
    manager.get_context = AsyncMock()
    manager.update_context = AsyncMock()
    manager.clear_context = AsyncMock()
    return manager


@pytest.fixture
def mock_saga_manager():
    """Mock saga manager for testing."""
    manager = AsyncMock()
    manager.create_saga = AsyncMock()
    manager.execute_saga = AsyncMock()
    manager.compensate_saga = AsyncMock()
    return manager


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        task_id=str(uuid4()),
        description="Test task description",
        metadata=TaskMetadata(
            priority=TaskPriority.MEDIUM,
            user_id="test_user",
            timeout=3600,
            max_retries=3,
            tags=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        ),
        status=TaskStatus.PENDING,
        context={},
        result={}
    )


@pytest_asyncio.fixture
async def orchestrator_service(
    mock_settings,
    mock_rabbitmq_client,
    mock_db_interface,
    mock_context_manager,
    mock_saga_manager,
    monkeypatch
):
    """Create an orchestrator service instance with mocked dependencies."""
    # Patch settings
    monkeypatch.setattr("services.task_orchestrator_service.src.orchestrator.settings", mock_settings)
    
    # Create service instance
    service = TaskOrchestratorService()
    
    # Replace dependencies with mocks
    service.rabbitmq_client = mock_rabbitmq_client
    service.db = mock_db_interface
    service.context_manager = mock_context_manager
    service.saga_manager = mock_saga_manager
    
    return service 