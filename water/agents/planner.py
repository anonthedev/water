# water/agents/planner.py
"""
Dynamic Task Injection (LLM-Driven Flow Planning) for Water.

Provides a PlannerAgent that uses an LLM to generate and execute
multi-step task plans at runtime, enabling dynamic flow construction
based on natural-language goals.
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable

from pydantic import BaseModel

from water.core.task import Task
from water.agents.llm import LLMProvider


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PlanStep:
    """A single step within an execution plan."""
    task_name: str
    input_mapping: Dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class ExecutionPlan:
    """An ordered sequence of PlanSteps produced by the planner."""
    steps: List[PlanStep]
    goal: str = ""
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Task registry
# ---------------------------------------------------------------------------

class TaskRegistry:
    """Registry of available tasks that the planner can use."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, task: Task, description: str = "") -> None:
        """Register a task under *name* with an optional human description."""
        self._tasks[name] = task
        self._descriptions[name] = description or task.description

    def get(self, name: str) -> Optional[Task]:
        """Return the task registered under *name*, or ``None``."""
        return self._tasks.get(name)

    def list_tasks(self) -> List[Dict[str, str]]:
        """Return a list of ``{"name": ..., "description": ...}`` dicts."""
        return [
            {"name": n, "description": self._descriptions[n]}
            for n in self._tasks
        ]

    def get_task_descriptions(self) -> str:
        """Format task descriptions as a bullet list for LLM context."""
        lines = []
        for name, desc in self._descriptions.items():
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Planner agent
# ---------------------------------------------------------------------------

class PlannerAgent:
    """An agent that plans and executes a sequence of tasks to achieve a goal."""

    def __init__(
        self,
        provider: LLMProvider,
        task_registry: TaskRegistry,
        max_steps: int = 10,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.registry = task_registry
        self.max_steps = max_steps
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.execution_history: List[Dict[str, Any]] = []

    # -- helpers ------------------------------------------------------------

    def _default_system_prompt(self) -> str:
        return (
            "You are a task planner. Given a goal and available tasks, "
            "output a JSON plan with steps to achieve the goal.\n"
            "Available tasks:\n{tasks}\n\n"
            'Respond with JSON: {{"steps": [{{"task": "task_name", "input": {{...}}}}], "reasoning": "..."}}'
        )

    def _parse_plan(self, response: str) -> ExecutionPlan:
        """Parse an LLM response string into an :class:`ExecutionPlan`."""
        try:
            text = response.strip()
            # Strip markdown code fences if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            data = json.loads(text)
            steps = [
                PlanStep(
                    task_name=s.get("task", ""),
                    input_mapping=s.get("input", {}),
                )
                for s in data.get("steps", [])
            ]
            return ExecutionPlan(
                steps=steps,
                reasoning=data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, IndexError):
            return ExecutionPlan(
                steps=[],
                reasoning=f"Failed to parse: {response[:200]}",
            )

    # -- public API ---------------------------------------------------------

    async def plan(self, goal: str) -> ExecutionPlan:
        """Generate an execution plan for the given *goal*."""
        prompt = self.system_prompt.replace(
            "{tasks}", self.registry.get_task_descriptions()
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Goal: {goal}"},
        ]
        response = await self.provider.complete(messages)
        plan = self._parse_plan(response.get("text", ""))
        plan.goal = goal
        return plan

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a plan step by step, threading data between steps."""
        data: Dict[str, Any] = dict(initial_data) if initial_data else {}
        self.execution_history = []

        for i, step in enumerate(plan.steps[: self.max_steps]):
            task = self.registry.get(step.task_name)
            if task is None:
                self.execution_history.append(
                    {
                        "step": i,
                        "task": step.task_name,
                        "status": "skipped",
                        "reason": "task not found",
                    }
                )
                continue

            # Merge accumulated data with step-specific input mappings
            step_input = {**data, **step.input_mapping}
            try:
                result = await task.execute(step_input, None)
                if isinstance(result, dict):
                    data = {**data, **result}
                else:
                    data = {**data, "result": result}
                self.execution_history.append(
                    {
                        "step": i,
                        "task": step.task_name,
                        "status": "completed",
                        "result": result,
                    }
                )
            except Exception as e:
                self.execution_history.append(
                    {
                        "step": i,
                        "task": step.task_name,
                        "status": "failed",
                        "error": str(e),
                    }
                )
                break

        return data

    async def plan_and_execute(
        self,
        goal: str,
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Plan and execute in one call."""
        plan = await self.plan(goal)
        return await self.execute_plan(plan, initial_data)


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def create_planner_task(
    id: Optional[str] = None,
    description: Optional[str] = None,
    provider: LLMProvider = None,
    task_registry: TaskRegistry = None,
    max_steps: int = 10,
    goal_key: str = "goal",
) -> Task:
    """Create a :class:`Task` that plans and executes dynamically.

    The returned task accepts an input dict containing a *goal_key* string
    and produces ``{"result": ..., "plan": ..., "history": ...}``.
    """
    task_id = id or f"planner_{uuid.uuid4().hex[:8]}"

    InputSchema = type(
        f"{task_id}_Input",
        (BaseModel,),
        {"__annotations__": {goal_key: str}},
    )
    OutputSchema = type(
        f"{task_id}_Output",
        (BaseModel,),
        {"__annotations__": {"result": dict, "plan": dict, "history": list}},
    )

    planner = PlannerAgent(
        provider=provider,
        task_registry=task_registry,
        max_steps=max_steps,
    )

    async def execute(params, context):
        goal = params.get(goal_key, "")
        plan = await planner.plan(goal)
        result = await planner.execute_plan(plan, params)
        return {
            "result": result,
            "plan": {
                "steps": [
                    {"task": s.task_name, "input": s.input_mapping}
                    for s in plan.steps
                ],
                "reasoning": plan.reasoning,
            },
            "history": planner.execution_history,
        }

    return Task(
        id=task_id,
        description=description or f"Planner: {task_id}",
        input_schema=InputSchema,
        output_schema=OutputSchema,
        execute=execute,
    )
