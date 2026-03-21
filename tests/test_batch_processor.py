"""
Tests for water.agents.batch – BatchProcessor, BatchResult, BatchItem,
and the create_batch_task factory.
"""

import asyncio

import pytest
from pydantic import BaseModel

from water.core.task import Task
from water.agents.batch import BatchItem, BatchProcessor, BatchResult, create_batch_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _In(BaseModel):
    value: int


class _Out(BaseModel):
    result: int


def _make_task(execute_fn=None, task_id="test_task"):
    """Return a simple Task that doubles its input value."""
    if execute_fn is None:
        async def execute_fn(params, context):
            return {"result": params["value"] * 2}

    return Task(
        id=task_id,
        description="test task",
        input_schema=_In,
        output_schema=_Out,
        execute=execute_fn,
    )


# ---------------------------------------------------------------------------
# BatchProcessor – basic execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_basic_execution():
    """BatchProcessor runs a task against every input and returns results."""
    task = _make_task()
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    inputs = [{"value": i} for i in range(5)]
    result = await proc.run_batch(task, inputs)

    assert result.total == 5
    assert result.completed == 5
    assert result.failed == 0
    for i, item in enumerate(result.items):
        assert item.status == "completed"
        assert item.result == {"result": i * 2}


# ---------------------------------------------------------------------------
# Concurrency limiting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrency_limiting():
    """max_concurrency caps the number of simultaneously running items."""
    active = {"count": 0, "peak": 0}

    async def slow(params, context):
        active["count"] += 1
        if active["count"] > active["peak"]:
            active["peak"] = active["count"]
        await asyncio.sleep(0.05)
        active["count"] -= 1
        return {"result": params["value"]}

    task = _make_task(execute_fn=slow)
    proc = BatchProcessor(max_concurrency=3, retry_failed=False)

    inputs = [{"value": i} for i in range(10)]
    result = await proc.run_batch(task, inputs)

    assert result.completed == 10
    assert active["peak"] <= 3


# ---------------------------------------------------------------------------
# Retry on failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_on_failure():
    """Failed items are retried up to max_retries times."""
    call_counts: dict = {}

    async def flaky(params, context):
        idx = params["value"]
        call_counts.setdefault(idx, 0)
        call_counts[idx] += 1
        if idx == 2 and call_counts[idx] <= 2:
            raise RuntimeError("transient")
        return {"result": idx}

    task = _make_task(execute_fn=flaky)
    proc = BatchProcessor(max_concurrency=5, retry_failed=True, max_retries=2)

    inputs = [{"value": i} for i in range(5)]
    result = await proc.run_batch(task, inputs)

    # Item 2 fails twice then succeeds on the 3rd attempt (initial + 2 retries)
    assert result.completed == 5
    assert result.failed == 0
    assert call_counts[2] == 3


# ---------------------------------------------------------------------------
# BatchResult.success_rate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_rate():
    """success_rate reflects the proportion of completed items."""
    async def half_fail(params, context):
        if params["value"] % 2 == 0:
            raise RuntimeError("even")
        return {"result": params["value"]}

    task = _make_task(execute_fn=half_fail)
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    inputs = [{"value": i} for i in range(4)]  # 0,1,2,3 -> 0,2 fail
    result = await proc.run_batch(task, inputs)

    assert result.success_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# BatchResult.get_results ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_results_ordering():
    """get_results returns results in the same order as inputs."""
    task = _make_task()
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    inputs = [{"value": i} for i in range(5)]
    result = await proc.run_batch(task, inputs)

    ordered = result.get_results()
    assert ordered == [{"result": i * 2} for i in range(5)]


# ---------------------------------------------------------------------------
# BatchResult.get_errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_errors():
    """get_errors returns index and error message for each failed item."""
    async def always_fail(params, context):
        raise ValueError(f"bad-{params['value']}")

    task = _make_task(execute_fn=always_fail)
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    inputs = [{"value": i} for i in range(3)]
    result = await proc.run_batch(task, inputs)

    errors = result.get_errors()
    assert len(errors) == 3
    assert errors[0] == {"index": 0, "error": "bad-0"}
    assert errors[1] == {"index": 1, "error": "bad-1"}
    assert errors[2] == {"index": 2, "error": "bad-2"}


# ---------------------------------------------------------------------------
# All succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_succeed():
    """When every item succeeds, failed == 0 and success_rate == 1.0."""
    task = _make_task()
    proc = BatchProcessor(max_concurrency=10, retry_failed=False)

    inputs = [{"value": i} for i in range(6)]
    result = await proc.run_batch(task, inputs)

    assert result.completed == 6
    assert result.failed == 0
    assert result.success_rate == 1.0
    assert result.get_errors() == []


# ---------------------------------------------------------------------------
# All fail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_fail():
    """When every item fails, completed == 0 and success_rate == 0.0."""
    async def boom(params, context):
        raise RuntimeError("boom")

    task = _make_task(execute_fn=boom)
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    inputs = [{"value": i} for i in range(4)]
    result = await proc.run_batch(task, inputs)

    assert result.completed == 0
    assert result.failed == 4
    assert result.success_rate == 0.0
    assert all(r is None for r in result.get_results())


# ---------------------------------------------------------------------------
# Mixed results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_results():
    """A mix of successes and failures is reported correctly."""
    async def sometimes(params, context):
        if params["value"] in (1, 3):
            raise RuntimeError("nope")
        return {"result": params["value"] * 10}

    task = _make_task(execute_fn=sometimes)
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    inputs = [{"value": i} for i in range(5)]  # 0 ok, 1 fail, 2 ok, 3 fail, 4 ok
    result = await proc.run_batch(task, inputs)

    assert result.completed == 3
    assert result.failed == 2

    ordered = result.get_results()
    assert ordered[0] == {"result": 0}
    assert ordered[1] is None
    assert ordered[2] == {"result": 20}
    assert ordered[3] is None
    assert ordered[4] == {"result": 40}


# ---------------------------------------------------------------------------
# create_batch_task factory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_batch_task():
    """create_batch_task wraps a task so it processes a list via a batch."""
    inner = _make_task()

    batch_task = create_batch_task(
        id="my_batch",
        task=inner,
        max_concurrency=3,
        input_key="items",
        output_key="results",
    )

    assert batch_task.id == "my_batch"

    output = await batch_task.execute(
        {"items": [{"value": 1}, {"value": 2}, {"value": 3}]},
        None,
    )

    assert output["results"] == [{"result": 2}, {"result": 4}, {"result": 6}]


# ---------------------------------------------------------------------------
# on_progress callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_progress_callback():
    """on_progress is called after each item completes."""
    progress_log: list = []

    def on_progress(completed, total):
        progress_log.append((completed, total))

    task = _make_task()
    proc = BatchProcessor(
        max_concurrency=2,
        retry_failed=False,
        on_progress=on_progress,
    )

    inputs = [{"value": i} for i in range(4)]
    result = await proc.run_batch(task, inputs)

    assert result.completed == 4
    # We should have received 4 progress callbacks
    assert len(progress_log) == 4
    # Each callback should report the correct total
    assert all(total == 4 for _, total in progress_log)


# ---------------------------------------------------------------------------
# Empty batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_batch():
    """An empty input list returns an empty BatchResult."""
    task = _make_task()
    proc = BatchProcessor(max_concurrency=5, retry_failed=False)

    result = await proc.run_batch(task, [])

    assert result.total == 0
    assert result.completed == 0
    assert result.failed == 0
    assert result.items == []
    assert result.get_results() == []
    assert result.get_errors() == []
    assert result.success_rate == 0.0
