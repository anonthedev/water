"""
Middleware support for Water flows.

Middleware intercepts task execution, allowing data transformation or logging
between tasks without explicit task nodes. Each middleware has ``before_task``
and ``after_task`` hooks that can inspect or modify the data flowing through
the pipeline.
"""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class Middleware:
    """
    Base middleware class.

    Subclass and override ``before_task`` and/or ``after_task`` to intercept
    task execution.  Both methods receive the current data and must return
    the (possibly modified) data dict.
    """

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        """Called before each task executes. Return (possibly modified) data."""
        return data

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        """Called after each task executes. Return (possibly modified) result."""
        return result


class LoggingMiddleware(Middleware):
    """
    Middleware that logs task_id, input keys, and output keys for every task.

    Does **not** modify the data — purely observational.
    """

    def __init__(self, logger_instance: Optional[logging.Logger] = None) -> None:
        self._logger = logger_instance or logger

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        self._logger.info(
            "Middleware [before] task=%s input_keys=%s",
            task_id,
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        return data

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        self._logger.info(
            "Middleware [after]  task=%s output_keys=%s",
            task_id,
            list(result.keys()) if isinstance(result, dict) else type(result).__name__,
        )
        return result


class TransformMiddleware(Middleware):
    """
    Middleware that delegates to user-supplied callables for custom transforms.

    ``before_fn(task_id, data, context) -> data``
    ``after_fn(task_id, data, result, context) -> result``

    Either callable may be ``None`` (no-op).  Callables can be sync or async.
    """

    def __init__(
        self,
        before_fn: Optional[Callable] = None,
        after_fn: Optional[Callable] = None,
    ) -> None:
        self._before_fn = before_fn
        self._after_fn = after_fn

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        if self._before_fn is not None:
            import inspect
            result = self._before_fn(task_id, data, context)
            if inspect.isawaitable(result):
                result = await result
            return result
        return data

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        if self._after_fn is not None:
            import inspect
            out = self._after_fn(task_id, data, result, context)
            if inspect.isawaitable(out):
                out = await out
            return out
        return result
