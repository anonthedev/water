"""
Testing utilities for the Water framework.

Provides MockTask and FlowTestRunner to simplify unit testing of flows.
"""

from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

from water.task import Task


class _GenericInput(BaseModel):
    """Default input schema for MockTask when none is provided."""
    data: Dict[str, Any] = {}


class _GenericOutput(BaseModel):
    """Default output schema for MockTask when none is provided."""
    data: Dict[str, Any] = {}


class MockTask(Task):
    """
    A test double for Task that records calls and returns canned responses.

    Use ``return_value`` for a fixed response, or ``side_effect`` for dynamic
    behaviour (callable) or to simulate errors (Exception subclass/instance).
    """

    def __init__(
        self,
        id: str,
        return_value: Optional[Dict[str, Any]] = None,
        side_effect: Any = None,
        input_schema: Optional[Type[BaseModel]] = None,
        output_schema: Optional[Type[BaseModel]] = None,
    ) -> None:
        self.id = id
        self.description = f"MockTask {id}"
        self.input_schema = input_schema if input_schema is not None else _GenericInput
        self.output_schema = output_schema if output_schema is not None else _GenericOutput
        self.retry_count = 0
        self.retry_delay = 0
        self.retry_backoff = 1
        self.timeout = None
        self.validate_schema = False
        self.rate_limit = None
        self.cache = None
        self.circuit_breaker = None

        self._return_value = return_value
        self._side_effect = side_effect

        # Tracking state
        self.call_count: int = 0
        self.calls: List[Dict[str, Any]] = []
        self.last_call: Optional[Dict[str, Any]] = None

        # Assign the execute callable
        self.execute = self._execute

    def _execute(self, params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """Record the call and return the configured response."""
        input_data = params.get("input_data", params)
        self.call_count += 1
        self.calls.append(input_data)
        self.last_call = input_data

        if self._side_effect is not None:
            if isinstance(self._side_effect, type) and issubclass(self._side_effect, BaseException):
                raise self._side_effect()
            if isinstance(self._side_effect, BaseException):
                raise self._side_effect
            if callable(self._side_effect):
                return self._side_effect(input_data)

        if self._return_value is not None:
            return self._return_value

        return {}

    # -- Assertion helpers --------------------------------------------------

    def reset(self) -> None:
        """Clear all tracking state."""
        self.call_count = 0
        self.calls = []
        self.last_call = None

    def assert_called(self) -> None:
        """Raise ``AssertionError`` if the task was never called."""
        if self.call_count == 0:
            raise AssertionError(f"MockTask '{self.id}' was never called")

    def assert_called_with(self, expected_data: Dict[str, Any]) -> None:
        """Raise ``AssertionError`` if the last call's input_data differs."""
        if self.last_call is None:
            raise AssertionError(f"MockTask '{self.id}' was never called")
        if self.last_call != expected_data:
            raise AssertionError(
                f"MockTask '{self.id}' last called with {self.last_call}, "
                f"expected {expected_data}"
            )

    def assert_call_count(self, n: int) -> None:
        """Raise ``AssertionError`` if the call count does not match ``n``."""
        if self.call_count != n:
            raise AssertionError(
                f"MockTask '{self.id}' called {self.call_count} time(s), expected {n}"
            )


class FlowTestRunner:
    """
    Convenience wrapper for running a Flow in tests and making assertions.

    Usage::

        runner = FlowTestRunner(my_flow)
        await runner.run({"key": "value"})
        runner.assert_completed()
        runner.assert_result_contains("key")
    """

    def __init__(self, flow: Any) -> None:
        self._flow = flow
        self._result: Optional[Dict[str, Any]] = None
        self._error: Optional[Exception] = None

    @property
    def result(self) -> Optional[Dict[str, Any]]:
        """The result of the last ``run`` invocation, or ``None``."""
        return self._result

    @property
    def error(self) -> Optional[Exception]:
        """The error from the last ``run`` invocation, or ``None``."""
        return self._error

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the wrapped flow and capture the result or error."""
        self._result = None
        self._error = None
        try:
            self._result = await self._flow.run(input_data)
            return self._result
        except Exception as exc:
            self._error = exc
            raise

    async def run_expecting_error(
        self,
        input_data: Dict[str, Any],
        error_type: Type[Exception] = Exception,
    ) -> Exception:
        """Run the flow, asserting that it raises ``error_type``."""
        self._result = None
        self._error = None
        try:
            self._result = await self._flow.run(input_data)
        except Exception as exc:
            self._error = exc
            if not isinstance(exc, error_type):
                raise AssertionError(
                    f"Expected {error_type.__name__}, got {type(exc).__name__}: {exc}"
                ) from exc
            return exc
        raise AssertionError(
            f"Expected {error_type.__name__} but flow completed successfully"
        )

    # -- Assertion helpers --------------------------------------------------

    def assert_completed(self) -> None:
        """Assert the last run succeeded (no error, result present)."""
        if self._error is not None:
            raise AssertionError(
                f"Expected flow to complete but it raised {type(self._error).__name__}: {self._error}"
            )
        if self._result is None:
            raise AssertionError("Flow has not been run yet")

    def assert_failed(self) -> None:
        """Assert the last run failed (error was captured)."""
        if self._error is None:
            raise AssertionError("Expected flow to fail but it completed successfully")

    def assert_result_contains(self, key: str, value: Any = None) -> None:
        """Assert the result dict contains ``key``, optionally with ``value``."""
        if self._result is None:
            raise AssertionError("No result available — flow has not been run or it failed")
        if key not in self._result:
            raise AssertionError(
                f"Result does not contain key '{key}'. Keys: {list(self._result.keys())}"
            )
        if value is not None and self._result[key] != value:
            raise AssertionError(
                f"Result['{key}'] = {self._result[key]!r}, expected {value!r}"
            )

    def assert_result_equals(self, expected: Dict[str, Any]) -> None:
        """Assert the result dict equals ``expected`` exactly."""
        if self._result is None:
            raise AssertionError("No result available — flow has not been run or it failed")
        if self._result != expected:
            raise AssertionError(
                f"Result {self._result} does not equal expected {expected}"
            )
