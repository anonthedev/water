"""
Streaming / Real-time Progress support via SSE and WebSocket-compatible event streams.

Provides StreamEvent, StreamManager, and StreamingFlow for emitting and consuming
real-time progress events from Water flow executions.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from water.core.flow import Flow

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """A single streaming event emitted during flow execution."""

    event_type: str  # "flow_start", "task_start", "task_progress", "task_complete", "task_error", "flow_complete", "flow_error", "token"
    flow_id: str
    execution_id: str
    task_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class StreamManager:
    """Manages event subscriptions and dispatches StreamEvents to subscribers.

    Subscribers receive events via asyncio.Queue instances. A subscriber can
    listen to a specific execution_id or to all executions (global).
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}  # execution_id -> queues
        self._global_subscribers: List[asyncio.Queue] = []

    def subscribe(self, execution_id: Optional[str] = None) -> asyncio.Queue:
        """Subscribe to events for a specific execution or all executions.

        Args:
            execution_id: If provided, only receive events for this execution.
                          If None, receive events for all executions.

        Returns:
            An asyncio.Queue that will receive StreamEvent instances.
        """
        queue: asyncio.Queue = asyncio.Queue()
        if execution_id is None:
            self._global_subscribers.append(queue)
        else:
            if execution_id not in self._subscribers:
                self._subscribers[execution_id] = []
            self._subscribers[execution_id].append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue, execution_id: Optional[str] = None) -> None:
        """Unsubscribe a queue from events.

        Args:
            queue: The queue to remove.
            execution_id: The execution_id it was subscribed to, or None for global.
        """
        if execution_id is None:
            try:
                self._global_subscribers.remove(queue)
            except ValueError:
                pass
        else:
            queues = self._subscribers.get(execution_id, [])
            try:
                queues.remove(queue)
            except ValueError:
                pass
            if not queues and execution_id in self._subscribers:
                del self._subscribers[execution_id]

    async def emit(self, event: StreamEvent) -> None:
        """Emit an event to all relevant subscribers.

        Sends to execution-specific subscribers and all global subscribers.
        Uses put_nowait to avoid blocking the emitter.

        Args:
            event: The StreamEvent to broadcast.
        """
        # Send to execution-specific subscribers
        for queue in self._subscribers.get(event.execution_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Stream subscriber queue full, dropping event %s for execution %s",
                    event.event_type,
                    event.execution_id,
                )

        # Send to global subscribers
        for queue in self._global_subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Global stream subscriber queue full, dropping event %s",
                    event.event_type,
                )

    async def stream_events(self, execution_id: Optional[str] = None) -> AsyncGenerator[StreamEvent, None]:
        """Async generator that yields events. For use with SSE.

        Args:
            execution_id: If provided, only yield events for this execution.
                          If None, yield events for all executions.

        Yields:
            StreamEvent instances as they arrive.
        """
        queue = self.subscribe(execution_id)
        try:
            while True:
                event = await queue.get()
                yield event
                # Stop streaming after terminal events
                if event.event_type in ("flow_complete", "flow_error"):
                    if execution_id is not None:
                        break
        finally:
            self.unsubscribe(queue, execution_id)

    def format_sse(self, event: StreamEvent) -> str:
        """Format event as an SSE string.

        Args:
            event: The StreamEvent to format.

        Returns:
            SSE-formatted string: 'event: {type}\\ndata: {json}\\n\\n'
        """
        event_dict = asdict(event)
        data_json = json.dumps(event_dict)
        return f"event: {event.event_type}\ndata: {data_json}\n\n"


class StreamingFlow:
    """A wrapper that adds streaming event emission to any Flow.

    Registers hooks on the underlying flow so that task and flow lifecycle
    events are automatically emitted to a StreamManager.
    """

    def __init__(self, flow: Flow, stream_manager: StreamManager) -> None:
        self.flow = flow
        self.stream = stream_manager
        self._execution_id: Optional[str] = None

    def _wire_hooks(self) -> None:
        """Register hook callbacks that emit stream events."""

        async def on_flow_start(flow_id: str, input_data: Any) -> None:
            await self.stream.emit(StreamEvent(
                event_type="flow_start",
                flow_id=flow_id,
                execution_id=self._execution_id,
                data={"input": _safe_serialize(input_data)},
            ))

        async def on_flow_complete(flow_id: str, output_data: Any) -> None:
            await self.stream.emit(StreamEvent(
                event_type="flow_complete",
                flow_id=flow_id,
                execution_id=self._execution_id,
                data={"output": _safe_serialize(output_data)},
            ))

        async def on_flow_error(flow_id: str, error: Exception) -> None:
            await self.stream.emit(StreamEvent(
                event_type="flow_error",
                flow_id=flow_id,
                execution_id=self._execution_id,
                data={"error": str(error)},
            ))

        async def on_task_start(task_id: str, input_data: Any, context: Any) -> None:
            await self.stream.emit(StreamEvent(
                event_type="task_start",
                flow_id=self.flow.id,
                execution_id=self._execution_id,
                task_id=task_id,
                data={"input": _safe_serialize(input_data)},
            ))

        async def on_task_complete(task_id: str, input_data: Any, output_data: Any, context: Any) -> None:
            await self.stream.emit(StreamEvent(
                event_type="task_complete",
                flow_id=self.flow.id,
                execution_id=self._execution_id,
                task_id=task_id,
                data={"output": _safe_serialize(output_data)},
            ))

        async def on_task_error(task_id: str, input_data: Any, error: Exception, context: Any) -> None:
            await self.stream.emit(StreamEvent(
                event_type="task_error",
                flow_id=self.flow.id,
                execution_id=self._execution_id,
                task_id=task_id,
                data={"error": str(error)},
            ))

        self.flow.hooks.on("on_flow_start", on_flow_start)
        self.flow.hooks.on("on_flow_complete", on_flow_complete)
        self.flow.hooks.on("on_flow_error", on_flow_error)
        self.flow.hooks.on("on_task_start", on_task_start)
        self.flow.hooks.on("on_task_complete", on_task_complete)
        self.flow.hooks.on("on_task_error", on_task_error)

    async def run(self, input_data: dict) -> dict:
        """Run flow while streaming progress events.

        Args:
            input_data: Input data for the flow.

        Returns:
            The flow result.
        """
        self._execution_id = uuid.uuid4().hex[:12]
        self._wire_hooks()
        return await self.flow.run(input_data)

    async def run_and_stream(self, input_data: dict) -> Tuple[dict, List[StreamEvent]]:
        """Run flow and return both result and collected events.

        Args:
            input_data: Input data for the flow.

        Returns:
            A tuple of (result, list_of_events).
        """
        self._execution_id = uuid.uuid4().hex[:12]
        self._wire_hooks()

        collected: List[StreamEvent] = []
        queue = self.stream.subscribe(self._execution_id)

        async def collect_events() -> None:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    collected.append(event)
                    if event.event_type in ("flow_complete", "flow_error"):
                        break
                except asyncio.TimeoutError:
                    break

        try:
            # Run flow and collector concurrently
            result_holder: List[Any] = []
            error_holder: List[Exception] = []

            async def run_flow() -> None:
                try:
                    r = await self.flow.run(input_data)
                    result_holder.append(r)
                except Exception as e:
                    error_holder.append(e)

            await asyncio.gather(run_flow(), collect_events())

            if error_holder:
                raise error_holder[0]

            return result_holder[0], collected
        finally:
            self.stream.unsubscribe(queue, self._execution_id)


def _safe_serialize(data: Any) -> Any:
    """Attempt to make data JSON-serializable."""
    if isinstance(data, dict):
        return {k: _safe_serialize(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_serialize(v) for v in data]
    if isinstance(data, (str, int, float, bool, type(None))):
        return data
    return str(data)


def add_streaming_routes(app: Any, stream_manager: StreamManager) -> None:
    """Add SSE streaming endpoints to a FastAPI application.

    Registers:
        GET /api/stream/{execution_id} - SSE endpoint for a specific execution
        GET /api/stream - SSE endpoint for all executions

    Args:
        app: A FastAPI application instance.
        stream_manager: The StreamManager to use for event subscriptions.
    """
    from starlette.responses import StreamingResponse

    async def _sse_generator(execution_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        queue = stream_manager.subscribe(execution_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield stream_manager.format_sse(event)
                    if event.event_type in ("flow_complete", "flow_error"):
                        if execution_id is not None:
                            break
                except asyncio.TimeoutError:
                    # Send a keep-alive comment
                    yield ": keep-alive\n\n"
        finally:
            stream_manager.unsubscribe(queue, execution_id)

    @app.get("/api/stream/{execution_id}")
    async def stream_execution(execution_id: str) -> StreamingResponse:
        return StreamingResponse(
            _sse_generator(execution_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/stream")
    async def stream_all() -> StreamingResponse:
        return StreamingResponse(
            _sse_generator(None),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
