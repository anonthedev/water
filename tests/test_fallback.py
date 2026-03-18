import pytest
from pydantic import BaseModel
from water import create_task, Flow


class NumberInput(BaseModel):
    value: int


class NumberOutput(BaseModel):
    value: int


def make_failing_task(task_id="failing_task"):
    """Create a task that always raises an exception."""
    def execute(params, context):
        raise RuntimeError("primary task failed")

    return create_task(
        id=task_id,
        description="A task that always fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=execute,
    )


def make_fallback_task(task_id="fallback_task"):
    """Create a fallback task that returns a fixed value."""
    def execute(params, context):
        return {"value": params["input_data"]["value"] * 10}

    return create_task(
        id=task_id,
        description="A fallback task that multiplies by 10",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=execute,
    )


def make_success_task(task_id="success_task"):
    """Create a task that succeeds normally."""
    def execute(params, context):
        return {"value": params["input_data"]["value"] + 1}

    return create_task(
        id=task_id,
        description="A task that adds one",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=execute,
    )


@pytest.mark.asyncio
async def test_fallback_runs_on_failure():
    """When the primary task fails and a fallback is provided, the fallback runs and the flow succeeds."""
    primary = make_failing_task()
    fallback = make_fallback_task()

    flow = Flow(id="fallback_flow", description="Test fallback on failure")
    flow.then(primary, fallback=fallback).register()

    result = await flow.run({"value": 5})
    assert result == {"value": 50}


@pytest.mark.asyncio
async def test_no_fallback_on_success():
    """When the primary task succeeds, the fallback is never invoked."""
    primary = make_success_task()
    fallback_called = {"called": False}

    def fallback_execute(params, context):
        fallback_called["called"] = True
        return {"value": -1}

    fallback = create_task(
        id="spy_fallback",
        description="A fallback that should not be called",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=fallback_execute,
    )

    flow = Flow(id="no_fallback_flow", description="Test no fallback on success")
    flow.then(primary, fallback=fallback).register()

    result = await flow.run({"value": 5})
    assert result == {"value": 6}
    assert fallback_called["called"] is False


@pytest.mark.asyncio
async def test_fallback_with_no_fallback_raises():
    """When no fallback is set and the task fails, the flow raises the original error."""
    primary = make_failing_task()

    flow = Flow(id="no_fallback_error_flow", description="Test error without fallback")
    flow.then(primary).register()

    with pytest.raises(RuntimeError, match="primary task failed"):
        await flow.run({"value": 5})


@pytest.mark.asyncio
async def test_fallback_also_fails():
    """When both primary and fallback tasks fail, the flow fails with the fallback's error."""
    primary = make_failing_task("primary_fail")

    def bad_fallback_execute(params, context):
        raise ValueError("fallback also failed")

    bad_fallback = create_task(
        id="bad_fallback",
        description="A fallback that also fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=bad_fallback_execute,
    )

    flow = Flow(id="double_fail_flow", description="Test both tasks failing")
    flow.then(primary, fallback=bad_fallback).register()

    with pytest.raises(ValueError, match="fallback also failed"):
        await flow.run({"value": 5})


@pytest.mark.asyncio
async def test_fallback_receives_original_data():
    """The fallback task receives the same input data that the primary task received."""
    captured_data = {}

    def failing_execute(params, context):
        raise RuntimeError("boom")

    def capturing_fallback(params, context):
        captured_data.update(params["input_data"])
        return params["input_data"]

    primary = create_task(
        id="fail_for_capture",
        description="Fails so fallback captures data",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=failing_execute,
    )
    fallback = create_task(
        id="capture_fallback",
        description="Captures input data",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=capturing_fallback,
    )

    flow = Flow(id="capture_flow", description="Test fallback receives original data")
    flow.then(primary, fallback=fallback).register()

    result = await flow.run({"value": 42})
    assert captured_data == {"value": 42}
    assert result == {"value": 42}
