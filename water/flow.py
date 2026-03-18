from typing import Any, List, Optional, Tuple, Dict, Type
import inspect
import uuid

from pydantic import BaseModel

from water.execution_engine import ExecutionEngine, NodeType, FlowPausedError, FlowStoppedError
from water.hooks import HookManager
from water.types import (
    InputData,
    OutputData,
    ConditionFunction,
    ExecutionNode
)

class Flow:
    """
    A workflow orchestrator that allows building and executing complex data processing pipelines.

    Flows support sequential execution, parallel processing, conditional branching, and loops.
    All flows must be registered before execution. Optionally accepts a storage backend
    to enable pause, stop, and resume of workflows.
    """

    def __init__(
        self,
        id: Optional[str] = None,
        description: Optional[str] = None,
        storage: Optional[Any] = None,
        version: Optional[str] = None,
    ) -> None:
        """
        Initialize a new Flow.

        Args:
            id: Unique identifier for the flow. Auto-generated if not provided.
            description: Human-readable description of the flow's purpose.
            storage: Optional storage backend for persistence and pause/resume support.
            version: Optional version string for tracking flow schema changes.
        """
        self.id: str = id if id else f"flow_{uuid.uuid4().hex[:8]}"
        self.description: str = description if description else f"Flow {self.id}"
        self.version: Optional[str] = version
        self._tasks: List[ExecutionNode] = []
        self._registered: bool = False
        self.metadata: Dict[str, Any] = {}
        self.storage = storage
        self.hooks = HookManager()
        self.events: Optional[Any] = None
        self.telemetry: Optional[Any] = None

    def _validate_registration_state(self) -> None:
        """Ensure flow is not registered when adding tasks."""
        if self._registered:
            raise RuntimeError("Cannot add tasks after registration")

    def _validate_task(self, task: Any) -> None:
        """Validate that a task is not None."""
        if task is None:
            raise ValueError("Task cannot be None")

    @staticmethod
    def _coerce_task(task: Any) -> Any:
        """Convert a Flow to a Task if needed."""
        if isinstance(task, Flow):
            return task.as_task()
        return task

    def _validate_condition(self, condition: ConditionFunction) -> None:
        """Validate that a condition function is not async."""
        if inspect.iscoroutinefunction(condition):
            raise ValueError("Branch conditions cannot be async functions")

    def _validate_loop_condition(self, condition: ConditionFunction) -> None:
        """Validate that a loop condition function is not async."""
        if inspect.iscoroutinefunction(condition):
            raise ValueError("Loop conditions cannot be async functions")

    def set_metadata(self, key: str, value: Any) -> 'Flow':
        """
        Set metadata for this flow.

        Args:
            key: The metadata key
            value: The metadata value

        Returns:
            Self for method chaining
        """
        self.metadata[key] = value
        return self

    def then(self, task: Any, when: Optional[ConditionFunction] = None) -> 'Flow':
        """
        Add a task to execute sequentially.

        Args:
            task: The task to execute
            when: Optional condition function. If provided and returns False,
                  the task is skipped and data passes through unchanged.

        Returns:
            Self for method chaining

        Raises:
            RuntimeError: If flow is already registered
            ValueError: If task is None
        """
        self._validate_registration_state()
        task = self._coerce_task(task)
        self._validate_task(task)
        if when is not None:
            self._validate_condition(when)

        node: ExecutionNode = {"type": NodeType.SEQUENTIAL.value, "task": task}
        if when is not None:
            node["when"] = when
        self._tasks.append(node)
        return self

    def map(self, task: Any, over: str) -> 'Flow':
        """
        Execute a task once per item in a list field, in parallel.

        Args:
            task: The task to execute for each item
            over: Key in the input data containing the list to iterate over.
                  Each task invocation receives the full data dict with that
                  key replaced by the individual item.

        Returns:
            Self for method chaining

        Raises:
            RuntimeError: If flow is already registered
            ValueError: If task is None or over is empty
        """
        self._validate_registration_state()
        task = self._coerce_task(task)
        self._validate_task(task)
        if not over:
            raise ValueError("Map 'over' key cannot be empty")

        node: ExecutionNode = {
            "type": NodeType.MAP.value,
            "task": task,
            "over": over,
        }
        self._tasks.append(node)
        return self

    def dag(self, tasks: List[Any], dependencies: Dict[str, List[str]] = None) -> 'Flow':
        """
        Add a DAG (directed acyclic graph) of tasks with automatic parallelization.

        Tasks with no dependencies run in parallel. As tasks complete, their
        dependents are unlocked and executed.

        Args:
            tasks: List of tasks to execute
            dependencies: Dict mapping task_id -> list of task_ids it depends on.
                          Tasks not listed have no dependencies.

        Returns:
            Self for method chaining

        Raises:
            RuntimeError: If flow is already registered
            ValueError: If task list is empty
        """
        self._validate_registration_state()
        if not tasks:
            raise ValueError("DAG task list cannot be empty")

        coerced = [self._coerce_task(t) for t in tasks]
        for task in coerced:
            self._validate_task(task)

        node: ExecutionNode = {
            "type": NodeType.DAG.value,
            "tasks": list(coerced),
            "dependencies": dependencies or {},
        }
        self._tasks.append(node)
        return self

    def parallel(self, tasks: List[Any]) -> 'Flow':
        """
        Add tasks to execute in parallel.

        Args:
            tasks: List of tasks or Flows to execute concurrently

        Returns:
            Self for method chaining

        Raises:
            RuntimeError: If flow is already registered
            ValueError: If task list is empty or contains None values
        """
        self._validate_registration_state()
        if not tasks:
            raise ValueError("Parallel task list cannot be empty")

        coerced = [self._coerce_task(t) for t in tasks]
        for task in coerced:
            self._validate_task(task)

        node: ExecutionNode = {
            "type": NodeType.PARALLEL.value,
            "tasks": list(coerced)
        }
        self._tasks.append(node)
        return self

    def branch(self, branches: List[Tuple[ConditionFunction, Any]]) -> 'Flow':
        """
        Add conditional branching logic.

        Executes the first task whose condition returns True.
        If no conditions match, data passes through unchanged.

        Args:
            branches: List of (condition_function, task_or_flow) tuples

        Returns:
            Self for method chaining

        Raises:
            RuntimeError: If flow is already registered
            ValueError: If branch list is empty, task is None, or condition is async
        """
        self._validate_registration_state()
        if not branches:
            raise ValueError("Branch list cannot be empty")

        coerced_branches = [(cond, self._coerce_task(task)) for cond, task in branches]
        for condition, task in coerced_branches:
            self._validate_task(task)
            self._validate_condition(condition)

        node: ExecutionNode = {
            "type": NodeType.BRANCH.value,
            "branches": [{"condition": cond, "task": task} for cond, task in coerced_branches]
        }
        self._tasks.append(node)
        return self

    def loop(
        self,
        condition: ConditionFunction,
        task: Any,
        max_iterations: int = 100
    ) -> 'Flow':
        """
        Execute a task repeatedly while a condition is true.

        Args:
            condition: Function that returns True to continue looping
            task: Task to execute on each iteration
            max_iterations: Maximum number of iterations to prevent infinite loops

        Returns:
            Self for method chaining

        Raises:
            RuntimeError: If flow is already registered
            ValueError: If task is None or condition is async
        """
        self._validate_registration_state()
        task = self._coerce_task(task)
        self._validate_task(task)
        self._validate_loop_condition(condition)

        node: ExecutionNode = {
            "type": NodeType.LOOP.value,
            "condition": condition,
            "task": task,
            "max_iterations": max_iterations
        }
        self._tasks.append(node)
        return self

    def as_task(
        self,
        input_schema: Optional[Type[BaseModel]] = None,
        output_schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        """
        Convert this flow into a Task that can be used inside another flow.

        Args:
            input_schema: Pydantic model for input (defaults to a generic dict model)
            output_schema: Pydantic model for output (defaults to a generic dict model)

        Returns:
            A Task instance that executes this sub-flow
        """
        from water.task import Task

        if not self._registered:
            raise RuntimeError("Sub-flow must be registered before converting to task")

        # Default generic schemas
        if not input_schema:
            input_schema = type(
                f"{self.id}_Input",
                (BaseModel,),
                {"__annotations__": {"data": Dict[str, Any]}},
            )
        if not output_schema:
            output_schema = type(
                f"{self.id}_Output",
                (BaseModel,),
                {"__annotations__": {"data": Dict[str, Any]}},
            )

        sub_flow = self

        async def execute_sub_flow(params, context):
            input_data = params["input_data"]
            return await sub_flow.run(input_data)

        return Task(
            id=f"subflow_{self.id}",
            description=f"Sub-flow: {self.description}",
            input_schema=input_schema,
            output_schema=output_schema,
            execute=execute_sub_flow,
        )

    def register(self) -> 'Flow':
        """
        Register the flow for execution.

        Must be called before running the flow.
        Once registered, no more tasks can be added.

        Returns:
            Self for method chaining

        Raises:
            ValueError: If flow has no tasks
        """
        if not self._tasks:
            raise ValueError("Flow must have at least one task")
        self._registered = True
        return self

    async def run(self, input_data: InputData) -> OutputData:
        """
        Execute the flow with the provided input data.

        Args:
            input_data: Input data dictionary to process

        Returns:
            The final output data after all tasks complete

        Raises:
            RuntimeError: If flow is not registered
            FlowPausedError: If the flow was paused during execution
            FlowStoppedError: If the flow was stopped during execution
        """
        if not self._registered:
            raise RuntimeError("Flow must be registered before running")

        if self.version:
            self.metadata["_flow_version"] = self.version

        await self.hooks.emit("on_flow_start", flow_id=self.id, input_data=input_data)

        if self.events:
            from water.events import FlowEvent
            await self.events.emit(FlowEvent("flow_start", self.id, data={"input": input_data}))

        try:
            result = await ExecutionEngine.run(
                self._tasks,
                input_data,
                flow_id=self.id,
                flow_metadata=self.metadata,
                storage=self.storage,
                hooks=self.hooks,
                event_emitter=self.events,
                telemetry=self.telemetry,
            )
            await self.hooks.emit("on_flow_complete", flow_id=self.id, output_data=result)
            if self.events:
                await self.events.emit(FlowEvent("flow_complete", self.id, data={"output": result}))
                await self.events.close()
            return result
        except (FlowPausedError, FlowStoppedError):
            raise
        except Exception as e:
            await self.hooks.emit("on_flow_error", flow_id=self.id, error=e)
            if self.events:
                await self.events.emit(FlowEvent("flow_error", self.id, data={"error": str(e)}))
                await self.events.close()
            raise

    async def pause(self, execution_id: str) -> None:
        """
        Request a running flow to pause at the next node boundary.

        The flow will save its state and can be resumed later with resume().

        Args:
            execution_id: The execution ID of the running flow

        Raises:
            RuntimeError: If no storage backend is configured
            ValueError: If session not found or not in a pausable state
        """
        if not self.storage:
            raise RuntimeError("Storage backend required for pause/resume")

        from water.storage import FlowStatus
        session = await self.storage.get_session(execution_id)
        if not session:
            raise ValueError(f"No session found for execution: {execution_id}")
        if session.status != FlowStatus.RUNNING:
            raise ValueError(
                f"Cannot pause flow in '{session.status.value}' state "
                f"(must be 'running')"
            )

        session.status = FlowStatus.PAUSED
        await self.storage.save_session(session)

    async def stop(self, execution_id: str) -> None:
        """
        Request a running flow to stop at the next node boundary.

        The flow will save its state. Stopped flows cannot be resumed.

        Args:
            execution_id: The execution ID of the running flow

        Raises:
            RuntimeError: If no storage backend is configured
            ValueError: If session not found or not in a stoppable state
        """
        if not self.storage:
            raise RuntimeError("Storage backend required for stop")

        from water.storage import FlowStatus
        session = await self.storage.get_session(execution_id)
        if not session:
            raise ValueError(f"No session found for execution: {execution_id}")
        if session.status not in (FlowStatus.RUNNING, FlowStatus.PAUSED):
            raise ValueError(
                f"Cannot stop flow in '{session.status.value}' state "
                f"(must be 'running' or 'paused')"
            )

        session.status = FlowStatus.STOPPED
        await self.storage.save_session(session)

    async def resume(self, execution_id: str) -> OutputData:
        """
        Resume a paused flow from where it left off.

        Args:
            execution_id: The execution ID of the paused flow

        Returns:
            The final output data after all remaining tasks complete

        Raises:
            RuntimeError: If no storage backend is configured or flow not registered
            ValueError: If session not found or not in 'paused' state
        """
        if not self.storage:
            raise RuntimeError("Storage backend required for resume")
        if not self._registered:
            raise RuntimeError("Flow must be registered before resuming")

        from water.storage import FlowStatus
        session = await self.storage.get_session(execution_id)
        if not session:
            raise ValueError(f"No session found for execution: {execution_id}")
        if session.status != FlowStatus.PAUSED:
            raise ValueError(
                f"Cannot resume flow in '{session.status.value}' state "
                f"(must be 'paused')"
            )

        # Check for version mismatch between paused session and current flow
        if self.version:
            import logging
            _logger = logging.getLogger(__name__)
            session_version = session.context_state.get("flow_version")
            if session_version and session_version != self.version:
                _logger.warning(
                    f"Flow version mismatch on resume: session was paused with "
                    f"v{session_version} but current flow is v{self.version}. "
                    f"Execution may produce unexpected results."
                )

        resume_from = {
            "execution_id": session.execution_id,
            "node_index": session.current_node_index,
            "data": session.current_data,
            "context_state": session.context_state,
        }

        return await ExecutionEngine.run(
            self._tasks,
            session.input_data,
            flow_id=self.id,
            flow_metadata=self.metadata,
            storage=self.storage,
            resume_from=resume_from,
            hooks=self.hooks,
        )

    async def get_session(self, execution_id: str):
        """
        Get the session for a given execution.

        Args:
            execution_id: The execution ID to look up

        Returns:
            FlowSession if found, None otherwise

        Raises:
            RuntimeError: If no storage backend is configured
        """
        if not self.storage:
            raise RuntimeError("Storage backend required")
        return await self.storage.get_session(execution_id)

    async def get_task_runs(self, execution_id: str):
        """
        Get all task runs for a given execution.

        Args:
            execution_id: The execution ID to look up

        Returns:
            List of TaskRun records

        Raises:
            RuntimeError: If no storage backend is configured
        """
        if not self.storage:
            raise RuntimeError("Storage backend required")
        return await self.storage.get_task_runs(execution_id)
