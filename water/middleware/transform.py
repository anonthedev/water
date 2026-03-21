"""TransformMiddleware — delegates to user-supplied callables."""

from typing import Any, Callable, Optional

from water.middleware.base import Middleware


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
        order: int = 0,
    ) -> None:
        super().__init__(order=order)
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
