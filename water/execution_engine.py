import inspect
import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from water.types import (
    ExecutionGraph,
    ExecutionNode,
    InputData,
    OutputData,
    SequentialNode,
    ParallelNode,
    BranchNode,
    LoopNode
)
from water.context import ExecutionContext

logger = logging.getLogger(__name__)

class NodeType(Enum):
    """Enumeration of supported execution node types."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    BRANCH = "branch"
    LOOP = "loop"
    MAP = "map"


class FlowPausedError(Exception):
    """Raised when a flow execution is paused."""
    pass


class FlowStoppedError(Exception):
    """Raised when a flow execution is stopped."""
    pass


class ExecutionEngine:
    """
    Core execution engine for Water flows.

    Orchestrates the execution of different node types including sequential tasks,
    parallel execution, conditional branching, and loops. Supports pause/stop/resume
    via an optional storage backend.
    """

    @staticmethod
    async def run(
        execution_graph: ExecutionGraph,
        input_data: InputData,
        flow_id: str,
        flow_metadata: Dict[str, Any] = None,
        storage: Optional[Any] = None,
        resume_from: Optional[Dict[str, Any]] = None,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        """
        Execute a complete flow execution graph.

        Args:
            execution_graph: List of execution nodes to process
            input_data: Initial input data
            flow_id: Unique identifier for the flow execution
            flow_metadata: Optional metadata for the flow
            storage: Optional storage backend for persistence and pause/resume
            resume_from: Optional dict with resume state (execution_id, node_index, data, context_state)

        Returns:
            Final output data after all nodes are executed

        Raises:
            FlowPausedError: If the flow was paused during execution
            FlowStoppedError: If the flow was stopped during execution
        """
        if resume_from:
            context = ExecutionContext(
                flow_id=flow_id,
                execution_id=resume_from["execution_id"],
                flow_metadata=flow_metadata or {},
                input_data=input_data,
            )
            # Restore context state
            ctx_state = resume_from.get("context_state", {})
            context._task_outputs = ctx_state.get("task_outputs", {})
            context._step_history = ctx_state.get("step_history", [])
            context.step_number = ctx_state.get("step_number", 0)

            data: OutputData = resume_from["data"]
            start_index = resume_from["node_index"]
        else:
            context = ExecutionContext(
                flow_id=flow_id,
                flow_metadata=flow_metadata or {},
                input_data=input_data
            )
            data = input_data
            start_index = 0

        # Save initial session state if storage is provided
        if storage:
            from water.storage import FlowSession, FlowStatus
            session = await storage.get_session(context.execution_id)
            if not session:
                session = FlowSession(
                    flow_id=flow_id,
                    input_data=input_data,
                    execution_id=context.execution_id,
                    status=FlowStatus.RUNNING,
                )
            else:
                session.status = FlowStatus.RUNNING
            await storage.save_session(session)

        try:
            for node_index in range(start_index, len(execution_graph)):
                # Check for pause/stop signals before each node
                if storage:
                    session = await storage.get_session(context.execution_id)
                    if session and session.status == FlowStatus.PAUSED:
                        # Save current state for resume
                        session.current_node_index = node_index
                        session.current_data = data
                        session.context_state = {
                            "task_outputs": context._task_outputs,
                            "step_history": context._step_history,
                            "step_number": context.step_number,
                            "flow_version": context.flow_metadata.get("_flow_version"),
                        }
                        await storage.save_session(session)
                        raise FlowPausedError(
                            f"Flow {flow_id} paused at node {node_index} "
                            f"(execution: {context.execution_id})"
                        )
                    elif session and session.status == FlowStatus.STOPPED:
                        session.current_node_index = node_index
                        session.current_data = data
                        session.context_state = {
                            "task_outputs": context._task_outputs,
                            "step_history": context._step_history,
                            "step_number": context.step_number,
                            "flow_version": context.flow_metadata.get("_flow_version"),
                        }
                        await storage.save_session(session)
                        raise FlowStoppedError(
                            f"Flow {flow_id} stopped at node {node_index} "
                            f"(execution: {context.execution_id})"
                        )

                node = execution_graph[node_index]
                data = await ExecutionEngine._execute_node(
                    node, data, context, storage, node_index, hooks, event_emitter
                )

            # Mark as completed
            if storage:
                session = await storage.get_session(context.execution_id)
                if session:
                    session.status = FlowStatus.COMPLETED
                    session.result = data
                    session.current_data = data
                    session.current_node_index = len(execution_graph)
                    await storage.save_session(session)

        except (FlowPausedError, FlowStoppedError):
            raise
        except Exception as e:
            if storage:
                session = await storage.get_session(context.execution_id)
                if session:
                    session.status = FlowStatus.FAILED
                    session.error = str(e)
                    await storage.save_session(session)
            raise

        return data

    @staticmethod
    async def _execute_node(
        node: ExecutionNode,
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        """
        Route execution to the appropriate node type handler.
        """
        try:
            node_type = NodeType(node["type"])
        except ValueError:
            raise ValueError(f"Unknown node type: {node['type']}")

        handlers = {
            NodeType.SEQUENTIAL: ExecutionEngine._execute_sequential,
            NodeType.PARALLEL: ExecutionEngine._execute_parallel,
            NodeType.BRANCH: ExecutionEngine._execute_branch,
            NodeType.LOOP: ExecutionEngine._execute_loop,
            NodeType.MAP: ExecutionEngine._execute_map,
        }

        handler = handlers.get(node_type)
        if not handler:
            raise ValueError(f"Unhandled node type: {node_type}")

        return await handler(node, data, context, storage, node_index, hooks, event_emitter)

    @staticmethod
    async def _execute_task(
        task: Any,
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        """
        Execute a single task, handling both sync and async functions.
        Supports retry with backoff, per-task timeouts, hooks, events, and storage recording.
        """
        from water.storage import TaskRun

        params: Dict[str, InputData] = {"input_data": data}

        # Update context with current task info
        context.task_id = task.id
        context.step_start_time = datetime.utcnow()
        context.step_number += 1

        retry_count = getattr(task, "retry_count", 0)
        retry_delay = getattr(task, "retry_delay", 0.0)
        retry_backoff = getattr(task, "retry_backoff", 1.0)
        task_timeout = getattr(task, "timeout", None)
        max_attempts = retry_count + 1
        last_error = None

        # Emit task start hook and event
        if hooks:
            await hooks.emit(
                "on_task_start",
                task_id=task.id,
                input_data=data,
                context=context,
            )
        if event_emitter:
            from water.events import FlowEvent
            await event_emitter.emit(FlowEvent(
                "task_start", context.flow_id,
                task_id=task.id, execution_id=context.execution_id,
                data={"input": data},
            ))

        for attempt in range(1, max_attempts + 1):
            context.attempt_number = attempt

            # Create task run record
            task_run = None
            if storage:
                task_run = TaskRun(
                    execution_id=context.execution_id,
                    task_id=task.id,
                    node_index=node_index,
                    status="running",
                    input_data=data,
                    started_at=datetime.utcnow(),
                )
                await storage.save_task_run(task_run)

            try:
                # Validate input against schema if enabled
                if getattr(task, "validate_schema", False) and hasattr(task, "input_schema"):
                    try:
                        task.input_schema(**data)
                    except Exception as ve:
                        raise ValueError(
                            f"Task '{task.id}' input validation failed: {ve}"
                        ) from ve

                # Execute the task (with optional timeout)
                if inspect.iscoroutinefunction(task.execute):
                    coro = task.execute(params, context)
                    if task_timeout:
                        result = await asyncio.wait_for(coro, timeout=task_timeout)
                    else:
                        result = await coro
                else:
                    if task_timeout:
                        loop = asyncio.get_event_loop()
                        result = await asyncio.wait_for(
                            loop.run_in_executor(None, task.execute, params, context),
                            timeout=task_timeout,
                        )
                    else:
                        result = task.execute(params, context)

                # Validate output against schema if enabled
                if getattr(task, "validate_schema", False) and hasattr(task, "output_schema"):
                    try:
                        task.output_schema(**result)
                    except Exception as ve:
                        raise ValueError(
                            f"Task '{task.id}' output validation failed: {ve}"
                        ) from ve

                # Store the task result in context for future tasks to access
                context.add_task_output(task.id, result)

                # Update task run record
                if storage and task_run:
                    task_run.status = "completed"
                    task_run.output_data = result
                    task_run.completed_at = datetime.utcnow()
                    await storage.save_task_run(task_run)

                # Emit task complete hook and event
                if hooks:
                    await hooks.emit(
                        "on_task_complete",
                        task_id=task.id,
                        input_data=data,
                        output_data=result,
                        context=context,
                    )
                if event_emitter:
                    from water.events import FlowEvent
                    await event_emitter.emit(FlowEvent(
                        "task_complete", context.flow_id,
                        task_id=task.id, execution_id=context.execution_id,
                        data={"output": result},
                    ))

                return result

            except Exception as e:
                last_error = e
                if storage and task_run:
                    task_run.status = "failed"
                    task_run.error = str(e)
                    task_run.completed_at = datetime.utcnow()
                    await storage.save_task_run(task_run)

                if attempt < max_attempts:
                    delay = retry_delay * (retry_backoff ** (attempt - 1))
                    if delay > 0:
                        await asyncio.sleep(delay)
                    logger.info(
                        f"Retrying task {task.id} (attempt {attempt + 1}/{max_attempts}) "
                        f"after error: {e}"
                    )
                else:
                    # Emit task error hook and event
                    if hooks:
                        await hooks.emit(
                            "on_task_error",
                            task_id=task.id,
                            input_data=data,
                            error=last_error,
                            context=context,
                        )
                    if event_emitter:
                        from water.events import FlowEvent
                        await event_emitter.emit(FlowEvent(
                            "task_error", context.flow_id,
                            task_id=task.id, execution_id=context.execution_id,
                            data={"error": str(last_error)},
                        ))
                    raise last_error

    @staticmethod
    async def _execute_sequential(
        node: SequentialNode,
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        # Support conditional skip via 'when' key
        when = node.get("when")
        if when is not None and not when(data):
            return data  # Skip task, pass data through

        task = node["task"]
        return await ExecutionEngine._execute_task(task, data, context, storage, node_index, hooks, event_emitter)

    @staticmethod
    async def _execute_parallel(
        node: ParallelNode,
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        tasks = node["tasks"]

        async def execute_single_task(task):
            return await ExecutionEngine._execute_task(task, data, context, storage, node_index, hooks, event_emitter)

        coroutines = [execute_single_task(task) for task in tasks]
        results: List[OutputData] = await asyncio.gather(*coroutines)

        parallel_results = {task.id: result for task, result in zip(tasks, results)}
        context.add_task_output("_parallel_results", parallel_results)

        return parallel_results

    @staticmethod
    async def _execute_branch(
        node: BranchNode,
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        branches = node["branches"]

        for branch in branches:
            condition = branch["condition"]

            if condition(data):
                task = branch["task"]
                return await ExecutionEngine._execute_task(task, data, context, storage, node_index, hooks, event_emitter)

        return data

    @staticmethod
    async def _execute_loop(
        node: LoopNode,
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        condition = node["condition"]
        task = node["task"]
        max_iterations: int = node.get("max_iterations", 100)

        iteration_count: int = 0
        current_data: OutputData = data

        while iteration_count < max_iterations:
            if not condition(current_data):
                break

            # Check for pause/stop signals during loops
            if storage:
                from water.storage import FlowStatus
                session = await storage.get_session(context.execution_id)
                if session and session.status == FlowStatus.PAUSED:
                    session.current_node_index = node_index
                    session.current_data = current_data
                    session.context_state = {
                        "task_outputs": context._task_outputs,
                        "step_history": context._step_history,
                        "step_number": context.step_number,
                    }
                    await storage.save_session(session)
                    raise FlowPausedError(
                        f"Flow paused during loop at node {node_index}, "
                        f"iteration {iteration_count}"
                    )
                elif session and session.status == FlowStatus.STOPPED:
                    session.current_node_index = node_index
                    session.current_data = current_data
                    session.context_state = {
                        "task_outputs": context._task_outputs,
                        "step_history": context._step_history,
                        "step_number": context.step_number,
                    }
                    await storage.save_session(session)
                    raise FlowStoppedError(
                        f"Flow stopped during loop at node {node_index}, "
                        f"iteration {iteration_count}"
                    )

            current_data = await ExecutionEngine._execute_task(
                task, current_data, context, storage, node_index, hooks, event_emitter
            )
            iteration_count += 1

        if iteration_count >= max_iterations:
            logger.warning(
                f"Loop reached maximum iterations ({max_iterations}) "
                f"for flow {context.flow_id}"
            )

        return current_data

    @staticmethod
    async def _execute_map(
        node: Dict[str, Any],
        data: InputData,
        context: ExecutionContext,
        storage: Optional[Any] = None,
        node_index: int = 0,
        hooks: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
    ) -> OutputData:
        """
        Execute a task once per item in a list field, in parallel.

        The node must have 'task' and 'over' keys. 'over' is the key in
        the input data containing the list to iterate over.
        """
        task = node["task"]
        over_key = node["over"]

        items = data.get(over_key, [])
        if not isinstance(items, list):
            raise ValueError(f"Map 'over' key '{over_key}' must reference a list, got {type(items).__name__}")

        async def execute_for_item(item):
            item_data = {**data, over_key: item}
            return await ExecutionEngine._execute_task(
                task, item_data, context, storage, node_index, hooks, event_emitter
            )

        results = await asyncio.gather(*[execute_for_item(item) for item in items])
        return {"results": list(results)}
