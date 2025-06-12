import inspect
import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List
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

class ExecutionEngine:
    """
    Core execution engine for Water flows.
    
    Orchestrates the execution of different node types including sequential tasks,
    parallel execution, conditional branching, and loops.
    """
    
    @staticmethod
    async def run(
        execution_graph: ExecutionGraph, 
        input_data: InputData,
        flow_id: str,
        flow_metadata: Dict[str, Any] = None
    ) -> OutputData:
        """
        Execute a complete flow execution graph.
        
        Args:
            execution_graph: List of execution nodes to process
            input_data: Initial input data
            flow_id: Unique identifier for the flow execution
            flow_metadata: Optional metadata for the flow
            
        Returns:
            Final output data after all nodes are executed
        """
        context = ExecutionContext(
            flow_id=flow_id,
            flow_metadata=flow_metadata or {}
        )
        context.initial_input = input_data
        
        data: OutputData = input_data
        
        for node in execution_graph:
            data = await ExecutionEngine._execute_node(node, data, context)
        
        return data
    
    @staticmethod
    async def _execute_node(
        node: ExecutionNode, 
        data: InputData, 
        context: ExecutionContext
    ) -> OutputData:
        """
        Route execution to the appropriate node type handler.
        
        Args:
            node: The execution node to process
            data: Input data for the node
            context: Execution context
            
        Returns:
            Output data from the node execution
            
        Raises:
            ValueError: If node type is unknown or unhandled
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
        }
        
        handler = handlers.get(node_type)
        if not handler:
            raise ValueError(f"Unhandled node type: {node_type}")
            
        return await handler(node, data, context)
    
    @staticmethod
    async def _execute_task(task: Any, data: InputData, context: ExecutionContext) -> OutputData:
        """
        Execute a single task, handling both sync and async functions.
        
        Args:
            task: The task to execute
            data: Input data for the task
            context: Execution context
            
        Returns:
            Output data from the task execution
        """
        params: Dict[str, InputData] = {"input_data": data}
        
        # Update context with current task info
        context.task_id = task.id
        context.step_start_time = datetime.utcnow()
        context.step_number += 1
        
        # Execute the task
        if inspect.iscoroutinefunction(task.execute):
            result = await task.execute(params, context)
        else:
            result = task.execute(params, context)
        
        # Store the task result in context for future tasks to access
        context.add_task_output(task.id, result)
        
        return result
    
    @staticmethod
    async def _execute_sequential(
        node: SequentialNode, 
        data: InputData, 
        context: ExecutionContext
    ) -> OutputData:
        """
        Execute a single task sequentially.
        
        Args:
            node: Sequential execution node
            data: Input data
            context: Execution context
            
        Returns:
            Task execution result
        """
        task = node["task"]
        return await ExecutionEngine._execute_task(task, data, context)
    
    @staticmethod
    async def _execute_parallel(
        node: ParallelNode,
        data: InputData,
        context: ExecutionContext
    ) -> OutputData:
        """
        Execute multiple tasks in parallel.
        
        Args:
            node: Parallel execution node
            data: Input data (shared by all tasks)
            context: Execution context
            
        Returns:
            Dictionary mapping task IDs to their results
        """
        tasks = node["tasks"]
        
        # Create task execution coroutines
        async def execute_single_task(task):
            return await ExecutionEngine._execute_task(task, data, context)
        
        coroutines = [execute_single_task(task) for task in tasks]
        
        # Execute all tasks in parallel
        results: List[OutputData] = await asyncio.gather(*coroutines)
        
        # Organize results by task ID
        parallel_results = {task.id: result for task, result in zip(tasks, results)}
        
        # Store individual parallel results in context (they were already stored by _execute_task)
        # but also store the combined parallel results as a special entry
        context.add_task_output("_parallel_results", parallel_results)
        
        return parallel_results
    
    @staticmethod
    async def _execute_branch(
        node: BranchNode, 
        data: InputData, 
        context: ExecutionContext
    ) -> OutputData:
        """
        Execute conditional branching - run the first task whose condition matches.
        
        Args:
            node: Branch execution node
            data: Input data
            context: Execution context
            
        Returns:
            Result from the executed branch, or input data if no conditions match
        """
        branches = node["branches"]
        
        for branch in branches:
            condition = branch["condition"]
            
            if condition(data):
                task = branch["task"]
                return await ExecutionEngine._execute_task(task, data, context)
        
        # If no condition matched, return data unchanged
        return data
    
    @staticmethod
    async def _execute_loop(
        node: LoopNode, 
        data: InputData, 
        context: ExecutionContext
    ) -> OutputData:
        """
        Execute a task repeatedly while condition is true.
        
        Args:
            node: Loop execution node
            data: Initial input data
            context: Execution context
            
        Returns:
            Final data after loop completion
        """
        condition = node["condition"]
        task = node["task"]
        max_iterations: int = node.get("max_iterations", 100)
        
        iteration_count: int = 0
        current_data: OutputData = data
        
        while iteration_count < max_iterations:
            if not condition(current_data):
                break
            
            current_data = await ExecutionEngine._execute_task(task, current_data, context)
            iteration_count += 1
        
        if iteration_count >= max_iterations:
            logger.warning(f"Loop reached maximum iterations ({max_iterations}) for flow {context.flow_id}")
            
        return current_data