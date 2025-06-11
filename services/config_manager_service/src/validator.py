from typing import Dict, Any, Optional, List
import jsonschema
from datetime import datetime
import hashlib
import json

class ConfigValidationError(Exception):
    pass

def validate_config_structure(config: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """
    Validates a configuration against a JSON schema.
    """
    try:
        jsonschema.validate(instance=config, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        raise ConfigValidationError(f"Configuration validation failed: {str(e)}")

def generate_config_checksum(config: Dict[str, Any]) -> str:
    """
    Generates a checksum for a configuration dictionary.
    """
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()

def validate_required_fields(config: Dict[str, Any], required_fields: List[str]) -> None:
    """
    Validates that all required fields are present in the configuration.
    """
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise ConfigValidationError(f"Missing required fields: {', '.join(missing_fields)}")

def validate_field_types(config: Dict[str, Any], field_types: Dict[str, type]) -> None:
    """
    Validates that fields have the correct types.
    """
    for field, expected_type in field_types.items():
        if field in config and not isinstance(config[field], expected_type):
            raise ConfigValidationError(
                f"Field '{field}' has incorrect type. Expected {expected_type.__name__}, got {type(config[field]).__name__}"
            )

def validate_numeric_ranges(config: Dict[str, Any], range_constraints: Dict[str, Dict[str, float]]) -> None:
    """
    Validates that numeric fields are within specified ranges.
    """
    for field, constraints in range_constraints.items():
        if field in config:
            value = config[field]
            if not isinstance(value, (int, float)):
                raise ConfigValidationError(f"Field '{field}' must be numeric")
            
            if 'min' in constraints and value < constraints['min']:
                raise ConfigValidationError(f"Field '{field}' must be >= {constraints['min']}")
            if 'max' in constraints and value > constraints['max']:
                raise ConfigValidationError(f"Field '{field}' must be <= {constraints['max']}")

def validate_string_patterns(config: Dict[str, Any], pattern_constraints: Dict[str, str]) -> None:
    """
    Validates that string fields match specified patterns.
    """
    import re
    for field, pattern in pattern_constraints.items():
        if field in config:
            value = config[field]
            if not isinstance(value, str):
                raise ConfigValidationError(f"Field '{field}' must be a string")
            
            if not re.match(pattern, value):
                raise ConfigValidationError(f"Field '{field}' does not match required pattern: {pattern}")

def validate_enum_values(config: Dict[str, Any], enum_constraints: Dict[str, List[Any]]) -> None:
    """
    Validates that fields have values from specified enums.
    """
    for field, allowed_values in enum_constraints.items():
        if field in config:
            value = config[field]
            if value not in allowed_values:
                raise ConfigValidationError(
                    f"Field '{field}' must be one of {allowed_values}, got {value}"
                ) 