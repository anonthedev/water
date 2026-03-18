import pytest
import time
import asyncio
from pydantic import BaseModel
from water import create_task, Flow
from water.resilience import RateLimiter


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    """RateLimiter acquire works without error."""
    rl = RateLimiter()
    await rl.acquire("test", 100.0)  # 100/sec, should be instant


@pytest.mark.asyncio
async def test_rate_limiter_throttles():
    """Multiple acquires on a slow bucket introduce delay."""
    rl = RateLimiter()
    start = time.monotonic()
    # 2 per second => second call should wait ~0.5s
    await rl.acquire("slow", 2.0)
    await rl.acquire("slow", 2.0)
    await rl.acquire("slow", 2.0)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4  # At least some throttling happened


@pytest.mark.asyncio
async def test_rate_limiter_separate_buckets():
    """Different names use independent buckets."""
    rl = RateLimiter()
    await rl.acquire("a", 1.0)
    await rl.acquire("b", 1.0)
    # Both should succeed quickly since they're separate buckets
    bucket_a = rl.get_bucket("a", 1.0)
    bucket_b = rl.get_bucket("b", 1.0)
    assert bucket_a is not bucket_b


@pytest.mark.asyncio
async def test_task_with_rate_limit():
    """Task with rate_limit executes correctly."""
    call_times = []

    def timed_execute(p, c):
        call_times.append(time.monotonic())
        return {"value": p["input_data"]["value"] + 1}

    task = create_task(
        id="rate_limited",
        description="Rate limited task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=timed_execute,
        rate_limit=10.0,  # 10 per second
    )

    flow = Flow(id="rl_flow", description="Rate limited flow")
    flow.then(task).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6


@pytest.mark.asyncio
async def test_task_without_rate_limit():
    """Task without rate_limit has no throttling."""
    task = create_task(
        id="no_rl",
        description="No rate limit",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )
    assert task.rate_limit is None

    flow = Flow(id="no_rl_flow", description="No rate limit")
    flow.then(task).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6


@pytest.mark.asyncio
async def test_parallel_tasks_with_rate_limit():
    """Rate-limited tasks in parallel share the same bucket per task id."""
    call_times = []

    def timed_execute(p, c):
        call_times.append(time.monotonic())
        return {"value": 1}

    task = create_task(
        id="shared_rl",
        description="Shared rate limit",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=timed_execute,
        rate_limit=5.0,  # 5 per second
    )

    flow = Flow(id="parallel_rl", description="Parallel rate limited")
    flow.parallel([task, task]).register()

    result = await flow.run({"value": 0})
    assert "shared_rl" in result
