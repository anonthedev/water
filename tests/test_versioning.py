"""Tests for flow versioning and migration system."""

import pytest

from water.core.versioning import (
    FlowVersion,
    SchemaChange,
    CompatibilityChecker,
    SchemaRegistry,
    MigrationStep,
    snapshot_flow_schemas,
)
from water.core.task import create_task
from water.core.flow import Flow
from pydantic import BaseModel


# --- FlowVersion tests ---

def test_parse_version():
    v = FlowVersion.parse("1.2.3")
    assert v.major == 1
    assert v.minor == 2
    assert v.patch == 3


def test_parse_version_invalid():
    with pytest.raises(ValueError):
        FlowVersion.parse("not.a.version")


def test_version_str():
    v = FlowVersion(major=1, minor=0, patch=0)
    assert str(v) == "1.0.0"


def test_version_comparison():
    v1 = FlowVersion.parse("1.0.0")
    v2 = FlowVersion.parse("2.0.0")
    v1b = FlowVersion.parse("1.0.0")
    assert v1 < v2
    assert v1 == v1b
    assert v1 <= v2
    assert v1 <= v1b


def test_version_to_dict():
    v = FlowVersion.parse("1.0.0")
    d = v.to_dict()
    assert d["version"] == "1.0.0"


# --- CompatibilityChecker tests ---

def test_check_no_changes():
    old = {"name": "str", "age": "int"}
    new = {"name": "str", "age": "int"}
    changes = CompatibilityChecker.check(old, new, task_id="t1")
    assert changes == []


def test_check_field_removed():
    old = {"name": "str", "age": "int"}
    new = {"name": "str"}
    changes = CompatibilityChecker.check(old, new, task_id="t1", direction="output")
    assert len(changes) == 1
    assert changes[0].change_type == "field_removed"
    assert changes[0].breaking


def test_check_field_added():
    old = {"name": "str"}
    new = {"name": "str", "email": "str"}
    changes = CompatibilityChecker.check(old, new, task_id="t1", direction="input")
    assert len(changes) == 1
    assert changes[0].change_type == "field_added"
    assert changes[0].breaking


def test_check_type_changed():
    old = {"name": "str"}
    new = {"name": "int"}
    changes = CompatibilityChecker.check(old, new, task_id="t1")
    assert len(changes) == 1
    assert changes[0].change_type == "type_changed"
    assert changes[0].breaking


def test_is_compatible():
    assert CompatibilityChecker.is_compatible([])
    assert not CompatibilityChecker.is_compatible([
        SchemaChange("field_removed", "x", "t1", "output", breaking=True)
    ])


# --- SchemaRegistry tests ---

def test_registry_register_version():
    reg = SchemaRegistry()
    fv = reg.register_version("flow1", "1.0.0", {"task1": {"name": "str"}})
    assert str(fv) == "1.0.0"
    assert reg.get_version("flow1", "1.0.0") is fv


def test_registry_list_versions():
    reg = SchemaRegistry()
    reg.register_version("flow1", "1.0.0", {})
    reg.register_version("flow1", "2.0.0", {})
    reg.register_version("flow1", "1.1.0", {})
    versions = reg.list_versions("flow1")
    assert versions == ["1.0.0", "1.1.0", "2.0.0"]


def test_registry_check_compatibility():
    reg = SchemaRegistry()
    reg.register_version("flow1", "1.0.0", {"task1": {"name": "str", "old_field": "str"}})
    reg.register_version("flow1", "2.0.0", {"task1": {"name": "str", "new_field": "int"}})
    changes = reg.check_compatibility("flow1", "1.0.0", "2.0.0")
    assert len(changes) > 0
    types = [c.change_type for c in changes]
    assert "field_removed" in types
    assert "field_added" in types


def test_registry_add_migration():
    reg = SchemaRegistry()
    reg.add_migration("flow1", "1.0.0", "2.0.0", lambda d: {**d, "new": "default"})
    result = reg.migrate_data("flow1", {"name": "test"}, "1.0.0", "2.0.0")
    assert result["new"] == "default"
    assert result["name"] == "test"


def test_registry_migration_chain():
    reg = SchemaRegistry()
    reg.add_migration("flow1", "1.0.0", "2.0.0", lambda d: {**d, "v2": True})
    reg.add_migration("flow1", "2.0.0", "3.0.0", lambda d: {**d, "v3": True})
    result = reg.migrate_data("flow1", {"original": True}, "1.0.0", "3.0.0")
    assert result["original"]
    assert result["v2"]
    assert result["v3"]


def test_registry_no_migration_path():
    reg = SchemaRegistry()
    with pytest.raises(ValueError, match="No migration path"):
        reg.migrate_data("flow1", {}, "1.0.0", "5.0.0")


def test_registry_same_version_noop():
    reg = SchemaRegistry()
    data = {"key": "value"}
    result = reg.migrate_data("flow1", data, "1.0.0", "1.0.0")
    assert result == data


# --- snapshot_flow_schemas tests ---

def test_snapshot_flow_schemas():
    class Input(BaseModel):
        name: str = ""

    class Output(BaseModel):
        result: str = ""

    task = create_task(
        id="t1", input_schema=Input, output_schema=Output,
        execute=lambda p, c: {"result": "ok"},
    )
    flow = Flow(id="test_flow", version="1.0.0")
    flow.then(task).register()

    snapshot = snapshot_flow_schemas(flow)
    assert "t1" in snapshot
    assert any("input.name" in k for k in snapshot["t1"])
    assert any("output.result" in k for k in snapshot["t1"])
