import pytest
import asyncio
import time
from pydantic import BaseModel
from water import create_task, Flow


class BatchInput(BaseModel):
    value: int


class BatchOutput(BaseModel):
    result: int


def make_flow(execute_fn=None):
    """Helper to build a registered flow with a single task."""
    if execute_fn is None:
        def execute_fn(params, context):
            data = params["input_data"]
            return {"result": data["value"] * 2}

    task = create_task(
        id="double",
        description="Double the value",
        input_schema=BatchInput,
        output_schema=BatchOutput,
        execute=execute_fn,
    )
    flow = Flow(id="batch_test")
    flow.then(task).register()
    return flow


@pytest.mark.asyncio
async def test_batch_processes_all_inputs():
    """All inputs are processed and results are returned in the same order."""
    flow = make_flow()
    inputs = [{"value": i} for i in range(5)]
    results = await flow.run_batch(inputs)
    assert len(results) == 5
    for i, result in enumerate(results):
        assert result["result"] == i * 2


@pytest.mark.asyncio
async def test_batch_respects_concurrency():
    """max_concurrency limits the number of concurrent executions."""
    active = {"count": 0, "peak": 0}

    async def slow_execute(params, context):
        active["count"] += 1
        if active["count"] > active["peak"]:
            active["peak"] = active["count"]
        await asyncio.sleep(0.05)
        active["count"] -= 1
        return {"result": params["input_data"]["value"]}

    flow = make_flow(execute_fn=slow_execute)
    inputs = [{"value": i} for i in range(10)]
    results = await flow.run_batch(inputs, max_concurrency=3)

    assert len(results) == 10
    assert active["peak"] <= 3


@pytest.mark.asyncio
async def test_batch_return_exceptions_false():
    """With return_exceptions=False (default), first error is raised."""
    def failing_execute(params, context):
        if params["input_data"]["value"] == 2:
            raise ValueError("bad value")
        return {"result": params["input_data"]["value"]}

    flow = make_flow(execute_fn=failing_execute)
    inputs = [{"value": i} for i in range(5)]
    with pytest.raises(ValueError, match="bad value"):
        await flow.run_batch(inputs, return_exceptions=False)


@pytest.mark.asyncio
async def test_batch_return_exceptions_true():
    """With return_exceptions=True, exceptions appear in the results list."""
    def failing_execute(params, context):
        if params["input_data"]["value"] == 2:
            raise ValueError("bad value")
        return {"result": params["input_data"]["value"]}

    flow = make_flow(execute_fn=failing_execute)
    inputs = [{"value": i} for i in range(5)]
    results = await flow.run_batch(inputs, return_exceptions=True)

    assert len(results) == 5
    assert isinstance(results[2], Exception)
    assert "bad value" in str(results[2])
    # Non-failing inputs should have normal results
    assert results[0]["result"] == 0
    assert results[1]["result"] == 1
    assert results[3]["result"] == 3
    assert results[4]["result"] == 4


@pytest.mark.asyncio
async def test_batch_empty_inputs():
    """Empty input list returns empty result list."""
    flow = make_flow()
    results = await flow.run_batch([])
    assert results == []


@pytest.mark.asyncio
async def test_batch_requires_registration():
    """run_batch raises RuntimeError if flow is not registered."""
    task = create_task(
        id="double",
        description="Double the value",
        input_schema=BatchInput,
        output_schema=BatchOutput,
        execute=lambda params, context: {"result": params["input_data"]["value"] * 2},
    )
    flow = Flow(id="unregistered")
    flow.then(task)  # added task but not registered

    with pytest.raises(RuntimeError, match="Flow must be registered before running"):
        await flow.run_batch([{"value": 1}])
