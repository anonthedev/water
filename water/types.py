from typing import Any, Callable, Dict, List, Union
from typing_extensions import TypedDict

# Forward declaration for ExecutionContext
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from water.context import ExecutionContext
    from water.task import Task

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