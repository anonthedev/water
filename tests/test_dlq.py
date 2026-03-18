import pytest
from pydantic import BaseModel
from water import create_task, InMemoryDLQ, DeadLetter
from water.flow import Flow


class NumberInput(BaseModel):
    value: int


class NumberOutput(BaseModel):
    value: int


def _failing_task(task_id="failing_task", retry_count=0):
    return create_task(
        id=task_id,
        description="Always fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: (_ for _ in ()).throw(ValueError("boom")),
        retry_count=retry_count,
    )


def _ok_task(task_id="ok_task"):
    return create_task(
        id=task_id,
        description="Always succeeds",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )


@pytest.mark.asyncio
async def test_failed_task_pushed_to_dlq():
    """A failing task creates a DeadLetter in the DLQ."""
    dlq = InMemoryDLQ()
    flow = Flow(id="dlq_flow")
    flow.dlq = dlq
    flow.then(_failing_task()).register()

    with pytest.raises(ValueError, match="boom"):
        await flow.run({"value": 1})

    assert await dlq.size() == 1


@pytest.mark.asyncio
async def test_dlq_captures_context():
    """DeadLetter has correct task_id, flow_id, input_data, error."""
    dlq = InMemoryDLQ()
    flow = Flow(id="ctx_flow")
    flow.dlq = dlq
    flow.then(_failing_task(task_id="my_task")).register()

    with pytest.raises(ValueError):
        await flow.run({"value": 42})

    letters = await dlq.list_letters()
    assert len(letters) == 1
    letter = letters[0]
    assert letter.task_id == "my_task"
    assert letter.flow_id == "ctx_flow"
    assert letter.input_data == {"value": 42}
    assert "boom" in letter.error
    assert letter.error_type == "ValueError"
    assert letter.attempts == 1


@pytest.mark.asyncio
async def test_dlq_list_and_pop():
    """list_letters and pop work correctly."""
    dlq = InMemoryDLQ()
    flow = Flow(id="pop_flow")
    flow.dlq = dlq

    flow.then(_failing_task(task_id="t1")).register()

    with pytest.raises(ValueError):
        await flow.run({"value": 1})
    with pytest.raises(ValueError):
        await flow.run({"value": 2})

    assert await dlq.size() == 2

    # list returns all
    all_letters = await dlq.list_letters()
    assert len(all_letters) == 2

    # list filtered by flow_id
    filtered = await dlq.list_letters(flow_id="pop_flow")
    assert len(filtered) == 2
    filtered_other = await dlq.list_letters(flow_id="other_flow")
    assert len(filtered_other) == 0

    # pop removes first by default
    first = await dlq.pop()
    assert first is not None
    assert first.input_data == {"value": 1}
    assert await dlq.size() == 1

    # pop out of range returns None
    assert await dlq.pop(index=99) is None


@pytest.mark.asyncio
async def test_dlq_clear():
    """clear empties the queue."""
    dlq = InMemoryDLQ()
    flow = Flow(id="clear_flow")
    flow.dlq = dlq
    flow.then(_failing_task()).register()

    with pytest.raises(ValueError):
        await flow.run({"value": 1})

    assert await dlq.size() == 1
    await dlq.clear()
    assert await dlq.size() == 0


@pytest.mark.asyncio
async def test_no_dlq_on_success():
    """Successful tasks don't push to DLQ."""
    dlq = InMemoryDLQ()
    flow = Flow(id="success_flow")
    flow.dlq = dlq
    flow.then(_ok_task()).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6
    assert await dlq.size() == 0


@pytest.mark.asyncio
async def test_no_dlq_by_default():
    """Flow works without DLQ configured."""
    flow = Flow(id="no_dlq_flow")
    flow.then(_ok_task()).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11
    assert flow.dlq is None
