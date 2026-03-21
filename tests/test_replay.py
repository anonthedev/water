"""Tests for the Execution Replay engine (Feature #33)."""

import pytest
from pydantic import BaseModel
from typing import Any, Dict

from water import Flow, create_task
from water.core.replay import ReplayConfig, ReplayResult, ReplayEngine


# ---------------------------------------------------------------------------
# Shared schemas and task helpers
# ---------------------------------------------------------------------------

class NumIn(BaseModel):
    value: int


class NumOut(BaseModel):
    value: int


class SumIn(BaseModel):
    value: int
    extra: int = 0


class SumOut(BaseModel):
    value: int
    extra: int


def _add_one(params: Dict[str, Any], ctx) -> Dict[str, Any]:
    d = params["input_data"]
    return {"value": d["value"] + 1}


def _double(params: Dict[str, Any], ctx) -> Dict[str, Any]:
    d = params["input_data"]
    return {"value": d["value"] * 2}


def _add_extra(params: Dict[str, Any], ctx) -> Dict[str, Any]:
    d = params["input_data"]
    return {"value": d["value"], "extra": d.get("extra", 0) + 10}


def _make_flow(flow_id: str = "replay_test") -> Flow:
    """Build a simple 3-task pipeline: +1 -> *2 -> +extra."""
    t1 = create_task(id="add_one", input_schema=NumIn, output_schema=NumOut,
                     execute=_add_one, description="add one")
    t2 = create_task(id="double", input_schema=NumIn, output_schema=NumOut,
                     execute=_double, description="double")
    t3 = create_task(id="add_extra", input_schema=SumIn, output_schema=SumOut,
                     execute=_add_extra, description="add extra")
    flow = Flow(id=flow_id, description="replay test flow")
    flow.then(t1).then(t2).then(t3).register()
    return flow


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReplayConfig:
    def test_defaults(self):
        cfg = ReplayConfig()
        assert cfg.from_task is None
        assert cfg.from_step is None
        assert cfg.override_inputs is None
        assert cfg.skip_tasks == []

    def test_custom_values(self):
        cfg = ReplayConfig(
            from_task="task_a",
            from_step=2,
            override_inputs={"task_a": {"x": 1}},
            skip_tasks=["task_b"],
        )
        assert cfg.from_task == "task_a"
        assert cfg.from_step == 2
        assert cfg.override_inputs == {"task_a": {"x": 1}}
        assert cfg.skip_tasks == ["task_b"]


class TestReplayResult:
    def test_creation(self):
        r = ReplayResult(
            original_session_id="sess_1",
            replay_session_id="replay_abc",
            replayed_from="task_a",
            cached_steps=["step_0"],
            re_executed_steps=["step_1"],
            result={"value": 42},
        )
        assert r.original_session_id == "sess_1"
        assert r.status == "completed"
        assert r.error is None

    def test_error_status(self):
        r = ReplayResult(
            original_session_id="s1",
            replay_session_id="r1",
            replayed_from="step_0",
            cached_steps=[],
            re_executed_steps=[],
            error="boom",
            status="failed",
        )
        assert r.status == "failed"
        assert r.error == "boom"


class TestReplayEngineSetOutputs:
    def test_set_and_read(self):
        engine = ReplayEngine()
        outputs = {"task_a": {"x": 1}, "task_b": {"y": 2}}
        engine.set_task_outputs(outputs)
        assert engine._task_outputs == outputs

    def test_set_copies(self):
        """set_task_outputs should store a copy, not a reference."""
        engine = ReplayEngine()
        original = {"t1": {"v": 1}}
        engine.set_task_outputs(original)
        original["t1"]["v"] = 999
        assert engine._task_outputs["t1"]["v"] == 1


@pytest.mark.asyncio
async def test_replay_from_specific_task():
    """Replay from 'double' should reuse add_one output, re-run double onward."""
    flow = _make_flow("from_task")
    engine = ReplayEngine()
    engine.set_task_outputs({
        "add_one": {"value": 6},   # pretend original add_one produced 6
        "double": {"value": 12},
        "add_extra": {"value": 12, "extra": 10},
    })

    result = await engine.replay(
        flow,
        session_id="orig_session",
        config=ReplayConfig(from_task="double"),
    )

    assert result.status == "completed"
    assert "add_one" in result.cached_steps
    assert "double" in result.re_executed_steps
    assert "add_extra" in result.re_executed_steps
    assert result.replayed_from == "double"


@pytest.mark.asyncio
async def test_replay_from_step_index():
    """Replay from step index 1 should cache step 0, re-run steps 1+."""
    flow = _make_flow("from_step")
    engine = ReplayEngine()
    engine.set_task_outputs({
        "add_one": {"value": 5},
        "double": {"value": 10},
        "add_extra": {"value": 10, "extra": 10},
    })

    result = await engine.replay(
        flow,
        session_id="s1",
        config=ReplayConfig(from_step=1),
    )

    assert result.status == "completed"
    assert result.cached_steps == ["add_one"]
    assert "double" in result.re_executed_steps
    assert result.replayed_from == "step_1"


@pytest.mark.asyncio
async def test_cached_steps_tracked():
    """Steps before the replay point that have cached outputs are recorded."""
    flow = _make_flow("cached_tracking")
    engine = ReplayEngine()
    engine.set_task_outputs({
        "add_one": {"value": 3},
        "double": {"value": 6},
    })

    result = await engine.replay(
        flow,
        session_id="s2",
        config=ReplayConfig(from_task="add_extra"),
    )

    assert result.cached_steps == ["add_one", "double"]


@pytest.mark.asyncio
async def test_re_executed_steps_tracked():
    """Steps from the replay point onward are listed as re-executed."""
    flow = _make_flow("re_exec")
    engine = ReplayEngine()
    engine.set_task_outputs({"add_one": {"value": 3}})

    result = await engine.replay(
        flow,
        session_id="s3",
        config=ReplayConfig(from_task="double"),
    )

    assert "double" in result.re_executed_steps
    assert "add_extra" in result.re_executed_steps
    assert "add_one" not in result.re_executed_steps


@pytest.mark.asyncio
async def test_override_inputs():
    """Override inputs should be merged into the data before re-execution."""
    flow = _make_flow("override")
    engine = ReplayEngine()
    engine.set_task_outputs({
        "add_one": {"value": 5},
    })

    result = await engine.replay(
        flow,
        session_id="s4",
        config=ReplayConfig(
            from_task="double",
            override_inputs={"double": {"value": 100}},
        ),
    )

    assert result.status == "completed"
    # The override merges value=100 into data before flow.run re-executes
    # the full registered pipeline.  add_one(100)->101, double(101)->202,
    # add_extra(202)->{value:202, extra:10}
    assert result.result is not None
    assert result.result["value"] == 202
    assert result.result["extra"] == 10


@pytest.mark.asyncio
async def test_replay_no_prior_outputs():
    """With no cached outputs the full flow runs from the beginning."""
    flow = _make_flow("no_cache")
    engine = ReplayEngine()
    # Don't set any task outputs -- simulates no prior session data.
    # Provide initial input via override_inputs so the flow has valid data.

    result = await engine.replay(
        flow,
        session_id="empty_session",
        config=ReplayConfig(override_inputs={"_init": {"value": 1}}),
    )

    # from_step defaults to 0 so everything is re-executed
    assert result.status == "completed"
    assert result.cached_steps == []
    assert len(result.re_executed_steps) == 3


@pytest.mark.asyncio
async def test_replay_result_status_on_error():
    """If the flow raises, the replay result captures the error."""
    def _boom(params, ctx):
        raise RuntimeError("kaboom")

    t = create_task(id="boom", input_schema=NumIn, output_schema=NumOut,
                    execute=_boom, description="boom")
    flow = Flow(id="err_flow", description="error flow")
    flow.then(t).register()

    engine = ReplayEngine()
    result = await engine.replay(flow, session_id="s_err")

    assert result.status == "failed"
    assert "kaboom" in result.error


@pytest.mark.asyncio
async def test_skip_tasks_config():
    """skip_tasks should exclude listed tasks from re_executed_steps."""
    flow = _make_flow("skip")
    engine = ReplayEngine()
    engine.set_task_outputs({"add_one": {"value": 3}})

    result = await engine.replay(
        flow,
        session_id="s5",
        config=ReplayConfig(from_task="double", skip_tasks=["add_extra"]),
    )

    assert result.status == "completed"
    assert "add_extra" not in result.re_executed_steps
    assert "double" in result.re_executed_steps


@pytest.mark.asyncio
async def test_load_session_async_with_no_storage():
    """load_session_async returns empty dict when no storage backend."""
    engine = ReplayEngine()
    outputs = await engine.load_session_async("any_id")
    assert outputs == {}
