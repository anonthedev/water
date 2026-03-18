import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Hook function signatures
# on_task_start(task_id, input_data, context)
# on_task_complete(task_id, input_data, output_data, context)
# on_task_error(task_id, input_data, error, context)
# on_flow_start(flow_id, input_data)
# on_flow_complete(flow_id, output_data)
# on_flow_error(flow_id, error)

HookFunction = Callable[..., Any]


class HookManager:
    """Manages lifecycle hooks for flow and task execution."""

    def __init__(self) -> None:
        self._hooks: Dict[str, List[HookFunction]] = {
            "on_task_start": [],
            "on_task_complete": [],
            "on_task_error": [],
            "on_flow_start": [],
            "on_flow_complete": [],
            "on_flow_error": [],
        }

    def on(self, event: str, callback: HookFunction) -> None:
        """
        Register a hook callback for an event.

        Args:
            event: Event name (on_task_start, on_task_complete, on_task_error,
                   on_flow_start, on_flow_complete, on_flow_error)
            callback: Function to call when the event fires
        """
        if event not in self._hooks:
            raise ValueError(
                f"Unknown hook event: {event}. "
                f"Valid events: {list(self._hooks.keys())}"
            )
        self._hooks[event].append(callback)

    async def emit(self, event: str, **kwargs: Any) -> None:
        """
        Fire all registered callbacks for an event.

        Args:
            event: Event name
            **kwargs: Arguments to pass to the callbacks
        """
        for callback in self._hooks.get(event, []):
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(**kwargs)
                else:
                    callback(**kwargs)
            except Exception as e:
                logger.warning(f"Hook {event} callback raised: {e}")

    def has_hooks(self, event: str) -> bool:
        """Check if any hooks are registered for an event."""
        return bool(self._hooks.get(event))
