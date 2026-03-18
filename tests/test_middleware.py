import pytest
from pydantic import BaseModel
from water import create_task, Middleware, LoggingMiddleware, TransformMiddleware
from water.core import Flow


class NumberInput(BaseModel):
    value: int


class NumberOutput(BaseModel):
    value: int


def _add_one_task(task_id="add_one"):
    return create_task(
        id=task_id,
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )


@pytest.mark.asyncio
async def test_before_task_modifies_data():
    """Middleware transforms input before task execution."""

    def before_fn(task_id, data, context):
        # Double the value before the task sees it
        return {**data, "value": data["value"] * 2}

    mw = TransformMiddleware(before_fn=before_fn)

    task = _add_one_task()
    flow = Flow(id="mw_before", description="Test before middleware")
    flow.use(mw).then(task).register()

    result = await flow.run({"value": 5})
    # 5 * 2 = 10, then +1 = 11
    assert result["value"] == 11


@pytest.mark.asyncio
async def test_after_task_modifies_result():
    """Middleware transforms output after task execution."""

    def after_fn(task_id, data, result, context):
        return {**result, "value": result["value"] * 10}

    mw = TransformMiddleware(after_fn=after_fn)

    task = _add_one_task()
    flow = Flow(id="mw_after", description="Test after middleware")
    flow.use(mw).then(task).register()

    result = await flow.run({"value": 3})
    # 3 + 1 = 4, then * 10 = 40
    assert result["value"] == 40


@pytest.mark.asyncio
async def test_multiple_middleware_chained():
    """Multiple middleware run in order (first added = first called)."""
    call_order = []

    def before_a(task_id, data, context):
        call_order.append("before_a")
        return {**data, "value": data["value"] + 100}

    def after_a(task_id, data, result, context):
        call_order.append("after_a")
        return result

    def before_b(task_id, data, context):
        call_order.append("before_b")
        return {**data, "value": data["value"] + 200}

    def after_b(task_id, data, result, context):
        call_order.append("after_b")
        return result

    mw_a = TransformMiddleware(before_fn=before_a, after_fn=after_a)
    mw_b = TransformMiddleware(before_fn=before_b, after_fn=after_b)

    task = _add_one_task()
    flow = Flow(id="mw_chain", description="Test chained middleware")
    flow.use(mw_a).use(mw_b).then(task).register()

    result = await flow.run({"value": 1})
    # before_a: 1 + 100 = 101
    # before_b: 101 + 200 = 301
    # task: 301 + 1 = 302
    assert result["value"] == 302
    assert call_order == ["before_a", "before_b", "after_a", "after_b"]


@pytest.mark.asyncio
async def test_logging_middleware():
    """LoggingMiddleware does not modify data, just logs."""
    mw = LoggingMiddleware()

    task = _add_one_task()
    flow = Flow(id="mw_log", description="Test logging middleware")
    flow.use(mw).then(task).register()

    result = await flow.run({"value": 7})
    # Data should pass through unchanged by middleware
    assert result["value"] == 8


@pytest.mark.asyncio
async def test_middleware_with_parallel():
    """Middleware runs for each task in a parallel node."""
    seen_tasks = []

    def before_fn(task_id, data, context):
        seen_tasks.append(task_id)
        return data

    mw = TransformMiddleware(before_fn=before_fn)

    task_a = create_task(
        id="par_a",
        description="Task A",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )
    task_b = create_task(
        id="par_b",
        description="Task B",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 2},
    )

    flow = Flow(id="mw_parallel", description="Test parallel middleware")
    flow.use(mw).parallel([task_a, task_b]).register()

    result = await flow.run({"value": 10})
    assert "par_a" in seen_tasks
    assert "par_b" in seen_tasks
    assert result["par_a"]["value"] == 11
    assert result["par_b"]["value"] == 12


@pytest.mark.asyncio
async def test_no_middleware_by_default():
    """Flow works without any middleware added."""
    task = _add_one_task()
    flow = Flow(id="no_mw", description="No middleware")
    flow.then(task).register()

    result = await flow.run({"value": 0})
    assert result["value"] == 1
    assert flow.middleware == []
