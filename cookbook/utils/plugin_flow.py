"""
Plugin System Flow Example: Extending Water with Plugins

This example demonstrates Water's plugin system for adding custom storage
backends, LLM providers, middleware, and integrations. It shows:
  - Creating a WaterPlugin subclass
  - Using PluginRegistry to register and discover plugins
  - Registration hooks (register_storage, register_provider, etc.)
  - Plugin lifecycle (on_load, on_unload)

NOTE: This example uses mock implementations so it runs without
      external dependencies.
"""

import asyncio
from typing import Any, Dict, List, Optional

from water.plugins import PluginRegistry, WaterPlugin, PluginType


# ---------------------------------------------------------------------------
# Example 1: Creating and registering a custom plugin
# ---------------------------------------------------------------------------

class InMemoryStoragePlugin(WaterPlugin):
    """A simple in-memory storage plugin for demonstration."""

    name = "memory_storage"
    plugin_type = PluginType.STORAGE
    version = "1.0.0"
    description = "In-memory key-value storage backend"

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._loaded = False

    def register(self, app: Any) -> None:
        """Register this storage backend with the plugin registry."""
        app.register_storage(self.name, self)

    def on_load(self) -> None:
        """Called when the plugin is first loaded."""
        self._loaded = True
        print(f"  [lifecycle] {self.name} on_load called")

    def on_unload(self) -> None:
        """Called when the plugin is unloaded."""
        self._store.clear()
        self._loaded = False
        print(f"  [lifecycle] {self.name} on_unload called")

    # Custom storage methods
    def put(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def keys(self) -> list:
        return list(self._store.keys())


async def example_basic_plugin():
    """Create and register a custom storage plugin."""
    print("=== Example 1: Custom Storage Plugin ===\n")

    registry = PluginRegistry()

    # Create and register the plugin
    storage_plugin = InMemoryStoragePlugin()
    registry.register(storage_plugin)

    # Retrieve it from the registry
    retrieved = registry.get_plugin("memory_storage")
    print(f"Plugin name:    {retrieved.name}")
    print(f"Plugin type:    {retrieved.plugin_type.value}")
    print(f"Plugin version: {retrieved.version}")
    print(f"Plugin info:    {retrieved.info()}")
    print()

    # Use the storage backend via the registry
    backend = registry.get_storage("memory_storage")
    backend.put("flow_result", {"status": "completed", "score": 0.95})
    backend.put("user_prefs", {"theme": "dark", "lang": "en"})
    print(f"Stored keys: {backend.keys()}")
    print(f"flow_result: {backend.get('flow_result')}")
    print()


# ---------------------------------------------------------------------------
# Example 2: Multiple plugin types and listing
# ---------------------------------------------------------------------------

class MockProviderPlugin(WaterPlugin):
    """A mock LLM provider plugin."""

    name = "mock_llm"
    plugin_type = PluginType.PROVIDER
    version = "0.1.0"
    description = "Mock LLM provider for testing"

    def register(self, app: Any) -> None:
        app.register_provider(self.name, self)

    async def complete(self, messages: list, **kwargs) -> dict:
        return {"text": "Mock response from plugin provider"}


class LoggingMiddlewarePlugin(WaterPlugin):
    """A logging middleware plugin."""

    name = "request_logger"
    plugin_type = PluginType.MIDDLEWARE
    version = "1.2.0"
    description = "Logs all task inputs and outputs"

    def register(self, app: Any) -> None:
        app.register_middleware(self.name, self)

    async def before_task(self, task_id: str, data: dict) -> dict:
        print(f"  [middleware] Before {task_id}: {list(data.keys())}")
        return data

    async def after_task(self, task_id: str, data: dict, result: dict) -> dict:
        print(f"  [middleware] After {task_id}: {list(result.keys())}")
        return result


class SlackIntegrationPlugin(WaterPlugin):
    """A mock Slack integration plugin."""

    name = "slack_notifier"
    plugin_type = PluginType.INTEGRATION
    version = "2.0.0"
    description = "Send flow notifications to Slack"

    def register(self, app: Any) -> None:
        app.register_integration(self.name, self)

    def notify(self, channel: str, message: str) -> dict:
        return {"channel": channel, "message": message, "sent": True}


async def example_multiple_plugins():
    """Register multiple plugin types and query the registry."""
    print("=== Example 2: Multiple Plugin Types ===\n")

    registry = PluginRegistry()

    # Register various plugins
    registry.register(InMemoryStoragePlugin())
    registry.register(MockProviderPlugin())
    registry.register(LoggingMiddlewarePlugin())
    registry.register(SlackIntegrationPlugin())

    # List all plugins
    all_plugins = registry.list_plugins()
    print(f"Total plugins: {len(all_plugins)}")
    for p in all_plugins:
        print(f"  - {p.name} ({p.plugin_type.value}) v{p.version}")
    print()

    # Filter by type
    providers = registry.list_plugins(plugin_type=PluginType.PROVIDER)
    print(f"Provider plugins: {[p.name for p in providers]}")

    storage = registry.list_plugins(plugin_type=PluginType.STORAGE)
    print(f"Storage plugins:  {[p.name for p in storage]}")

    integrations = registry.list_plugins(plugin_type=PluginType.INTEGRATION)
    print(f"Integration plugins: {[p.name for p in integrations]}")
    print()

    # Use the mock provider via registry
    provider = registry.get_provider("mock_llm")
    response = await provider.complete([{"role": "user", "content": "Hello"}])
    print(f"Provider response: {response['text']}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Plugin lifecycle and unregistration
# ---------------------------------------------------------------------------

async def example_lifecycle():
    """Demonstrate plugin load, use, and unload lifecycle."""
    print("=== Example 3: Plugin Lifecycle ===\n")

    registry = PluginRegistry()

    # Register (triggers on_load)
    print("Registering plugin...")
    storage = InMemoryStoragePlugin()
    registry.register(storage)

    # Use the plugin
    backend = registry.get_storage("memory_storage")
    backend.put("session", {"user": "alice", "active": True})
    print(f"Data stored: {backend.get('session')}")

    # Check plugin exists
    plugin = registry.get_plugin("memory_storage")
    print(f"Plugin found: {plugin is not None}")

    # Unregister (triggers on_unload)
    print("Unregistering plugin...")
    registry.unregister("memory_storage")

    # Verify it's gone
    plugin = registry.get_plugin("memory_storage")
    print(f"Plugin found after unregister: {plugin is not None}")

    # Verify duplicate registration is rejected
    print()
    new_registry = PluginRegistry()
    new_registry.register(InMemoryStoragePlugin())
    try:
        new_registry.register(InMemoryStoragePlugin())
    except ValueError as e:
        print(f"Duplicate registration caught: {e}")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_basic_plugin()
    await example_multiple_plugins()
    await example_lifecycle()
    print("All plugin examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
