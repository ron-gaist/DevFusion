import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Service Configuration
SERVICE_NAME = "task_orchestrator_service"
SERVICE_VERSION = "1.0.0"

# RabbitMQ Configuration
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "devfusion.tasks")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "task_orchestrator_service.new_tasks")
RABBITMQ_BINDING_KEYS = os.getenv("RABBITMQ_BINDING_KEYS", "task.new").split(",")

# Task Configuration
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "10"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "3600"))  # 1 hour in seconds

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv(
    "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Database Configuration (if needed in the future)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "devfusion")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# API Configuration (if needed in the future)
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))


# Task Status Constants
class TaskStatus:
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    AWAITING_USER_INPUT = "AWAITING_USER_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Task Priority Constants
class TaskPriority:
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


def get_database_url() -> str:
    """Get the database URL from environment variables."""
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def get_api_url() -> str:
    """Get the API URL from environment variables."""
    return f"http://{API_HOST}:{API_PORT}"
