import pytest
import time
from pydantic import BaseModel
from water import create_task, Flow, InMemoryCache


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_cache_hit_skips_execution():
    """Second run with same input returns cached result without calling execute."""
    call_count = 0

    def counting_execute(p, c):
        nonlocal call_count
        call_count += 1
        return {"value": p["input_data"]["value"] + 1}

    cache = InMemoryCache()
    task = create_task(
        id="cached_add",
        description="Cached add",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=counting_execute,
        cache=cache,
    )

    flow = Flow(id="cache_hit", description="Cache hit")
    flow.then(task).register()

    r1 = await flow.run({"value": 5})
    assert r1["value"] == 6
    assert call_count == 1

    r2 = await flow.run({"value": 5})
    assert r2["value"] == 6
    assert call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_cache_miss_executes():
    """First run always executes the task."""
    call_count = 0

    def counting_execute(p, c):
        nonlocal call_count
        call_count += 1
        return {"value": p["input_data"]["value"] * 2}

    cache = InMemoryCache()
    task = create_task(
        id="cached_double",
        description="Cached double",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=counting_execute,
        cache=cache,
    )

    flow = Flow(id="cache_miss", description="Cache miss")
    flow.then(task).register()

    result = await flow.run({"value": 3})
    assert result["value"] == 6
    assert call_count == 1


@pytest.mark.asyncio
async def test_different_inputs_different_cache():
    """Different inputs produce different cache entries."""
    call_count = 0

    def counting_execute(p, c):
        nonlocal call_count
        call_count += 1
        return {"value": p["input_data"]["value"] + 1}

    cache = InMemoryCache()
    task = create_task(
        id="cached_t",
        description="Cached",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=counting_execute,
        cache=cache,
    )

    flow = Flow(id="diff_inputs", description="Different inputs")
    flow.then(task).register()

    await flow.run({"value": 1})
    await flow.run({"value": 2})
    assert call_count == 2  # Both executed (different inputs)

    await flow.run({"value": 1})
    await flow.run({"value": 2})
    assert call_count == 2  # Both cached now


@pytest.mark.asyncio
async def test_cache_ttl_expires():
    """Cached entry expires after TTL."""
    call_count = 0

    def counting_execute(p, c):
        nonlocal call_count
        call_count += 1
        return {"value": 1}

    cache = InMemoryCache()
    task = create_task(
        id="ttl_task",
        description="TTL task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=counting_execute,
        cache=cache,
    )

    flow = Flow(id="ttl_flow", description="TTL flow")
    flow.then(task).register()

    # Manually set with short TTL
    from water.cache import cache_key
    ck = cache_key("ttl_task", {"value": 0})
    cache.set(ck, {"value": 1}, ttl=0.05)

    # Should hit cache
    r1 = await flow.run({"value": 0})
    assert r1["value"] == 1
    assert call_count == 0

    # Wait for expiry
    time.sleep(0.06)

    # Should miss cache and execute
    r2 = await flow.run({"value": 0})
    assert r2["value"] == 1
    assert call_count == 1


@pytest.mark.asyncio
async def test_no_cache_by_default():
    """Tasks without cache always execute."""
    call_count = 0

    def counting_execute(p, c):
        nonlocal call_count
        call_count += 1
        return {"value": 1}

    task = create_task(
        id="no_cache",
        description="No cache",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=counting_execute,
    )

    flow = Flow(id="no_cache_flow", description="No cache")
    flow.then(task).register()

    await flow.run({"value": 0})
    await flow.run({"value": 0})
    assert call_count == 2


@pytest.mark.asyncio
async def test_cache_clear():
    """Clearing cache forces re-execution."""
    call_count = 0

    def counting_execute(p, c):
        nonlocal call_count
        call_count += 1
        return {"value": 1}

    cache = InMemoryCache()
    task = create_task(
        id="clear_task",
        description="Clear task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=counting_execute,
        cache=cache,
    )

    flow = Flow(id="clear_flow", description="Clear flow")
    flow.then(task).register()

    await flow.run({"value": 0})
    assert call_count == 1

    cache.clear()

    await flow.run({"value": 0})
    assert call_count == 2
