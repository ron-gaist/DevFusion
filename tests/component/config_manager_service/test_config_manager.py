import os
import pytest
import yaml
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from services.config_manager_service import (
    ConfigManager,
    ConfigSource,
    ConfigMetadata,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
)
from services.config_manager_service.src.validator import ConfigValidationError

# Test fixtures
@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory for test configuration files."""
    return tmp_path

@pytest.fixture
def test_config_file(temp_config_dir):
    """Create a test configuration file."""
    config_path = temp_config_dir / "test_config.yaml"
    config_content = {
        "version": "0.1.0",
        "services": {
            "test_service": {
                "setting1": "value1",
                "setting2": 42
            }
        },
        "global_settings": {
            "log_level": "INFO",
            "debug": True
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(config_content, f)
    return config_path

@pytest.fixture
async def config_manager(temp_config_dir, test_config_file):
    """Create a ConfigManager instance for testing."""
    manager = ConfigManager(
        config_dir=str(temp_config_dir),
        default_config_file=test_config_file.name,
        watch_config=False  # Disable file watching for tests
    )
    await manager.start()
    yield manager
    await manager.stop()

# Test cases
@pytest.mark.asyncio
async def test_load_config(config_manager, test_config_file):
    """Test loading configuration from file."""
    config = await config_manager.get_config()
    assert config["version"] == "0.1.0"
    assert "test_service" in config["services"]
    assert config["services"]["test_service"]["setting1"] == "value1"
    assert config["services"]["test_service"]["setting2"] == 42
    assert config["global_settings"]["log_level"] == "INFO"
    assert config["global_settings"]["debug"] is True

@pytest.mark.asyncio
async def test_get_service_config(config_manager):
    """Test getting configuration for a specific service."""
    service_config = await config_manager.get_config("test_service")
    assert service_config["setting1"] == "value1"
    assert service_config["setting2"] == 42

@pytest.mark.asyncio
async def test_get_nonexistent_service_config(config_manager):
    """Test getting configuration for a non-existent service."""
    service_config = await config_manager.get_config("nonexistent_service")
    assert service_config == {}

@pytest.mark.asyncio
async def test_update_service_config(config_manager):
    """Test updating configuration for a service."""
    update_request = ConfigUpdateRequest(
        service_name="test_service",
        config={"new_setting": "new_value"},
        version="0.1.1"
    )
    response = await config_manager.update_config(update_request)
    assert response.success is True
    assert response.new_version == "0.1.1"

    # Verify the update
    service_config = await config_manager.get_config("test_service")
    assert service_config["new_setting"] == "new_value"

@pytest.mark.asyncio
async def test_update_global_config(config_manager):
    """Test updating global configuration."""
    update_request = ConfigUpdateRequest(
        service_name=None,
        config={"global_settings": {"new_global": "value"}},
        version="0.1.1"
    )
    response = await config_manager.update_config(update_request)
    assert response.success is True

    # Verify the update
    config = await config_manager.get_config()
    assert config["global_settings"]["new_global"] == "value"

@pytest.mark.asyncio
async def test_config_metadata(config_manager):
    """Test getting configuration metadata."""
    metadata = config_manager.get_metadata()
    assert isinstance(metadata, ConfigMetadata)
    assert metadata.source == ConfigSource.FILE
    assert metadata.version == "0.1.0"
    assert isinstance(metadata.last_updated, str)
    assert isinstance(metadata.checksum, str)

@pytest.mark.asyncio
async def test_config_subscription(config_manager):
    """Test configuration update subscription."""
    queue = await config_manager.subscribe_to_updates()
    
    # Make an update
    update_request = ConfigUpdateRequest(
        service_name="test_service",
        config={"sub_test": "value"},
        version="0.1.2"
    )
    await config_manager.update_config(update_request)
    
    # Check the notification
    update = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert update["version"] == "0.1.2"
    assert "checksum" in update
    assert "timestamp" in update

@pytest.mark.asyncio
async def test_invalid_config_validation(temp_config_dir):
    """Test validation of invalid configuration."""
    # Create an invalid config file
    invalid_config_path = temp_config_dir / "invalid_config.yaml"
    invalid_config = {
        "services": {},  # Missing required 'version' and 'global_settings'
    }
    with open(invalid_config_path, "w") as f:
        yaml.dump(invalid_config, f)

    # Create manager with invalid config
    manager = ConfigManager(
        config_dir=str(temp_config_dir),
        default_config_file=invalid_config_path.name,
        watch_config=False
    )

    # Should raise validation error
    with pytest.raises(ConfigValidationError):
        await manager.start()

@pytest.mark.asyncio
async def test_config_file_not_found(temp_config_dir):
    """Test behavior when configuration file is not found."""
    manager = ConfigManager(
        config_dir=str(temp_config_dir),
        default_config_file="nonexistent.yaml",
        watch_config=False
    )
    await manager.start()
    
    # Should return empty config
    config = await manager.get_config()
    assert config == {}

@pytest.mark.asyncio
async def test_config_file_change(config_manager, test_config_file):
    """Test handling of configuration file changes."""
    # Modify the config file
    with open(test_config_file, "r") as f:
        config = yaml.safe_load(f)
    
    config["version"] = "0.1.3"
    config["services"]["test_service"]["setting1"] = "updated_value"
    
    with open(test_config_file, "w") as f:
        yaml.dump(config, f)
    
    # Reload config
    await config_manager.load_config()
    
    # Verify changes
    service_config = await config_manager.get_config("test_service")
    assert service_config["setting1"] == "updated_value"
    assert config_manager._config_version == "0.1.3" 