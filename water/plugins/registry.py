"""
Plugin registry for Water.

Discovers, loads, and manages plugins from Python entry points
and manual registration.
"""

import logging
from typing import Any, Dict, List, Optional, Type

from water.plugins.base import WaterPlugin, PluginType

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Central registry for discovering and loading plugins.

    Plugins can be:
    1. Discovered from entry points (``water.plugins`` group)
    2. Registered manually via ``register()``

    Example::

        registry = PluginRegistry()
        registry.discover()  # scans entry points
        print(registry.list_plugins())
    """

    def __init__(self):
        self._plugins: Dict[str, WaterPlugin] = {}
        self._storage: Dict[str, Any] = {}
        self._providers: Dict[str, Any] = {}
        self._middleware: Dict[str, Any] = {}
        self._guardrails: Dict[str, Any] = {}
        self._integrations: Dict[str, Any] = {}

    def discover(self) -> List[WaterPlugin]:
        """
        Scan Python entry points for installed plugins.

        Looks for the ``water.plugins`` entry point group.
        Returns list of discovered and loaded plugins.
        """
        discovered = []
        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            # Python 3.12+ returns a SelectableGroups or dict-like
            if hasattr(eps, "select"):
                water_eps = eps.select(group="water.plugins")
            elif isinstance(eps, dict):
                water_eps = eps.get("water.plugins", [])
            else:
                water_eps = [ep for ep in eps if ep.group == "water.plugins"]

            for ep in water_eps:
                try:
                    plugin_cls = ep.load()
                    if isinstance(plugin_cls, type) and issubclass(plugin_cls, WaterPlugin):
                        plugin = plugin_cls()
                        self.register(plugin)
                        discovered.append(plugin)
                        logger.info(f"Discovered plugin: {plugin.name}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin entry point {ep.name}: {e}")
        except ImportError:
            logger.debug("importlib.metadata not available, skipping entry point discovery")

        return discovered

    def register(self, plugin: WaterPlugin) -> None:
        """
        Register a plugin manually.

        Args:
            plugin: A WaterPlugin instance.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.name}")

        plugin.on_load()
        plugin.register(self)
        self._plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name} ({plugin.plugin_type.value})")

    def unregister(self, name: str) -> None:
        """Unregister and unload a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.on_unload()
            logger.info(f"Unregistered plugin: {name}")

    def get_plugin(self, name: str) -> Optional[WaterPlugin]:
        """Get a registered plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> List[WaterPlugin]:
        """
        List all registered plugins, optionally filtered by type.

        Args:
            plugin_type: Filter by plugin type (storage, provider, etc.).

        Returns:
            List of registered WaterPlugin instances.
        """
        plugins = list(self._plugins.values())
        if plugin_type:
            plugins = [p for p in plugins if p.plugin_type == plugin_type]
        return plugins

    # --- Registration hooks for plugins ---

    def register_storage(self, name: str, backend: Any) -> None:
        """Register a storage backend (called by storage plugins)."""
        self._storage[name] = backend

    def register_provider(self, name: str, provider: Any) -> None:
        """Register an LLM provider (called by provider plugins)."""
        self._providers[name] = provider

    def register_middleware(self, name: str, middleware: Any) -> None:
        """Register a middleware (called by middleware plugins)."""
        self._middleware[name] = middleware

    def register_guardrail(self, name: str, guardrail: Any) -> None:
        """Register a guardrail (called by guardrail plugins)."""
        self._guardrails[name] = guardrail

    def register_integration(self, name: str, integration: Any) -> None:
        """Register an integration (called by integration plugins)."""
        self._integrations[name] = integration

    def get_storage(self, name: str) -> Optional[Any]:
        """Get a registered storage backend."""
        return self._storage.get(name)

    def get_provider(self, name: str) -> Optional[Any]:
        """Get a registered LLM provider."""
        return self._providers.get(name)
