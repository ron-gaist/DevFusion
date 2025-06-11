from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum

class ConfigSource(str, Enum):
    FILE = "file"
    ENV = "env"
    CONSUL = "consul"
    AWS_PARAMETER_STORE = "aws_parameter_store"

class ConfigMetadata(BaseModel):
    version: str = Field(..., description="Configuration version")
    source: ConfigSource = Field(..., description="Source of the configuration")
    last_updated: str = Field(..., description="Last update timestamp")
    checksum: str = Field(..., description="Configuration checksum")

class ServiceConfig(BaseModel):
    name: str = Field(..., description="Service name")
    config: Dict[str, Any] = Field(default_factory=dict, description="Service configuration")
    metadata: ConfigMetadata = Field(..., description="Configuration metadata")

class GlobalConfig(BaseModel):
    services: Dict[str, ServiceConfig] = Field(default_factory=dict, description="Service configurations")
    global_settings: Dict[str, Any] = Field(default_factory=dict, description="Global settings")
    metadata: ConfigMetadata = Field(..., description="Configuration metadata")

class ConfigUpdateRequest(BaseModel):
    service_name: Optional[str] = Field(None, description="Service name to update, None for global update")
    config: Dict[str, Any] = Field(..., description="New configuration values")
    version: str = Field(..., description="New configuration version")

class ConfigUpdateResponse(BaseModel):
    success: bool = Field(..., description="Whether the update was successful")
    message: str = Field(..., description="Response message")
    new_version: str = Field(..., description="New configuration version") 