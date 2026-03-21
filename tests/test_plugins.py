"""Tests for the plugin system."""

import pytest

from water.plugins.base import WaterPlugin, PluginType
from water.plugins.registry import PluginRegistry


# --- Test plugins ---

class FakeStoragePlugin(WaterPlugin):
    name = "fake_storage"
    plugin_type = PluginType.STORAGE
    version = "1.0.0"
    description = "A fake storage plugin for testing"

    def __init__(self):
        self.loaded = False
        self.registered = False

    def on_load(self):
        self.loaded = True

    def register(self, app):
        self.registered = True
        app.register_storage("fake", {"type": "fake"})

    def on_unload(self):
        self.loaded = False


class FakeProviderPlugin(WaterPlugin):
    name = "fake_provider"
    plugin_type = PluginType.PROVIDER
    version = "0.1.0"
    description = "A fake LLM provider plugin"

    def register(self, app):
        app.register_provider("fake_llm", {"model": "fake"})


class FakeMiddlewarePlugin(WaterPlugin):
    name = "fake_middleware"
    plugin_type = PluginType.MIDDLEWARE

    def register(self, app):
        app.register_middleware("fake_mw", {"type": "transform"})


# --- Registry tests ---

def test_register_plugin():
    registry = PluginRegistry()
    plugin = FakeStoragePlugin()
    registry.register(plugin)
    assert plugin.loaded
    assert plugin.registered
    assert registry.get_plugin("fake_storage") is plugin


def test_register_duplicate_raises():
    registry = PluginRegistry()
    registry.register(FakeStoragePlugin())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeStoragePlugin())


def test_unregister_plugin():
    registry = PluginRegistry()
    plugin = FakeStoragePlugin()
    registry.register(plugin)
    registry.unregister("fake_storage")
    assert not plugin.loaded
    assert registry.get_plugin("fake_storage") is None


def test_list_plugins():
    registry = PluginRegistry()
    registry.register(FakeStoragePlugin())
    registry.register(FakeProviderPlugin())
    registry.register(FakeMiddlewarePlugin())
    assert len(registry.list_plugins()) == 3


def test_list_plugins_by_type():
    registry = PluginRegistry()
    registry.register(FakeStoragePlugin())
    registry.register(FakeProviderPlugin())
    storage_plugins = registry.list_plugins(plugin_type=PluginType.STORAGE)
    assert len(storage_plugins) == 1
    assert storage_plugins[0].name == "fake_storage"


def test_get_storage():
    registry = PluginRegistry()
    registry.register(FakeStoragePlugin())
    backend = registry.get_storage("fake")
    assert backend == {"type": "fake"}


def test_get_provider():
    registry = PluginRegistry()
    registry.register(FakeProviderPlugin())
    provider = registry.get_provider("fake_llm")
    assert provider == {"model": "fake"}


def test_get_nonexistent():
    registry = PluginRegistry()
    assert registry.get_plugin("nope") is None
    assert registry.get_storage("nope") is None
    assert registry.get_provider("nope") is None


def test_plugin_info():
    plugin = FakeStoragePlugin()
    info = plugin.info()
    assert info["name"] == "fake_storage"
    assert info["type"] == "storage"
    assert info["version"] == "1.0.0"


def test_discover_no_crash():
    """discover() should not crash even with no plugins installed."""
    registry = PluginRegistry()
    discovered = registry.discover()
    assert isinstance(discovered, list)
