import pytest
from unittest.mock import AsyncMock, patch
from pydantic import BaseModel
from water import Flow, create_task, InMemoryCheckpoint


class NumIn(BaseModel):
    value: int


class NumOut(BaseModel):
    value: int


def make_add_task(task_id: str, amount: int):
    """Helper: creates a task that adds *amount* to ``value``."""
    def execute(p, c):
        return {"value": p["input_data"]["value"] + amount}
    return create_task(
        id=task_id,
        description=f"Add {amount}",
        input_schema=NumIn,
        output_schema=NumOut,
        execute=execute,
    )


@pytest.mark.asyncio
async def test_checkpoint_saves_after_each_node():
    """Checkpoint.save is called once after every node."""
    cp = InMemoryCheckpoint()
    cp.save = AsyncMock(wraps=cp.save)
    cp.clear = AsyncMock(wraps=cp.clear)

    t1 = make_add_task("add1", 1)
    t2 = make_add_task("add2", 10)
    t3 = make_add_task("add3", 100)

    flow = Flow(id="ckpt_save", description="Checkpoint save test")
    flow.checkpoint = cp
    flow.then(t1).then(t2).then(t3).register()

    result = await flow.run({"value": 0})
    assert result["value"] == 111

    # save called once per node (3 nodes)
    assert cp.save.call_count == 3
    # clear called once at the end
    assert cp.clear.call_count == 1


@pytest.mark.asyncio
async def test_checkpoint_recovery():
    """A flow can resume from a saved checkpoint after a simulated crash."""
    cp = InMemoryCheckpoint()

    call_log = []

    def make_logged_task(task_id, amount):
        def execute(p, c):
            call_log.append(task_id)
            return {"value": p["input_data"]["value"] + amount}
        return create_task(
            id=task_id,
            description=f"Logged add {amount}",
            input_schema=NumIn,
            output_schema=NumOut,
            execute=execute,
        )

    t1 = make_logged_task("step1", 1)
    t2 = make_logged_task("step2", 10)
    t3 = make_logged_task("step3", 100)

    # --- First run: simulate crash after node 1 by pre-saving a checkpoint ---
    # Manually save a checkpoint as if node 0 and node 1 completed
    # node_index=2 means "resume from node 2", data is result after step1+step2
    await cp.save("ckpt_recover", "exec_1", 2, {"value": 11})

    # Build a new flow that will pick up the checkpoint
    flow = Flow(id="ckpt_recover", description="Recovery test")
    flow.checkpoint = cp
    flow.then(t1).then(t2).then(t3).register()

    # Patch ExecutionContext to use a fixed execution_id so it matches the checkpoint
    with patch("water.execution_engine.ExecutionContext") as MockCtx:
        ctx_instance = MockCtx.return_value
        ctx_instance.execution_id = "exec_1"
        ctx_instance.flow_id = "ckpt_recover"
        ctx_instance.flow_metadata = {}
        ctx_instance._task_outputs = {}
        ctx_instance._step_history = []
        ctx_instance.step_number = 0
        ctx_instance.task_id = None
        ctx_instance.step_start_time = None
        ctx_instance.attempt_number = 1
        ctx_instance.add_task_output = lambda tid, res: None

        result = await flow.run({"value": 0})

    # Only step3 should have executed (skipped step1 and step2)
    assert call_log == ["step3"]
    assert result["value"] == 111


@pytest.mark.asyncio
async def test_checkpoint_cleared_on_completion():
    """After successful completion the checkpoint is removed."""
    cp = InMemoryCheckpoint()

    t1 = make_add_task("c1", 5)
    flow = Flow(id="ckpt_clear", description="Clear test")
    flow.checkpoint = cp
    flow.then(t1).register()

    await flow.run({"value": 0})

    # Checkpoint should have been cleared — nothing to load
    loaded = await cp.load("ckpt_clear", "any_exec_id")
    assert loaded is None


@pytest.mark.asyncio
async def test_no_checkpoint_by_default():
    """Flow works normally when no checkpoint backend is configured."""
    t1 = make_add_task("plain1", 1)
    t2 = make_add_task("plain2", 2)

    flow = Flow(id="no_ckpt", description="No checkpoint")
    flow.then(t1).then(t2).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 13


@pytest.mark.asyncio
async def test_in_memory_checkpoint_save_load_clear():
    """Unit test the InMemoryCheckpoint backend directly."""
    cp = InMemoryCheckpoint()

    # Initially empty
    assert await cp.load("f1", "e1") is None

    # Save and load
    await cp.save("f1", "e1", 3, {"x": 42})
    loaded = await cp.load("f1", "e1")
    assert loaded == {"node_index": 3, "data": {"x": 42}}

    # Overwrite
    await cp.save("f1", "e1", 5, {"x": 99})
    loaded = await cp.load("f1", "e1")
    assert loaded["node_index"] == 5
    assert loaded["data"]["x"] == 99

    # Clear
    await cp.clear("f1", "e1")
    assert await cp.load("f1", "e1") is None

    # Clear non-existent key is a no-op
    await cp.clear("f1", "e1")
