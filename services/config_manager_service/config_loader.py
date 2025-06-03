import yaml
import os
from typing import Dict, Any, Optional


CONFIG_DIR = os.getenv('DEVFUION_CONFIG_DIR', os.path.join(os.path.dirname(__file__), '..', '..', 'config'))
DEFAULT_CONFIG_FILENAME = 'config.dev.yaml'
CONFIG_FILE_PATH = os.getenv('DEVFUION_CONFIG_PATH', os.path.join(CONFIG_DIR, DEFAULT_CONFIG_FILENAME))

_config: Dict[str, Any] = {}

def load_config(config_path: str = CONFIG_FILE_PATH) -> None:
    global _config
    resolved_config_path = os.path.abspath(config_path)

    try:
        with open(resolved_config_path, 'r') as f:
            _config = yaml.safe_load(f)
        print(f"Configuration loaded from {resolved_config_path}")
    except FileNotFoundError:
        print(f"WARNING: Configuration file not found at {resolved_config_path}. Using empty config.")
        _config = {}
    except yaml.YAMLError as e:
        print(f"ERROR: Could not parse configuration file {resolved_config_path}: {e}")
        _config = {}

def get_config(service_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the configuration for a specific service or the global config.
    """
    if not _config: # Ensure config is loaded at least once
        load_config() # Will use the default path logic

    if service_name:
        return _config.get(service_name, {})
    return _config

if __name__ == '__main__':
    # For testing, ensure a dummy config exists at the expected default path
    # This example assumes the 'config' dir is two levels up from this script, then in 'config/'
    test_config_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
    os.makedirs(test_config_dir, exist_ok=True)
    test_config_file = os.path.join(test_config_dir, DEFAULT_CONFIG_FILENAME)

    dummy_config_content = {
        "global_settings": {"log_level": "INFO"},
        "task_orchestrator_service": {"max_concurrent_tasks": 10},
        "llm_abstraction_service": {
            "default_provider": "ollama",
            "ollama_url": "http://localhost:11434"
        }
    }
    with open(test_config_file, 'w') as f:
        yaml.dump(dummy_config_content, f)

    # Test loading with default path logic
    load_config() # Should find it in ../../config/config.dev.yaml relative to this script's dir
    print("\nGlobal Config:", get_config())
    print("\nTask Orchestrator Config:", get_config("task_orchestrator_service"))

    # To test with environment variable override:
    # 1. Create a 'my_custom_config.yaml' somewhere with different content.
    # 2. Set DEVFUION_CONFIG_PATH environment variable to the full path of 'my_custom_config.yaml'.
    # 3. Rerun this script.
    # Example:
    # os.environ['DEVFUION_CONFIG_PATH'] = '/path/to/your/my_custom_config.yaml'
    # _config = {} # Reset to force reload
    # load_config()
    # print("\nCustom Config via ENV:", get_config())


    # Clean up dummy file (optional)
    # os.remove(test_config_file)
    # if not os.listdir(test_config_dir):
    #     os.rmdir(test_config_dir)