import dataclasses
from typing import Any, Callable, Dict, List, Union
from typing_extensions import TypedDict


class SerializableMixin:
    """Mixin that adds to_dict() serialization to dataclasses."""

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if hasattr(value, 'to_dict'):
                result[f.name] = value.to_dict()
            elif isinstance(value, list):
                result[f.name] = [
                    item.to_dict() if hasattr(item, 'to_dict') else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[f.name] = {
                    k: v.to_dict() if hasattr(v, 'to_dict') else v
                    for k, v in value.items()
                }
            else:
                result[f.name] = value
        return result

# Forward declaration for ExecutionContext
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from water.core.context import ExecutionContext
    from water.core.task import Task

# Type aliases
InputData = Dict[str, Any]
OutputData = Dict[str, Any]
ConditionFunction = Callable[[InputData], bool]

# Updated task execution function signature to include context
TaskExecuteFunction = Callable[[Dict[str, InputData], 'ExecutionContext'], OutputData]

# TypedDict definitions for node structures
class SequentialNode(TypedDict):
    type: str
    task: 'Task'

class ParallelNode(TypedDict):
    type: str
    tasks: List['Task']

class BranchCondition(TypedDict):
    condition: ConditionFunction
    task: 'Task'

class BranchNode(TypedDict):
    type: str
    branches: List[BranchCondition]

class LoopNode(TypedDict):
    type: str
    condition: ConditionFunction
    task: 'Task'
    max_iterations: int

# Union type for all node types
ExecutionNode = Union[SequentialNode, ParallelNode, BranchNode, LoopNode]
ExecutionGraph = List[ExecutionNode]
