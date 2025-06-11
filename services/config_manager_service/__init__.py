"""
Configuration Manager Service
Provides centralized configuration management for all DevFusion services.
"""

from .src.config_manager import ConfigManager, app
from .src.schemas import (
    ConfigSource,
    ConfigMetadata,
    ServiceConfig,
    GlobalConfig,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
)

__version__ = "0.1.0"
__all__ = [
    "ConfigManager",
    "app",
    "ConfigSource",
    "ConfigMetadata",
    "ServiceConfig",
    "GlobalConfig",
    "ConfigUpdateRequest",
    "ConfigUpdateResponse",
]
