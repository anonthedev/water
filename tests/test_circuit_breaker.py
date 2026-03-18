import pytest
import time
from pydantic import BaseModel
from water import create_task, Flow, CircuitBreaker, CircuitBreakerOpen


class InputSchema(BaseModel):
    value: int


class OutputSchema(BaseModel):
    value: int


def test_circuit_breaker_closed_by_default():
    """A new circuit breaker starts in the closed state."""
    cb = CircuitBreaker()
    assert cb.state == "closed"
    assert cb.can_execute() is True


def test_circuit_breaker_opens_after_threshold():
    """Circuit opens after N consecutive failures and rejects calls."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    assert cb.can_execute() is False

    with pytest.raises(CircuitBreakerOpen):
        raise CircuitBreakerOpen("open")


def test_circuit_breaker_resets_on_success():
    """A success resets the failure count and closes the circuit."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"

    cb.record_success()
    assert cb.state == "closed"

    # Need full threshold again to open
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    assert cb.can_execute() is True


def test_circuit_breaker_half_open_after_timeout():
    """After recovery timeout, circuit transitions to half_open and allows one call."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"
    assert cb.can_execute() is False

    # Wait for recovery timeout
    time.sleep(0.06)

    assert cb.state == "half_open"
    assert cb.can_execute() is True

    # A success closes it again
    cb.record_success()
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_task_with_circuit_breaker_integration():
    """Full integration: task protected by circuit breaker opens after failures."""
    call_count = 0

    def failing_execute(params, context):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("API down")

    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

    task = create_task(
        id="api_call",
        description="Failing API call",
        input_schema=InputSchema,
        output_schema=OutputSchema,
        execute=failing_execute,
        circuit_breaker=cb,
    )

    flow = Flow(id="cb_flow", description="Circuit breaker flow")
    flow.then(task).register()

    # First two calls fail and record failures
    with pytest.raises(RuntimeError):
        await flow.run({"value": 1})
    with pytest.raises(RuntimeError):
        await flow.run({"value": 2})

    assert cb.state == "open"
    assert call_count == 2

    # Third call is blocked by circuit breaker without executing
    with pytest.raises(CircuitBreakerOpen):
        await flow.run({"value": 3})

    assert call_count == 2  # No additional execution


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets_in_flow():
    """A successful call through the flow resets the circuit breaker."""
    call_count = 0

    def succeed_execute(params, context):
        nonlocal call_count
        call_count += 1
        return {"value": params["input_data"]["value"] + 1}

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

    # Pre-load some failures
    cb.record_failure()
    cb.record_failure()

    task = create_task(
        id="good_api",
        description="Succeeding API call",
        input_schema=InputSchema,
        output_schema=OutputSchema,
        execute=succeed_execute,
        circuit_breaker=cb,
    )

    flow = Flow(id="cb_reset_flow", description="Circuit breaker reset flow")
    flow.then(task).register()

    result = await flow.run({"value": 10})
    assert result["value"] == 11
    assert cb.state == "closed"
    assert call_count == 1
