"""
Plugin base classes for Water.

Third-party packages extend WaterPlugin to add custom storage backends,
LLM providers, middleware, guardrails, and integrations.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional


class PluginType(str, Enum):
    """Supported plugin categories."""
    STORAGE = "storage"
    PROVIDER = "provider"
    MIDDLEWARE = "middleware"
    GUARDRAIL = "guardrail"
    INTEGRATION = "integration"


class WaterPlugin(ABC):
    """
    Base class for Water plugins.

    Plugins are discovered via Python entry points (``water.plugins``
    group) and registered at startup.

    Attributes:
        name: Unique plugin name.
        plugin_type: Category (storage, provider, middleware, etc.).
        version: Plugin version string.
        description: Human-readable description.
    """

    name: str = ""
    plugin_type: PluginType = PluginType.INTEGRATION
    version: str = "0.1.0"
    description: str = ""

    @abstractmethod
    def register(self, app: Any) -> None:
        """
        Register this plugin's capabilities with a Water application.

        Called once during plugin discovery. The plugin should register
        its storage backends, providers, middleware, etc.

        Args:
            app: A registry or application context that accepts registrations.
        """
        ...

    def on_load(self) -> None:
        """Called when the plugin is first loaded. Override for setup logic."""
        pass

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""
        pass

    def info(self) -> dict:
        """Return plugin metadata."""
        return {
            "name": self.name,
            "type": self.plugin_type.value,
            "version": self.version,
            "description": self.description,
        }
