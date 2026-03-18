import pytest
import asyncio
import os
import tempfile
from pydantic import BaseModel

from water import (
    Flow,
    create_task,
    InMemoryStorage,
    SQLiteStorage,
    FlowSession,
    FlowStatus,
    TaskRun,
    FlowPausedError,
    FlowStoppedError,
)


# --- Test Schemas ---

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


# --- Storage Backend Tests ---

@pytest.mark.asyncio
async def test_in_memory_storage_save_and_get_session():
    storage = InMemoryStorage()
    session = FlowSession(
        flow_id="test_flow",
        input_data={"value": 1},
        execution_id="exec_123",
    )
    await storage.save_session(session)

    retrieved = await storage.get_session("exec_123")
    assert retrieved is not None
    assert retrieved.flow_id == "test_flow"
    assert retrieved.input_data == {"value": 1}
    assert retrieved.status == FlowStatus.PENDING

@pytest.mark.asyncio
async def test_in_memory_storage_get_nonexistent_session():
    storage = InMemoryStorage()
    result = await storage.get_session("nonexistent")
    assert result is None

@pytest.mark.asyncio
async def test_in_memory_storage_list_sessions():
    storage = InMemoryStorage()
    session1 = FlowSession(flow_id="flow_a", input_data={}, execution_id="exec_1")
    session2 = FlowSession(flow_id="flow_b", input_data={}, execution_id="exec_2")
    session3 = FlowSession(flow_id="flow_a", input_data={}, execution_id="exec_3")

    await storage.save_session(session1)
    await storage.save_session(session2)
    await storage.save_session(session3)

    all_sessions = await storage.list_sessions()
    assert len(all_sessions) == 3

    flow_a_sessions = await storage.list_sessions(flow_id="flow_a")
    assert len(flow_a_sessions) == 2

@pytest.mark.asyncio
async def test_in_memory_storage_save_and_get_task_runs():
    storage = InMemoryStorage()
    task_run = TaskRun(
        execution_id="exec_123",
        task_id="task_1",
        node_index=0,
        status="completed",
        input_data={"value": 1},
        output_data={"value": 2},
    )
    await storage.save_task_run(task_run)

    runs = await storage.get_task_runs("exec_123")
    assert len(runs) == 1
    assert runs[0].task_id == "task_1"
    assert runs[0].output_data == {"value": 2}

@pytest.mark.asyncio
async def test_in_memory_storage_update_task_run():
    storage = InMemoryStorage()
    task_run = TaskRun(
        execution_id="exec_123",
        task_id="task_1",
        node_index=0,
        status="running",
        id="run_abc",
    )
    await storage.save_task_run(task_run)

    task_run.status = "completed"
    task_run.output_data = {"value": 42}
    await storage.save_task_run(task_run)

    runs = await storage.get_task_runs("exec_123")
    assert len(runs) == 1
    assert runs[0].status == "completed"


# --- SQLite Storage Tests ---

@pytest.mark.asyncio
async def test_sqlite_storage_save_and_get_session():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = SQLiteStorage(db_path=db_path)
        session = FlowSession(
            flow_id="test_flow",
            input_data={"value": 1},
            execution_id="exec_sqlite",
        )
        await storage.save_session(session)

        retrieved = await storage.get_session("exec_sqlite")
        assert retrieved is not None
        assert retrieved.flow_id == "test_flow"
        assert retrieved.input_data == {"value": 1}
    finally:
        os.unlink(db_path)

@pytest.mark.asyncio
async def test_sqlite_storage_list_sessions():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = SQLiteStorage(db_path=db_path)
        session1 = FlowSession(flow_id="flow_a", input_data={}, execution_id="exec_1")
        session2 = FlowSession(flow_id="flow_b", input_data={}, execution_id="exec_2")

        await storage.save_session(session1)
        await storage.save_session(session2)

        all_sessions = await storage.list_sessions()
        assert len(all_sessions) == 2

        flow_a_sessions = await storage.list_sessions(flow_id="flow_a")
        assert len(flow_a_sessions) == 1
    finally:
        os.unlink(db_path)

@pytest.mark.asyncio
async def test_sqlite_storage_task_runs():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = SQLiteStorage(db_path=db_path)
        task_run = TaskRun(
            execution_id="exec_1",
            task_id="task_1",
            node_index=0,
            status="completed",
            input_data={"value": 10},
            output_data={"value": 20},
        )
        await storage.save_task_run(task_run)

        runs = await storage.get_task_runs("exec_1")
        assert len(runs) == 1
        assert runs[0].output_data == {"value": 20}
    finally:
        os.unlink(db_path)


# --- FlowSession Serialization Tests ---

def test_flow_session_to_dict_and_back():
    session = FlowSession(
        flow_id="test_flow",
        input_data={"key": "val"},
        execution_id="exec_ser",
        status=FlowStatus.PAUSED,
        current_node_index=2,
        current_data={"computed": True},
    )
    d = session.to_dict()
    restored = FlowSession.from_dict(d)
    assert restored.execution_id == "exec_ser"
    assert restored.status == FlowStatus.PAUSED
    assert restored.current_node_index == 2
    assert restored.current_data == {"computed": True}

def test_task_run_to_dict_and_back():
    run = TaskRun(
        execution_id="exec_1",
        task_id="t1",
        node_index=0,
        status="completed",
        input_data={"a": 1},
        output_data={"b": 2},
    )
    d = run.to_dict()
    restored = TaskRun.from_dict(d)
    assert restored.task_id == "t1"
    assert restored.status == "completed"
    assert restored.output_data == {"b": 2}


# --- Flow with Storage (Session Tracking) Tests ---

@pytest.mark.asyncio
async def test_flow_run_with_storage_creates_session():
    storage = InMemoryStorage()
    add_one = create_task(
        id="add_one",
        description="Add one",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1}
    )

    flow = Flow(id="tracked_flow", description="Test", storage=storage)
    flow.then(add_one).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6

    sessions = await storage.list_sessions(flow_id="tracked_flow")
    assert len(sessions) == 1
    assert sessions[0].status == FlowStatus.COMPLETED
    assert sessions[0].result == {"value": 6}

@pytest.mark.asyncio
async def test_flow_run_with_storage_records_task_runs():
    storage = InMemoryStorage()
    task1 = create_task(
        id="step1",
        description="Step 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1}
    )
    task2 = create_task(
        id="step2",
        description="Step 2",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] * 2}
    )

    flow = Flow(id="tracked_flow", description="Test", storage=storage)
    flow.then(task1).then(task2).register()

    result = await flow.run({"value": 3})
    assert result["value"] == 8  # (3+1)*2

    sessions = await storage.list_sessions()
    exec_id = sessions[0].execution_id

    task_runs = await storage.get_task_runs(exec_id)
    assert len(task_runs) == 2
    assert task_runs[0].task_id == "step1"
    assert task_runs[0].status == "completed"
    assert task_runs[1].task_id == "step2"
    assert task_runs[1].status == "completed"

@pytest.mark.asyncio
async def test_flow_run_failure_records_status():
    storage = InMemoryStorage()

    def failing_fn(params, ctx):
        raise RuntimeError("boom")

    task = create_task(
        id="fail_task",
        description="Fails",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=failing_fn,
    )

    flow = Flow(id="fail_flow", description="Test failure", storage=storage)
    flow.then(task).register()

    with pytest.raises(RuntimeError, match="boom"):
        await flow.run({"value": 1})

    sessions = await storage.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].status == FlowStatus.FAILED
    assert sessions[0].error == "boom"


# --- Pause / Stop / Resume Tests ---

@pytest.mark.asyncio
async def test_pause_and_resume_flow():
    """Test pausing a flow and resuming it from where it left off."""
    storage = InMemoryStorage()
    execution_tracker = {}

    task1 = create_task(
        id="task1",
        description="First task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 10}
    )

    async def slow_task(params, ctx):
        """A task that takes time, giving us a chance to pause."""
        await asyncio.sleep(0.1)
        return {"value": params["input_data"]["value"] + 20}

    task2 = create_task(
        id="task2",
        description="Second task (slow)",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=slow_task,
    )

    task3 = create_task(
        id="task3",
        description="Third task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 30}
    )

    flow = Flow(id="pausable_flow", description="Test pause/resume", storage=storage)
    flow.then(task1).then(task2).then(task3).register()

    # Start the flow in background and pause after task1 completes
    async def run_and_pause():
        # Start the flow
        run_task = asyncio.create_task(flow.run({"value": 0}))

        # Give task1 time to complete, then pause before task2 or task3
        await asyncio.sleep(0.05)

        sessions = await storage.list_sessions()
        if sessions:
            exec_id = sessions[0].execution_id
            execution_tracker["exec_id"] = exec_id
            await flow.pause(exec_id)

        try:
            await run_task
        except FlowPausedError:
            pass

    await run_and_pause()

    # Verify the flow is paused
    exec_id = execution_tracker["exec_id"]
    session = await storage.get_session(exec_id)
    assert session.status == FlowStatus.PAUSED

    # Resume the flow
    result = await flow.resume(exec_id)

    # Verify the flow completed
    session = await storage.get_session(exec_id)
    assert session.status == FlowStatus.COMPLETED

@pytest.mark.asyncio
async def test_stop_flow():
    """Test stopping a running flow."""
    storage = InMemoryStorage()

    async def slow_task(params, ctx):
        await asyncio.sleep(0.1)
        return {"value": params["input_data"]["value"] + 1}

    task1 = create_task(
        id="task1",
        description="Slow task 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=slow_task,
    )
    task2 = create_task(
        id="task2",
        description="Task 2",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1}
    )

    flow = Flow(id="stoppable_flow", description="Test stop", storage=storage)
    flow.then(task1).then(task2).register()

    execution_tracker = {}

    async def run_and_stop():
        run_task = asyncio.create_task(flow.run({"value": 0}))
        await asyncio.sleep(0.05)

        sessions = await storage.list_sessions()
        if sessions:
            exec_id = sessions[0].execution_id
            execution_tracker["exec_id"] = exec_id
            await flow.stop(exec_id)

        try:
            await run_task
        except FlowStoppedError:
            pass

    await run_and_stop()

    exec_id = execution_tracker["exec_id"]
    session = await storage.get_session(exec_id)
    assert session.status == FlowStatus.STOPPED

@pytest.mark.asyncio
async def test_resume_requires_paused_state():
    """Test that resume only works on paused flows."""
    storage = InMemoryStorage()
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )

    flow = Flow(id="test_flow", description="Test", storage=storage)
    flow.then(task).register()

    # Run to completion
    await flow.run({"value": 0})

    sessions = await storage.list_sessions()
    exec_id = sessions[0].execution_id

    with pytest.raises(ValueError, match="Cannot resume flow in 'completed' state"):
        await flow.resume(exec_id)

@pytest.mark.asyncio
async def test_pause_requires_running_state():
    """Test that pause only works on running flows."""
    storage = InMemoryStorage()
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )

    flow = Flow(id="test_flow", description="Test", storage=storage)
    flow.then(task).register()

    await flow.run({"value": 0})

    sessions = await storage.list_sessions()
    exec_id = sessions[0].execution_id

    with pytest.raises(ValueError, match="Cannot pause flow in 'completed' state"):
        await flow.pause(exec_id)

@pytest.mark.asyncio
async def test_pause_requires_storage():
    """Test that pause fails without storage backend."""
    flow = Flow(id="no_storage", description="Test")
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )
    flow.then(task).register()

    with pytest.raises(RuntimeError, match="Storage backend required"):
        await flow.pause("some_exec_id")

@pytest.mark.asyncio
async def test_stop_requires_storage():
    """Test that stop fails without storage backend."""
    flow = Flow(id="no_storage", description="Test")
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )
    flow.then(task).register()

    with pytest.raises(RuntimeError, match="Storage backend required"):
        await flow.stop("some_exec_id")

@pytest.mark.asyncio
async def test_resume_requires_storage():
    """Test that resume fails without storage backend."""
    flow = Flow(id="no_storage", description="Test")
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )
    flow.then(task).register()

    with pytest.raises(RuntimeError, match="Storage backend required"):
        await flow.resume("some_exec_id")

@pytest.mark.asyncio
async def test_pause_nonexistent_session():
    """Test pausing a nonexistent session."""
    storage = InMemoryStorage()
    flow = Flow(id="test", description="Test", storage=storage)
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )
    flow.then(task).register()

    with pytest.raises(ValueError, match="No session found"):
        await flow.pause("nonexistent")

@pytest.mark.asyncio
async def test_get_session_and_task_runs():
    """Test flow convenience methods for session/task run access."""
    storage = InMemoryStorage()
    task = create_task(
        id="my_task",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1}
    )

    flow = Flow(id="test_flow", description="Test", storage=storage)
    flow.then(task).register()

    await flow.run({"value": 5})

    sessions = await storage.list_sessions()
    exec_id = sessions[0].execution_id

    session = await flow.get_session(exec_id)
    assert session is not None
    assert session.status == FlowStatus.COMPLETED

    runs = await flow.get_task_runs(exec_id)
    assert len(runs) == 1
    assert runs[0].task_id == "my_task"

@pytest.mark.asyncio
async def test_stop_paused_flow():
    """Test that a paused flow can be stopped."""
    storage = InMemoryStorage()

    # Manually create a paused session
    session = FlowSession(
        flow_id="test_flow",
        input_data={"value": 1},
        execution_id="exec_paused",
        status=FlowStatus.PAUSED,
    )
    await storage.save_session(session)

    flow = Flow(id="test_flow", description="Test", storage=storage)
    task = create_task(
        id="task1",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": 1}
    )
    flow.then(task).register()

    await flow.stop("exec_paused")

    session = await storage.get_session("exec_paused")
    assert session.status == FlowStatus.STOPPED

@pytest.mark.asyncio
async def test_flow_without_storage_runs_normally():
    """Verify that flows without storage still work as before."""
    task = create_task(
        id="add_one",
        description="Add one",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1}
    )

    flow = Flow(id="no_storage_flow", description="Test")
    flow.then(task).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11
