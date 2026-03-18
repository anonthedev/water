import pytest
from pydantic import BaseModel
from water import create_task
from water.core import Flow
from water.middleware.hooks import HookManager


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_on_task_start_hook():
    events = []

    def on_start(task_id, input_data, context):
        events.append(("start", task_id, input_data))

    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="hook_flow", description="Test hooks")
    flow.hooks.on("on_task_start", on_start)
    flow.then(task).register()

    await flow.run({"value": 5})
    assert len(events) == 1
    assert events[0][1] == "t1"
    assert events[0][2] == {"value": 5}

@pytest.mark.asyncio
async def test_on_task_complete_hook():
    events = []

    def on_complete(task_id, input_data, output_data, context):
        events.append(("complete", task_id, output_data))

    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="hook_flow", description="Test hooks")
    flow.hooks.on("on_task_complete", on_complete)
    flow.then(task).register()

    await flow.run({"value": 10})
    assert len(events) == 1
    assert events[0][2] == {"value": 11}

@pytest.mark.asyncio
async def test_on_task_error_hook():
    errors = []

    def on_error(task_id, input_data, error, context):
        errors.append(("error", task_id, str(error)))

    task = create_task(
        id="fail",
        description="Fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    flow = Flow(id="error_hook_flow", description="Test error hooks")
    flow.hooks.on("on_task_error", on_error)
    flow.then(task).register()

    with pytest.raises(RuntimeError):
        await flow.run({"value": 0})

    assert len(errors) == 1
    assert errors[0][1] == "fail"
    assert "boom" in errors[0][2]

@pytest.mark.asyncio
async def test_on_flow_start_and_complete_hooks():
    events = []

    flow = Flow(id="lifecycle_flow", description="Test lifecycle hooks")
    flow.hooks.on("on_flow_start", lambda flow_id, input_data: events.append(("flow_start", flow_id)))
    flow.hooks.on("on_flow_complete", lambda flow_id, output_data: events.append(("flow_complete", flow_id, output_data)))

    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )
    flow.then(task).register()

    await flow.run({"value": 0})
    assert events[0] == ("flow_start", "lifecycle_flow")
    assert events[1] == ("flow_complete", "lifecycle_flow", {"value": 1})

@pytest.mark.asyncio
async def test_on_flow_error_hook():
    errors = []

    flow = Flow(id="flow_err", description="Test flow error")
    flow.hooks.on("on_flow_error", lambda flow_id, error: errors.append(str(error)))

    task = create_task(
        id="fail",
        description="Fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: (_ for _ in ()).throw(RuntimeError("flow boom")),
    )
    flow.then(task).register()

    with pytest.raises(RuntimeError):
        await flow.run({"value": 0})

    assert len(errors) == 1
    assert "flow boom" in errors[0]

@pytest.mark.asyncio
async def test_async_hook():
    events = []

    async def async_on_complete(task_id, input_data, output_data, context):
        events.append(("async_complete", task_id))

    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )

    flow = Flow(id="async_hook_flow", description="Test async hooks")
    flow.hooks.on("on_task_complete", async_on_complete)
    flow.then(task).register()

    await flow.run({"value": 0})
    assert events == [("async_complete", "t1")]

@pytest.mark.asyncio
async def test_multiple_hooks_same_event():
    events = []

    flow = Flow(id="multi_hook", description="Test multiple hooks")
    flow.hooks.on("on_task_start", lambda **kw: events.append("hook1"))
    flow.hooks.on("on_task_start", lambda **kw: events.append("hook2"))

    task = create_task(
        id="t1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )
    flow.then(task).register()

    await flow.run({"value": 0})
    assert events == ["hook1", "hook2"]

def test_invalid_hook_event():
    hm = HookManager()
    with pytest.raises(ValueError, match="Unknown hook event"):
        hm.on("on_invalid", lambda: None)

@pytest.mark.asyncio
async def test_hook_exception_does_not_break_flow():
    """Hook errors are logged but don't stop execution."""
    def bad_hook(task_id, input_data, output_data, context):
        raise RuntimeError("hook error")

    task = create_task(
        id="t1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 42},
    )

    flow = Flow(id="bad_hook_flow", description="Test bad hook")
    flow.hooks.on("on_task_complete", bad_hook)
    flow.then(task).register()

    result = await flow.run({"value": 0})
    assert result["value"] == 42  # Flow still completes
