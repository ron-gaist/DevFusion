import asyncio
import os
import yaml
import json
import hashlib
from datetime import datetime, UTC
from typing import Dict, Any, Optional, List, Set
from pathlib import Path
import aiofiles
import watchfiles
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

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
)
from shared.common_utils.logger import logger

class ConfigManager:
    def __init__(
        self,
        config_dir: str = None,
        default_config_file: str = "config.dev.yaml",
        watch_config: bool = True,
    ):
        self.config_dir = config_dir or os.getenv(
            "DEVFUSION_CONFIG_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "config"),
        )
        self.default_config_file = default_config_file
        self.config_file_path = os.getenv(
            "DEVFUSION_CONFIG_PATH",
            os.path.join(self.config_dir, self.default_config_file),
        )
        self._config: Dict[str, Any] = {}
        self._config_version: str = "0.0.0"
        self._config_checksum: str = ""
        self._config_watcher = None
        self._config_subscribers: Set[asyncio.Queue] = set()
        self._watch_config = watch_config
        self.app = FastAPI(title="Config Manager Service")
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes."""
        @self.app.get("/api/v1/config/service/{service_name}")
        async def get_service_config(service_name: str) -> ServiceConfig:
            config = self._config.get("services", {}).get(service_name, {})
            if not config:
                raise HTTPException(status_code=404, detail=f"Configuration for {service_name} not found")
            return ServiceConfig(**config)

        @self.app.get("/api/v1/config/global")
        async def get_global_config() -> GlobalConfig:
            if not self._config:
                await self.load_config()
            if not self._config.get("global_settings"):
                raise HTTPException(status_code=404, detail="Global configuration not found")
            return GlobalConfig(**self._config.get("global_settings", {}))

        @self.app.post("/api/v1/config/update")
        async def update_config(request: ConfigUpdateRequest) -> ConfigUpdateResponse:
            try:
                if request.service_name:
                    await self._update_service_config(request.service_name, request.config)
                else:
                    await self._update_global_config(request.config)
                return ConfigUpdateResponse(success=True, message="Configuration updated successfully")
            except Exception as e:
                logger.error(f"Failed to update configuration: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

    async def start(self):
        """Start the config manager service."""
        await self.load_config()
        if self._watch_config:
            await self._start_config_watcher()
        logger.info("Config Manager Service started")

    async def stop(self):
        """Stop the config manager service."""
        if self._config_watcher:
            self._config_watcher.stop()
            self._config_watcher = None
        logger.info("Config Manager Service stopped")

    async def load_config(self) -> None:
        """Load configuration from file."""
        try:
            async with aiofiles.open(self.config_file_path, "r") as f:
                content = await f.read()
                self._config = yaml.safe_load(content)
                
            # Generate metadata
            self._config_checksum = generate_config_checksum(self._config)
            self._config_version = self._config.get("version", "0.0.0")
            
            # Validate configuration
            self._validate_config()
            
            # Notify subscribers
            await self._notify_subscribers()
            
            logger.info(f"Configuration loaded from {self.config_file_path}")
        except FileNotFoundError:
            logger.warning(f"Configuration file not found at {self.config_file_path}. Using empty config.")
            self._config = {}
        except yaml.YAMLError as e:
            logger.error(f"Could not parse configuration file {self.config_file_path}: {e}")
            raise
        except ConfigValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise

    def _validate_config(self) -> None:
        """Validate the loaded configuration."""
        # Add your validation logic here
        required_fields = ["version", "services", "global_settings"]
        validate_required_fields(self._config, required_fields)

    async def get_config(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        """Get configuration for a specific service or global config."""
        if not self._config:
            await self.load_config()

        if service_name:
            return self._config.get("services", {}).get(service_name, {})
        return self._config

    async def update_config(
        self, update_request: ConfigUpdateRequest
    ) -> ConfigUpdateResponse:
        """Update configuration for a service or global settings."""
        try:
            if update_request.service_name:
                # Update service config
                if "services" not in self._config:
                    self._config["services"] = {}
                self._config["services"][update_request.service_name] = update_request.config
            else:
                # Update global config
                self._config.update(update_request.config)

            # Update version and checksum
            self._config_version = update_request.version
            self._config_checksum = generate_config_checksum(self._config)

            # Save to file
            await self._save_config()

            # Notify subscribers
            await self._notify_subscribers()

            return ConfigUpdateResponse(
                success=True,
                message="Configuration updated successfully",
                new_version=self._config_version,
            )
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _save_config(self) -> None:
        """Save current configuration to file."""
        try:
            async with aiofiles.open(self.config_file_path, "w") as f:
                await f.write(yaml.dump(self._config))
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise

    async def subscribe_to_updates(self) -> asyncio.Queue:
        """Subscribe to configuration updates."""
        queue = asyncio.Queue()
        self._config_subscribers.add(queue)
        return queue

    async def unsubscribe_from_updates(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from configuration updates."""
        self._config_subscribers.discard(queue)

    async def _notify_subscribers(self) -> None:
        """Notify all subscribers of configuration updates."""
        for queue in self._config_subscribers:
            await queue.put({
                "version": self._config_version,
                "checksum": self._config_checksum,
                "timestamp": datetime.now(UTC).isoformat(),
            })

    async def _start_config_watcher(self) -> None:
        """Start watching for configuration file changes."""
        async def on_config_change(changes):
            logger.info(f"Configuration file changed: {changes}")
            await self.load_config()

        self._config_watcher = watchfiles.watch(
            self.config_dir,
            callback=on_config_change,
            watch_filter=None,
            recursive=False,
        )

    def get_metadata(self) -> ConfigMetadata:
        """Get current configuration metadata."""
        return ConfigMetadata(
            version=self._config_version,
            source=ConfigSource.FILE,
            last_updated=datetime.now(UTC).isoformat(),
            checksum=self._config_checksum,
        )

    async def _update_service_config(self, service_name: str, config: Dict[str, Any]) -> None:
        """Update service configuration."""
        config_path = Path(self.config_dir) / "services" / f"{service_name}.yaml"
        async with aiofiles.open(config_path, 'w') as f:
            await f.write(yaml.dump(config))
        self._config["services"][service_name] = ServiceConfig(**config)
        logger.info(f"Configuration updated for {service_name}")

    async def _update_global_config(self, config: Dict[str, Any]) -> None:
        """Update global configuration."""
        config_path = Path(self.config_dir) / "global.yaml"
        async with aiofiles.open(config_path, 'w') as f:
            await f.write(yaml.dump(config))
        self._config["global_settings"] = GlobalConfig(**config)
        logger.info("Global configuration updated")

# FastAPI app setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    # Startup
    config_manager = ConfigManager()
    await config_manager.start()
    yield
    # Shutdown
    await config_manager.stop()

app = FastAPI(title="Configuration Manager Service", lifespan=lifespan)
config_manager = ConfigManager()

@app.get("/config/{service_name}")
async def get_service_config(service_name: str):
    return await config_manager.get_config(service_name)

@app.get("/config")
async def get_global_config():
    return await config_manager.get_config()

@app.post("/config/update")
async def update_config(update_request: ConfigUpdateRequest):
    return await config_manager.update_config(update_request)

@app.get("/config/metadata")
async def get_config_metadata():
    return config_manager.get_metadata()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 