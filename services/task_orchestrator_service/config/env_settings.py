import os
from typing import Optional, Dict, Any, List
import httpx
from pydantic_settings import BaseSettings
from pydantic import Field
from shared.message_schemas.task_status import TaskStatus
from shared.message_schemas.task_priority import TaskPriority

class OrchestratorSettings(BaseSettings):
    # Service settings
    SERVICE_NAME: str = "task_orchestrator_service"
    SERVICE_VERSION: str = "1.0.0"
    SERVICE_DESCRIPTION: str = "Task Orchestrator Service for DevFusion"
    
    # RabbitMQ settings
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    RABBITMQ_VHOST: str = "/"
    RABBITMQ_EXCHANGE: str = "devfusion"
    RABBITMQ_QUEUE: str = "task_orchestrator"
    RABBITMQ_BINDING_KEYS: List[str] = ["task.*"]
    
    # Task settings
    MAX_CONCURRENT_TASKS: int = 10
    TASK_TIMEOUT: int = 3600  # 1 hour in seconds
    
    # Database settings
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "devfusion"
    
    # API settings
    API_HOST: str = "localhost"
    API_PORT: int = 8000
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Config service settings
    CONFIG_SERVICE_URL: str = "http://config_manager:8000"
    CONFIG_SERVICE_TIMEOUT: int = 5
    
    # Override mechanism for testing
    _config_override: Optional[Dict[str, Any]] = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self._config_override:
            self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from config service."""
        try:
            response = httpx.get(
                f"{self.CONFIG_SERVICE_URL}/api/v1/config/service/task_orchestrator_service",
                timeout=self.CONFIG_SERVICE_TIMEOUT
            )
            if response.status_code == 200:
                config_data = response.json()
                for key, value in config_data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
        except Exception as e:
            # Log the error but don't raise it - use default values
            print(f"Warning: Failed to load configuration from config service: {str(e)}")
    
    @classmethod
    def override_config(cls, config: Dict[str, Any]) -> None:
        """Override configuration for testing purposes."""
        cls._config_override = config
    
    @classmethod
    def reset_config(cls) -> None:
        """Reset configuration override."""
        cls._config_override = None

    @property
    def RABBITMQ_URL(self) -> str:
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/{self.RABBITMQ_VHOST}"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def API_URL(self) -> str:
        return f"http://{self.API_HOST}:{self.API_PORT}"

# Global settings instance
settings = OrchestratorSettings() 