import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from uuid import uuid4
import asyncio
from typing import AsyncGenerator

from shared.message_schemas.task_schemas import Task, TaskStatus, TaskPriority, TaskMetadata
from shared.db_models.task_models import TaskModel
from shared.common_utils.saga_manager import SagaManager
from services.task_orchestrator_service.src.orchestrator import TaskOrchestratorService
from services.task_orchestrator_service.config.env_settings import OrchestratorSettings


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
async def mock_db_interface():
    """Create a mock database interface."""
    db = AsyncMock()
    db.connection_params = {
        "host": "localhost",
        "port": 5432,
        "database": "test_db",
        "user": "test_user",
        "password": "test_password"
    }
    db.session = AsyncMock()
    db.engine = AsyncMock()
    db.session_factory = AsyncMock()
    db.pool = AsyncMock()
    
    # Mock common database operations
    db.get_active_tasks = AsyncMock(return_value=[])
    db.get_task = AsyncMock(return_value=None)
    db.create_task = AsyncMock(return_value=TaskModel(
        id="test-task-id",
        description="Test Task",
        task_metadata={
            "priority": 1,
            "timeout": 3600,
            "max_retries": 3,
            "tags": [],
            "user_id": "test-user"
        },
        status="pending",
        context={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    ))
    db.update_task = AsyncMock(return_value=None)
    db.delete_task = AsyncMock(return_value=None)
    db.list_tasks = AsyncMock(return_value=[])
    db.create_task_event = AsyncMock(return_value=None)
    db.get_task_events = AsyncMock(return_value=[])
    
    # Mock connect and close methods
    db.connect = AsyncMock()
    db.close = AsyncMock()
    
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


@pytest.fixture
def test_config():
    """Create test configuration."""
    return {
        "database": {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password"
        },
        "rabbitmq": {
            "host": "localhost",
            "port": 5672,
            "username": "guest",
            "password": "guest",
            "virtual_host": "/",
            "exchange": "test_exchange",
            "queue": "test_queue",
            "binding_keys": ["test.*"]
        }
    }


@pytest.fixture
async def orchestrator_service(mock_db_interface, mock_rabbitmq_client, test_config):
    """Create a test instance of the orchestrator service."""
    service = TaskOrchestratorService()
    service.db = mock_db_interface
    service.rabbitmq_client = mock_rabbitmq_client
    service.config = test_config
    service.task_processor = AsyncMock()
    return service


@pytest.fixture(scope="session")
def test_config():
    """Create a test configuration for task orchestrator service."""
    return {
        "version": "1.0.0",
        "service_name": "task_orchestrator_service",
        "service_version": "1.0.0",
        "rabbitmq": {
            "url": "amqp://guest:guest@localhost:5672/",
            "host": "localhost",
            "port": 5672,
            "username": "guest",
            "password": "guest",
            "exchange": "devfusion.tasks",
            "queue": "task_orchestrator_service.new_tasks",
            "binding_keys": ["task.new"]
        },
        "task": {
            "max_concurrent_tasks": 5,
            "timeout": 1800
        },
        "logging": {
            "level": "DEBUG",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "devfusion_test",
            "user": "postgres",
            "password": "postgres"
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8000
        }
    }


@pytest.fixture(scope="function")
def mock_config_manager(test_config):
    """Mock the config manager service response."""
    with patch("httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = test_config
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        yield mock_get


@pytest.fixture(scope="function")
def mock_config_manager_error():
    """Mock the config manager service error response."""
    with patch("httpx.get") as mock_get:
        mock_get.side_effect = Exception("Config service unavailable")
        yield mock_get 


@pytest.fixture(autouse=True)
def setup_test_config():
    """Setup test configuration."""
    test_config = {
        "SERVICE_NAME": "task_orchestrator_service",
        "SERVICE_VERSION": "1.0.0",
        "RABBITMQ_HOST": "localhost",
        "RABBITMQ_PORT": 5672,
        "RABBITMQ_USER": "guest",
        "RABBITMQ_PASSWORD": "guest",
        "RABBITMQ_VHOST": "/",
        "RABBITMQ_EXCHANGE": "devfusion",
        "RABBITMQ_QUEUE": "task_orchestrator",
        "RABBITMQ_BINDING_KEYS": ["task.*"],
        "MAX_CONCURRENT_TASKS": 10,
        "TASK_TIMEOUT": 3600,
        "DB_HOST": "localhost",
        "DB_PORT": 5432,
        "DB_USER": "postgres",
        "DB_PASSWORD": "postgres",
        "DB_NAME": "devfusion",
        "API_HOST": "localhost",
        "API_PORT": 8000,
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    }
    OrchestratorSettings.override_config(test_config)
    yield
    OrchestratorSettings.reset_config()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close() 