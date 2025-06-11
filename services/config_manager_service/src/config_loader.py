import os
import yaml
import json
from typing import Dict, Any, Optional
from pathlib import Path
import aiofiles
import asyncio
from watchfiles import watch
from .schemas import ServiceConfig, GlobalConfig

class ConfigLoader:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.service_configs: Dict[str, ServiceConfig] = {}
        self.global_config: Optional[GlobalConfig] = None
        self._watch_task: Optional[asyncio.Task] = None

    async def load_config(self) -> None:
        """Load all configuration files."""
        await self.load_global_config()
        await self.load_service_configs()

    async def load_global_config(self) -> None:
        """Load global configuration."""
        global_config_path = self.config_dir / "global.yaml"
        if global_config_path.exists():
            async with aiofiles.open(global_config_path, 'r') as f:
                content = await f.read()
                config_data = yaml.safe_load(content)
                self.global_config = GlobalConfig(**config_data)

    async def load_service_configs(self) -> None:
        """Load all service configurations."""
        services_dir = self.config_dir / "services"
        if not services_dir.exists():
            return

        for service_file in services_dir.glob("*.yaml"):
            service_name = service_file.stem
            async with aiofiles.open(service_file, 'r') as f:
                content = await f.read()
                config_data = yaml.safe_load(content)
                self.service_configs[service_name] = ServiceConfig(**config_data)

    async def get_service_config(self, service_name: str) -> Optional[ServiceConfig]:
        """Get configuration for a specific service."""
        return self.service_configs.get(service_name)

    async def get_global_config(self) -> Optional[GlobalConfig]:
        """Get global configuration."""
        return self.global_config

    async def start_watching(self) -> None:
        """Start watching configuration files for changes."""
        async def watch_config():
            async for changes in watch(self.config_dir):
                await self.load_config()

        self._watch_task = asyncio.create_task(watch_config())

    async def stop_watching(self) -> None:
        """Stop watching configuration files."""
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

# Global instance
_config_loader = ConfigLoader()

async def get_config(service_name: str) -> Optional[ServiceConfig]:
    """Get configuration for a specific service."""
    return await _config_loader.get_service_config(service_name)

async def get_global_config() -> Optional[GlobalConfig]:
    """Get global configuration."""
    return await _config_loader.get_global_config()

async def initialize_config(config_dir: str = "config") -> None:
    """Initialize the configuration loader."""
    _config_loader.config_dir = Path(config_dir)
    await _config_loader.load_config()
    await _config_loader.start_watching()

async def shutdown_config() -> None:
    """Shutdown the configuration loader."""
    await _config_loader.stop_watching() 