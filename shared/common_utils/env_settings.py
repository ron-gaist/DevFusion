import os
from dotenv import load_dotenv, find_dotenv
from typing import Dict, Any

class SingletonMeta(type):
    _instance: Dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instance:
            instance = super().__call__(*args, **kwargs)
            cls._instance[cls] = instance
        return cls._instance[cls]


class EnvironmentSettings(metaclass=SingletonMeta):
    _loaded: bool = False

    def __init__(self) -> None:
        if not EnvironmentSettings._loaded:
            dotenv_path = find_dotenv(usecwd=True, raise_error_if_not_found=True)
            load_dotenv(dotenv_path=dotenv_path, override=True)
            EnvironmentSettings._loaded = True

    def require(self, key: str, var_type: type = str) -> Any:
        value: Any
        raw_value = os.getenv(key)

        if raw_value is None:
            raise ValueError(f"Required environment variable '{key}' is not set.")

        if var_type == str:
            value = raw_value
        elif var_type == int:
            try:
                value = int(raw_value)
            except ValueError:
                raise ValueError(
                    f"Required environment variable '{key}' with value '{raw_value}' could not be cast to int."
                )
        elif var_type == bool:
            val_lower = raw_value.lower()
            if val_lower in ('true', '1', 't', 'y', 'yes', 'on'):
                value = True
            elif val_lower in ('false', '0', 'f', 'n', 'no', 'off'):
                value = False
            else:
                raise ValueError(
                    f"Required environment variable '{key}' with value '{raw_value}' could not be reliably cast to bool."
                )
        else:
            raise TypeError(f"Unsupported type '{var_type.__name__}' for require method. Use str, int, or bool.")

        return value


env_settings = EnvironmentSettings()
