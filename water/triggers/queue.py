"""Queue trigger for message-based flow execution."""

import asyncio
from typing import Any, Callable, Dict, List, Optional

from water.triggers.base import Trigger, TriggerEvent


class QueueTrigger(Trigger):
    """Trigger that fires when a message is pushed onto an in-memory queue.

    This provides a simple pub/sub-style trigger that can be used for
    decoupled, asynchronous flow invocation within a single process.

    Args:
        flow_name: The ID of the flow to execute.
        transform: Optional callable to transform each message payload.
        max_size: Maximum queue size (0 = unlimited).

    Example::

        trigger = QueueTrigger(flow_name="process-event")
        await trigger.start()
        await trigger.push({"user_id": "123", "action": "signup"})
    """

    def __init__(
        self,
        flow_name: str,
        transform: Optional[Callable] = None,
        max_size: int = 0,
    ) -> None:
        super().__init__(flow_name, transform)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._task: Optional[asyncio.Task] = None
        self._processed_events: List[TriggerEvent] = []

    @property
    def pending(self) -> int:
        """Number of messages waiting in the queue."""
        return self._queue.qsize()

    async def push(self, message: Dict[str, Any]) -> None:
        """Add a message to the queue.

        Args:
            message: Dictionary payload to enqueue.

        Raises:
            RuntimeError: If the trigger is not active.
        """
        if not self._active:
            raise RuntimeError("QueueTrigger is not active. Call start() first.")
        await self._queue.put(message)

    async def pop(self) -> TriggerEvent:
        """Wait for and retrieve the next message from the queue.

        Returns:
            A TriggerEvent wrapping the dequeued message.
        """
        message = await self._queue.get()
        event = self.create_event(message)
        self._processed_events.append(event)
        return event

    async def pop_nowait(self) -> Optional[TriggerEvent]:
        """Retrieve the next message without waiting.

        Returns:
            A TriggerEvent if a message is available, ``None`` otherwise.
        """
        try:
            message = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        event = self.create_event(message)
        self._processed_events.append(event)
        return event

    async def _consume_loop(self, callback: Callable) -> None:
        """Internal loop that consumes messages and invokes the callback."""
        while self._active:
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            event = self.create_event(message)
            self._processed_events.append(event)
            await callback(event)

    async def start(self, callback: Optional[Callable] = None) -> None:
        """Activate the queue trigger.

        Args:
            callback: Optional async callable invoked for each dequeued message.
        """
        self._active = True
        if callback:
            self._task = asyncio.create_task(self._consume_loop(callback))

    async def stop(self) -> None:
        """Deactivate the queue trigger and cancel the consumer task."""
        self._active = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
