import pytest
from pydantic import BaseModel
from water import create_task, Flow, TelemetryManager, is_otel_available
from water.telemetry import NoOpTelemetry


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


def test_noop_telemetry():
    """NoOpTelemetry is always inactive."""
    t = NoOpTelemetry()
    assert not t.is_active
    # Context managers should work as no-ops
    with t.flow_span("test") as span:
        assert span is None
    with t.task_span("task1", "flow1") as span:
        assert span is None


def test_telemetry_manager_without_otel():
    """TelemetryManager with enabled=True but no OTel installed is inactive."""
    t = TelemetryManager(enabled=True)
    # If OTel is not installed, is_active should be False
    if not is_otel_available():
        assert not t.is_active


def test_telemetry_manager_disabled():
    """TelemetryManager with enabled=False is always inactive."""
    t = TelemetryManager(enabled=False)
    assert not t.is_active


def test_record_error_noop():
    """record_error on inactive telemetry does nothing."""
    t = NoOpTelemetry()
    t.record_error(None, Exception("test"))


def test_set_success_noop():
    """set_success on inactive telemetry does nothing."""
    t = NoOpTelemetry()
    t.set_success(None)


@pytest.mark.asyncio
async def test_flow_with_telemetry_disabled():
    """Flow runs normally with disabled telemetry."""
    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="telem_flow", description="Telemetry flow")
    flow.telemetry = TelemetryManager(enabled=False)
    flow.then(task).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6


@pytest.mark.asyncio
async def test_flow_with_noop_telemetry():
    """Flow runs normally with NoOpTelemetry."""
    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="noop_telem", description="NoOp telemetry flow")
    flow.telemetry = NoOpTelemetry()
    flow.then(task).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11


@pytest.mark.asyncio
async def test_flow_without_telemetry():
    """Flow runs normally without any telemetry set."""
    task = create_task(
        id="t1",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="no_telem", description="No telemetry")
    flow.then(task).register()

    result = await flow.run({"value": 20})
    assert result["value"] == 21
