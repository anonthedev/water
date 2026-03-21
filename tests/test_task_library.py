"""Tests for the reusable task library."""

import pytest
import json
from pathlib import Path

from water.core.flow import Flow
from water.tasks.transform import json_transform, map_fields, filter_fields
from water.tasks.io import file_read, file_write
from water.tasks.utils import delay, log_task, noop
from water.tasks.http import http_request
from water.tasks.notify import webhook_task


# --- json_transform tests ---

@pytest.mark.asyncio
async def test_json_transform_dot_path():
    t = json_transform(id="extract", expression="user.email")
    flow = Flow(id="tf1")
    flow.then(t).register()
    result = await flow.run({"user": {"email": "test@example.com", "name": "Test"}})
    assert result["data"] == "test@example.com"


@pytest.mark.asyncio
async def test_json_transform_nested():
    t = json_transform(id="extract", expression="data.items")
    flow = Flow(id="tf2")
    flow.then(t).register()
    result = await flow.run({"data": {"items": [1, 2, 3]}})
    assert result["data"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_json_transform_missing_path():
    t = json_transform(id="extract", expression="nonexistent.path")
    flow = Flow(id="tf3")
    flow.then(t).register()
    result = await flow.run({"foo": "bar"})
    assert result["data"] is None


# --- map_fields tests ---

@pytest.mark.asyncio
async def test_map_fields():
    t = map_fields(id="rename", field_map={"name": "full_name", "age": "years"})
    flow = Flow(id="mf1")
    flow.then(t).register()
    result = await flow.run({"name": "Alice", "age": 30})
    assert result["full_name"] == "Alice"
    assert result["years"] == 30
    assert "name" not in result


# --- filter_fields tests ---

@pytest.mark.asyncio
async def test_filter_fields_include():
    t = filter_fields(id="filter", include=["name", "email"])
    flow = Flow(id="ff1")
    flow.then(t).register()
    result = await flow.run({"name": "Alice", "email": "a@b.com", "age": 30})
    assert "name" in result
    assert "email" in result
    assert "age" not in result


@pytest.mark.asyncio
async def test_filter_fields_exclude():
    t = filter_fields(id="filter", exclude=["password"])
    flow = Flow(id="ff2")
    flow.then(t).register()
    result = await flow.run({"name": "Alice", "password": "secret"})
    assert "name" in result
    assert "password" not in result


# --- file_read / file_write tests ---

@pytest.mark.asyncio
async def test_file_write_and_read(tmp_path):
    fpath = str(tmp_path / "test.txt")

    w = file_write(id="write", path=fpath, content="Hello {name}")
    flow_w = Flow(id="fw1")
    flow_w.then(w).register()
    result = await flow_w.run({"name": "World"})
    assert result["success"]

    r = file_read(id="read", path=fpath)
    flow_r = Flow(id="fr1")
    flow_r.then(r).register()
    result = await flow_r.run({})
    assert result["content"] == "Hello World"
    assert result["success"]


@pytest.mark.asyncio
async def test_file_read_json(tmp_path):
    fpath = str(tmp_path / "data.json")
    Path(fpath).write_text(json.dumps({"key": "value"}))

    r = file_read(id="read_json", path=fpath, parse_json=True)
    flow = Flow(id="frj1")
    flow.then(r).register()
    result = await flow.run({})
    assert result["json_data"] == {"key": "value"}


@pytest.mark.asyncio
async def test_file_read_not_found():
    r = file_read(id="read_missing", path="/nonexistent/file.txt")
    flow = Flow(id="frm1")
    flow.then(r).register()
    result = await flow.run({})
    assert not result["success"]


# --- delay tests ---

@pytest.mark.asyncio
async def test_delay():
    t = delay(id="wait", seconds=0.01)
    flow = Flow(id="d1")
    flow.then(t).register()
    result = await flow.run({"key": "value"})
    assert result["key"] == "value"


# --- log_task tests ---

@pytest.mark.asyncio
async def test_log_task():
    t = log_task(id="logger", message="Processing {name}")
    flow = Flow(id="lt1")
    flow.then(t).register()
    result = await flow.run({"name": "test"})
    assert result["name"] == "test"


# --- noop tests ---

@pytest.mark.asyncio
async def test_noop():
    t = noop(id="no_op")
    flow = Flow(id="n1")
    flow.then(t).register()
    result = await flow.run({"data": "pass"})
    assert result["data"] == "pass"


# --- http_request tests ---

def test_http_request_creation():
    t = http_request(id="fetch", url="https://example.com/api/{id}", method="GET")
    assert t.id == "fetch"


# --- webhook_task tests ---

def test_webhook_task_creation():
    t = webhook_task(id="notify", url="https://hooks.example.com/webhook")
    assert t.id == "notify"


# --- Composition test ---

@pytest.mark.asyncio
async def test_task_composition():
    """Chain multiple library tasks together."""
    t1 = noop(id="start")
    t2 = map_fields(id="rename", field_map={"input": "data"})
    t3 = filter_fields(id="clean", include=["data"])

    flow = Flow(id="composed")
    flow.then(t1).then(t2).then(t3).register()
    result = await flow.run({"input": "hello", "extra": "remove"})
    assert result == {"data": "hello"}
