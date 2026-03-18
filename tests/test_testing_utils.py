import pytest
from pydantic import BaseModel
from water import Flow, create_task, MockTask, FlowTestRunner


# --- Schemas ---

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


# --- MockTask tests ---

@pytest.mark.asyncio
async def test_mock_task_returns_value():
    """MockTask with return_value works when used in a flow."""
    mock = MockTask(id="add_ten", return_value={"value": 42})

    flow = Flow(id="mock_return_flow", description="Test MockTask return_value")
    flow.then(mock).register()

    result = await flow.run({"value": 1})
    assert result["value"] == 42


@pytest.mark.asyncio
async def test_mock_task_tracks_calls():
    """call_count and calls list are populated after execution."""
    mock = MockTask(id="tracker", return_value={"value": 10})

    flow = Flow(id="mock_track_flow", description="Test MockTask tracking")
    flow.then(mock).register()

    await flow.run({"value": 5})
    await flow.run({"value": 7})

    assert mock.call_count == 2
    assert len(mock.calls) == 2
    assert mock.calls[0] == {"value": 5}
    assert mock.calls[1] == {"value": 7}
    assert mock.last_call == {"value": 7}


@pytest.mark.asyncio
async def test_mock_task_side_effect_callable():
    """side_effect as a callable is invoked with input_data."""
    mock = MockTask(
        id="doubler",
        side_effect=lambda data: {"value": data["value"] * 2},
    )

    flow = Flow(id="mock_side_effect_flow", description="Test MockTask side_effect callable")
    flow.then(mock).register()

    result = await flow.run({"value": 6})
    assert result["value"] == 12


@pytest.mark.asyncio
async def test_mock_task_side_effect_exception():
    """side_effect as an Exception class causes execute to raise."""
    mock = MockTask(id="exploder", side_effect=ValueError("boom"))

    flow = Flow(id="mock_exception_flow", description="Test MockTask side_effect exception")
    flow.then(mock).register()

    with pytest.raises(ValueError, match="boom"):
        await flow.run({"value": 1})


def test_mock_task_assert_called():
    """assert_called raises when not called, passes after a call."""
    mock = MockTask(id="checker", return_value={"value": 0})

    with pytest.raises(AssertionError, match="was never called"):
        mock.assert_called()

    # Simulate a call directly
    mock.execute({"input_data": {"value": 1}})
    mock.assert_called()  # Should not raise


def test_mock_task_assert_called_with():
    """assert_called_with checks last call's input_data."""
    mock = MockTask(id="call_checker", return_value={"value": 0})
    mock.execute({"input_data": {"value": 99}})

    mock.assert_called_with({"value": 99})

    with pytest.raises(AssertionError):
        mock.assert_called_with({"value": 1})


def test_mock_task_reset():
    """reset clears all tracking state."""
    mock = MockTask(id="resettable", return_value={"value": 0})
    mock.execute({"input_data": {"value": 1}})
    mock.execute({"input_data": {"value": 2}})

    assert mock.call_count == 2
    assert len(mock.calls) == 2

    mock.reset()

    assert mock.call_count == 0
    assert mock.calls == []
    assert mock.last_call is None

    with pytest.raises(AssertionError, match="was never called"):
        mock.assert_called()


# --- FlowTestRunner tests ---

@pytest.mark.asyncio
async def test_flow_test_runner_success():
    """FlowTestRunner.run captures result; assert_completed passes."""
    mock = MockTask(id="success_task", return_value={"value": 100})

    flow = Flow(id="runner_success_flow", description="Test FlowTestRunner success")
    flow.then(mock).register()

    runner = FlowTestRunner(flow)
    await runner.run({"value": 1})

    runner.assert_completed()
    assert runner.result == {"value": 100}
    assert runner.error is None


@pytest.mark.asyncio
async def test_flow_test_runner_failure():
    """FlowTestRunner.run_expecting_error captures error; assert_failed passes."""
    mock = MockTask(id="fail_task", side_effect=RuntimeError("task broke"))

    flow = Flow(id="runner_fail_flow", description="Test FlowTestRunner failure")
    flow.then(mock).register()

    runner = FlowTestRunner(flow)
    err = await runner.run_expecting_error({"value": 1}, error_type=RuntimeError)

    runner.assert_failed()
    assert isinstance(err, RuntimeError)
    assert "task broke" in str(err)
    assert runner.result is None


@pytest.mark.asyncio
async def test_flow_test_runner_assert_result():
    """assert_result_contains and assert_result_equals check result dict."""
    mock = MockTask(
        id="result_task",
        return_value={"name": "water", "version": 2},
    )

    flow = Flow(id="runner_result_flow", description="Test FlowTestRunner result assertions")
    flow.then(mock).register()

    runner = FlowTestRunner(flow)
    await runner.run({"input": "x"})

    runner.assert_result_contains("name")
    runner.assert_result_contains("name", "water")
    runner.assert_result_contains("version", 2)
    runner.assert_result_equals({"name": "water", "version": 2})

    with pytest.raises(AssertionError):
        runner.assert_result_contains("missing_key")

    with pytest.raises(AssertionError):
        runner.assert_result_equals({"name": "wrong"})
