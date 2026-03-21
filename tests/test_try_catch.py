"""Tests for try-catch-finally (Feature #27: Conditional Sub-flow Composition)."""

import pytest
import asyncio
from pydantic import BaseModel
from typing import Dict, Any

from water.core.flow import Flow
from water.core.task import Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class GenericInput(BaseModel):
    data: Dict[str, Any] = {}

class GenericOutput(BaseModel):
    data: Dict[str, Any] = {}


def make_task(task_id: str, fn):
    """Create a Task from a simple async function."""
    return Task(
        id=task_id,
        description=task_id,
        input_schema=GenericInput,
        output_schema=GenericOutput,
        execute=fn,
    )


# Reusable tasks
async def add_one(params, context):
    val = params["input_data"].get("value", 0)
    return {**params["input_data"], "value": val + 1}


async def multiply_two(params, context):
    val = params["input_data"].get("value", 0)
    return {**params["input_data"], "value": val * 2}


async def failing_task(params, context):
    raise ValueError("intentional failure")


async def catch_task_fn(params, context):
    return {
        "caught": True,
        "error": params["input_data"].get("_error", ""),
        "error_type": params["input_data"].get("_error_type", ""),
    }


# Track side-effects for finally assertions
_finally_calls = []

async def finally_task_fn(params, context):
    _finally_calls.append(params["input_data"].get("_try_success"))
    return params["input_data"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_finally_calls():
    _finally_calls.clear()
    yield
    _finally_calls.clear()


@pytest.mark.asyncio
async def test_try_succeeds_catch_not_called():
    """When the try block succeeds, catch should not be called."""
    catch_called = []

    async def catch_fn(params, context):
        catch_called.append(True)
        return {"caught": True}

    task_ok = make_task("ok", add_one)
    task_catch = make_task("catch", catch_fn)

    flow = Flow(id="try_ok")
    flow.try_catch(task_ok, catch_handler=task_catch).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11
    assert len(catch_called) == 0


@pytest.mark.asyncio
async def test_try_fails_catch_called():
    """When the try block fails, catch handler should be invoked."""
    task_fail = make_task("fail", failing_task)
    task_catch = make_task("catch", catch_task_fn)

    flow = Flow(id="try_fail")
    flow.try_catch(task_fail, catch_handler=task_catch).register()

    result = await flow.run({"value": 1})
    assert result["caught"] is True
    assert "intentional failure" in result["error"]


@pytest.mark.asyncio
async def test_finally_runs_on_success():
    """finally_handler should run even when try succeeds."""
    task_ok = make_task("ok", add_one)
    task_finally = make_task("fin", finally_task_fn)

    flow = Flow(id="fin_ok")
    flow.try_catch(task_ok, finally_handler=task_finally).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6
    assert _finally_calls == [True]


@pytest.mark.asyncio
async def test_finally_runs_on_failure():
    """finally_handler should run even when try fails (with catch)."""
    task_fail = make_task("fail", failing_task)
    task_catch = make_task("catch", catch_task_fn)
    task_finally = make_task("fin", finally_task_fn)

    flow = Flow(id="fin_fail")
    flow.try_catch(task_fail, catch_handler=task_catch, finally_handler=task_finally).register()

    result = await flow.run({"value": 1})
    assert result["caught"] is True
    assert _finally_calls == [False]


@pytest.mark.asyncio
async def test_on_error_global_handler():
    """on_error wraps the entire flow in a catch."""
    task_fail = make_task("fail", failing_task)
    task_catch = make_task("catch", catch_task_fn)

    flow = Flow(id="global_err")
    flow.then(task_fail).on_error(task_catch).register()

    result = await flow.run({"value": 0})
    assert result["caught"] is True
    assert "intentional failure" in result["error"]


@pytest.mark.asyncio
async def test_try_catch_single_task():
    """try_catch should accept a single task (not a list)."""
    task_ok = make_task("single", add_one)

    flow = Flow(id="single_tc")
    flow.try_catch(task_ok).register()

    result = await flow.run({"value": 99})
    assert result["value"] == 100


@pytest.mark.asyncio
async def test_try_catch_multiple_tasks():
    """try_catch should accept a list of tasks and run them sequentially."""
    t1 = make_task("add", add_one)
    t2 = make_task("mul", multiply_two)

    flow = Flow(id="multi_tc")
    flow.try_catch([t1, t2]).register()

    result = await flow.run({"value": 3})
    # (3 + 1) * 2 = 8
    assert result["value"] == 8


@pytest.mark.asyncio
async def test_catch_handler_receives_error_info():
    """Catch handler should receive _error and _error_type in input data."""
    received = {}

    async def inspect_catch(params, context):
        received["error"] = params["input_data"].get("_error")
        received["error_type"] = params["input_data"].get("_error_type")
        return {"inspected": True}

    task_fail = make_task("fail", failing_task)
    task_catch = make_task("inspect", inspect_catch)

    flow = Flow(id="err_info")
    flow.try_catch(task_fail, catch_handler=task_catch).register()

    await flow.run({})
    assert received["error"] == "intentional failure"
    assert received["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_nested_try_catch():
    """A try_catch inside another try_catch should work correctly."""
    task_fail = make_task("fail", failing_task)
    task_ok = make_task("ok", add_one)

    async def inner_catch_fn(params, context):
        return {"inner_caught": True, "value": 42}

    task_inner_catch = make_task("inner_catch", inner_catch_fn)

    async def outer_catch_fn(params, context):
        return {"outer_caught": True}

    task_outer_catch = make_task("outer_catch", outer_catch_fn)

    # Inner flow: try failing task, catch it
    inner_flow = Flow(id="inner")
    inner_flow.try_catch(task_fail, catch_handler=task_inner_catch).register()

    # Outer flow: try the inner flow as a task, with its own catch
    outer_flow = Flow(id="outer")
    outer_flow.try_catch(
        inner_flow.as_task(),
        catch_handler=task_outer_catch,
    ).register()

    result = await outer_flow.run({"input_data": {"value": 0}})
    # Inner catch should handle it; outer catch should NOT fire
    assert result.get("inner_caught") is True
    assert result.get("outer_caught") is None


@pytest.mark.asyncio
async def test_try_catch_in_flow_chain():
    """try_catch can be chained with .then() in a flow."""
    t_pre = make_task("pre", add_one)
    t_try = make_task("try", multiply_two)
    t_post = make_task("post", add_one)

    flow = Flow(id="chain")
    flow.then(t_pre).try_catch(t_try).then(t_post).register()

    result = await flow.run({"value": 5})
    # pre: 5+1=6, try: 6*2=12, post: 12+1=13
    assert result["value"] == 13


@pytest.mark.asyncio
async def test_try_catch_no_catch_reraises():
    """Without a catch handler, the error should propagate."""
    task_fail = make_task("fail", failing_task)

    flow = Flow(id="no_catch")
    flow.try_catch(task_fail).register()

    with pytest.raises(ValueError, match="intentional failure"):
        await flow.run({})


@pytest.mark.asyncio
async def test_try_catch_callable_catch_handler():
    """catch_handler can be a plain callable instead of a Task."""
    def my_handler(error, context):
        return {"handled": True, "msg": str(error)}

    task_fail = make_task("fail", failing_task)

    flow = Flow(id="callable_catch")
    flow.try_catch(task_fail, catch_handler=my_handler).register()

    result = await flow.run({})
    assert result["handled"] is True
    assert "intentional failure" in result["msg"]


@pytest.mark.asyncio
async def test_registration_prevents_try_catch():
    """Cannot add try_catch after registration."""
    task_ok = make_task("ok", add_one)

    flow = Flow(id="locked")
    flow.then(task_ok).register()

    with pytest.raises(RuntimeError, match="Cannot add tasks after registration"):
        flow.try_catch(task_ok)
