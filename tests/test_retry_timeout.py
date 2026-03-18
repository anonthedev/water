import pytest
import asyncio
from pydantic import BaseModel
from water import create_task
from water.flow import Flow


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


# --- Retry Tests ---

@pytest.mark.asyncio
async def test_retry_on_failure():
    call_count = {"n": 0}

    def flaky_task(params, ctx):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("temporary failure")
        return {"value": params["input_data"]["value"] + 1}

    task = create_task(
        id="flaky",
        description="Fails twice then succeeds",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=flaky_task,
        retry_count=2,
        retry_delay=0.01,
    )

    flow = Flow(id="retry_flow", description="Test retry")
    flow.then(task).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11
    assert call_count["n"] == 3

@pytest.mark.asyncio
async def test_retry_exhausted():
    def always_fails(params, ctx):
        raise RuntimeError("permanent failure")

    task = create_task(
        id="always_fail",
        description="Always fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=always_fails,
        retry_count=2,
        retry_delay=0.01,
    )

    flow = Flow(id="retry_exhausted", description="Test retry exhaustion")
    flow.then(task).register()

    with pytest.raises(RuntimeError, match="permanent failure"):
        await flow.run({"value": 1})

@pytest.mark.asyncio
async def test_retry_with_backoff():
    call_count = {"n": 0}
    timestamps = []

    def timed_flaky(params, ctx):
        call_count["n"] += 1
        timestamps.append(asyncio.get_event_loop().time())
        if call_count["n"] < 3:
            raise RuntimeError("fail")
        return {"value": 1}

    task = create_task(
        id="backoff_task",
        description="Backoff retry",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=timed_flaky,
        retry_count=2,
        retry_delay=0.05,
        retry_backoff=2.0,
    )

    flow = Flow(id="backoff_flow", description="Test backoff")
    flow.then(task).register()

    result = await flow.run({"value": 0})
    assert result["value"] == 1
    assert len(timestamps) == 3

    # First retry delay: 0.05s, second: 0.1s
    delay1 = timestamps[1] - timestamps[0]
    delay2 = timestamps[2] - timestamps[1]
    assert delay1 >= 0.04  # ~0.05
    assert delay2 >= 0.08  # ~0.10

@pytest.mark.asyncio
async def test_no_retry_by_default():
    def fails(params, ctx):
        raise RuntimeError("fail")

    task = create_task(
        id="no_retry",
        description="No retry",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=fails,
    )

    flow = Flow(id="no_retry_flow", description="Test no retry")
    flow.then(task).register()

    with pytest.raises(RuntimeError, match="fail"):
        await flow.run({"value": 0})

@pytest.mark.asyncio
async def test_retry_with_async_task():
    call_count = {"n": 0}

    async def async_flaky(params, ctx):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise RuntimeError("async fail")
        return {"value": 42}

    task = create_task(
        id="async_retry",
        description="Async retry",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=async_flaky,
        retry_count=1,
    )

    flow = Flow(id="async_retry_flow", description="Test async retry")
    flow.then(task).register()

    result = await flow.run({"value": 0})
    assert result["value"] == 42


# --- Timeout Tests ---

@pytest.mark.asyncio
async def test_task_timeout():
    async def slow_task(params, ctx):
        await asyncio.sleep(5)
        return {"value": 1}

    task = create_task(
        id="slow",
        description="Slow task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=slow_task,
        timeout=0.1,
    )

    flow = Flow(id="timeout_flow", description="Test timeout")
    flow.then(task).register()

    with pytest.raises(asyncio.TimeoutError):
        await flow.run({"value": 0})

@pytest.mark.asyncio
async def test_task_completes_within_timeout():
    async def fast_task(params, ctx):
        await asyncio.sleep(0.01)
        return {"value": params["input_data"]["value"] + 1}

    task = create_task(
        id="fast",
        description="Fast task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=fast_task,
        timeout=5.0,
    )

    flow = Flow(id="fast_flow", description="Test fast task with timeout")
    flow.then(task).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11

@pytest.mark.asyncio
async def test_timeout_with_retry():
    call_count = {"n": 0}

    async def sometimes_slow(params, ctx):
        call_count["n"] += 1
        if call_count["n"] == 1:
            await asyncio.sleep(5)  # Times out
        return {"value": 99}

    task = create_task(
        id="timeout_retry",
        description="Timeout then succeed",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=sometimes_slow,
        timeout=0.1,
        retry_count=1,
    )

    flow = Flow(id="timeout_retry_flow", description="Test timeout + retry")
    flow.then(task).register()

    result = await flow.run({"value": 0})
    assert result["value"] == 99
    assert call_count["n"] == 2
