import uuid
from typing import Dict, Any, Optional, Type, Callable, List
from pydantic import BaseModel
from water.core.task import Task


class SubFlow:
    """Wraps a registered Flow as a Task for composition within another Flow."""

    def __init__(
        self,
        flow,  # A Flow instance
        input_mapping: Optional[Dict[str, str]] = None,
        output_mapping: Optional[Dict[str, str]] = None,
        id: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.flow = flow
        self.input_mapping = input_mapping or {}
        self.output_mapping = output_mapping or {}
        self._id = id
        self._description = description

    def as_task(self) -> Task:
        """Convert this SubFlow into a Task."""
        task_id = self._id or f"subflow_{self.flow.id}_{uuid.uuid4().hex[:6]}"

        # Try to infer schemas from flow's first/last task
        input_schema = self._get_input_schema()
        output_schema = self._get_output_schema()

        input_mapping = self.input_mapping
        output_mapping = self.output_mapping
        flow = self.flow

        async def execute(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
            # The engine wraps data as {"input_data": data} before calling execute
            data = params.get("input_data", params)
            if not isinstance(data, dict):
                data = params

            # Apply input mapping
            mapped_input = dict(data)
            for target, source in input_mapping.items():
                if source in data:
                    mapped_input[target] = data[source]

            # Run the sub-flow
            result = await flow.run(mapped_input)

            # Apply output mapping
            if output_mapping and isinstance(result, dict):
                mapped_output = {}
                for target, source in output_mapping.items():
                    if source in result:
                        mapped_output[target] = result[source]
                return mapped_output

            return result if isinstance(result, dict) else {"result": result}

        return Task(
            id=task_id,
            description=self._description or f"SubFlow: {self.flow.id}",
            input_schema=input_schema,
            output_schema=output_schema,
            execute=execute,
        )

    def _get_input_schema(self) -> Type[BaseModel]:
        """Try to get input schema from flow's first task."""
        if self.flow._tasks:
            first_node = self.flow._tasks[0]
            if hasattr(first_node, 'task') and first_node.task and hasattr(first_node.task, 'input_schema'):
                return first_node.task.input_schema
            # ExecutionNode is a TypedDict / dict
            if isinstance(first_node, dict) and 'task' in first_node:
                task = first_node['task']
                if hasattr(task, 'input_schema'):
                    return task.input_schema
        # Generic fallback
        return type("SubFlowInput", (BaseModel,), {"__annotations__": {"data": Dict[str, Any]}})

    def _get_output_schema(self) -> Type[BaseModel]:
        """Try to get output schema from flow's last task."""
        if self.flow._tasks:
            last_node = self.flow._tasks[-1]
            if hasattr(last_node, 'task') and last_node.task and hasattr(last_node.task, 'output_schema'):
                return last_node.task.output_schema
            # ExecutionNode is a TypedDict / dict
            if isinstance(last_node, dict) and 'task' in last_node:
                task = last_node['task']
                if hasattr(task, 'output_schema'):
                    return task.output_schema
        return type("SubFlowOutput", (BaseModel,), {"__annotations__": {"result": Dict[str, Any]}})


def compose_flows(*flows, id: Optional[str] = None, description: Optional[str] = None):
    """Compose multiple flows sequentially into a new flow."""
    from water.core.flow import Flow

    flow_id = id or f"composed_{'_'.join(f.id for f in flows)}"
    composed = Flow(id=flow_id, description=description or f"Composed flow: {flow_id}")

    for sub_flow in flows:
        sub = SubFlow(sub_flow)
        composed = composed.then(sub.as_task())

    return composed
