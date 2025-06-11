import pytest
import os
import yaml
from pathlib import Path

@pytest.fixture(scope="session")
def test_config_dir():
    """Create a test configuration directory."""
    return Path(__file__).parent / "test_configs"

@pytest.fixture(scope="session", autouse=True)
def setup_test_configs(test_config_dir):
    """Set up test configuration files."""
    os.makedirs(test_config_dir, exist_ok=True)
    
    # Create test configuration files
    config_files = {
        "valid_config.yaml": {
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
        },
        "invalid_config.yaml": {
            "services": {}  # Missing required fields
        },
        "empty_config.yaml": {}
    }
    
    for filename, content in config_files.items():
        with open(test_config_dir / filename, "w") as f:
            yaml.dump(content, f)
    
    yield
    
    # Cleanup (optional)
    # for filename in config_files:
    #     os.remove(test_config_dir / filename)
    # os.rmdir(test_config_dir) 