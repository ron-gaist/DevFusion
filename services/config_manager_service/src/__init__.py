"""
Configuration Manager Service Source Package
Contains the core implementation of the configuration management service.
"""

from .config_manager import ConfigManager, app
from .schemas import (
    ConfigSource,
    ConfigMetadata,
    ServiceConfig,
    GlobalConfig,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
)
from .validator import (
    ConfigValidationError,
    validate_config_structure,
    generate_config_checksum,
    validate_required_fields,
    validate_field_types,
    validate_numeric_ranges,
    validate_string_patterns,
    validate_enum_values,
)
from .config_loader import (
    get_config,
    get_global_config,
    initialize_config,
    shutdown_config
)

__all__ = [
    # Main components
    "ConfigManager",
    "app",
    
    # Schemas
    "ConfigSource",
    "ConfigMetadata",
    "ServiceConfig",
    "GlobalConfig",
    "ConfigUpdateRequest",
    "ConfigUpdateResponse",
    
    # Validation
    "ConfigValidationError",
    "validate_config_structure",
    "generate_config_checksum",
    "validate_required_fields",
    "validate_field_types",
    "validate_numeric_ranges",
    "validate_string_patterns",
    "validate_enum_values",

    # Config Loader
    "get_config",
    "get_global_config",
    "initialize_config",
    "shutdown_config"
] 