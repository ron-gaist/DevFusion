import os
from typing import Optional
from dotenv import load_dotenv

from shared.message_schemas.task_status import TaskStatus
from shared.message_schemas.task_priority import TaskPriority

class OrchestratorSettings:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        
        # Service Configuration
        self.SERVICE_NAME = "task_orchestrator_service"
        self.SERVICE_VERSION = "1.0.0"

        # RabbitMQ Configuration
        self.RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
        self.RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "devfusion.tasks")
        self.RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "task_orchestrator_service.new_tasks")
        self.RABBITMQ_BINDING_KEYS = os.getenv("RABBITMQ_BINDING_KEYS", "task.new").split(",")

        # Task Configuration
        self.MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "10"))
        self.TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "3600"))  # 1 hour in seconds

        # Logging Configuration
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv(
            "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Database Configuration
        self.DB_HOST = os.getenv("DB_HOST", "localhost")
        self.DB_PORT = int(os.getenv("DB_PORT", "5432"))
        self.DB_NAME = os.getenv("DB_NAME", "devfusion")
        self.DB_USER = os.getenv("DB_USER", "postgres")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

        # API Configuration
        self.API_HOST = os.getenv("API_HOST", "0.0.0.0")
        self.API_PORT = int(os.getenv("API_PORT", "8000"))

    def get_database_url(self) -> str:
        """Get the database URL from environment variables."""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    def get_api_url(self) -> str:
        """Get the API URL from environment variables."""
        return f"http://{self.API_HOST}:{self.API_PORT}"

# Create a singleton instance
settings = OrchestratorSettings() 