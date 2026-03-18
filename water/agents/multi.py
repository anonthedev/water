"""
Multi-Agent Coordination for Water workflows.

Provides tools for multiple agents to share state, hand off work,
and collaborate within a single flow.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timezone
import asyncio
import inspect

from pydantic import BaseModel

from water.core.task import Task, create_task


@dataclass
class AgentRole:
    """Defines a single agent's role within a multi-agent team.

    Attributes:
        name: Unique agent identifier (e.g., "planner", "coder", "reviewer").
        description: Human-readable description of what this agent does.
        task: The Water Task this agent executes.
        can_delegate_to: List of agent names this agent is allowed to hand off to.
    """
    name: str
    description: str
    task: Any  # A Water Task instance
    can_delegate_to: List[str] = field(default_factory=list)


class SharedContext:
    """Shared mutable state accessible by all agents in a team.

    Provides a key-value store, an agent-to-agent message bus,
    and an execution history log.
    """

    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._messages: List[Dict[str, Any]] = []
        self._history: List[Dict[str, Any]] = []

    def set(self, key: str, value: Any) -> None:
        """Store a value in the shared state."""
        self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the shared state."""
        return self._state.get(key, default)

    def add_message(self, from_agent: str, to_agent: str, content: Any) -> None:
        """Send a message from one agent to another."""
        self._messages.append({
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_messages(self, agent_name: str = None) -> List[Dict[str, Any]]:
        """Get messages, optionally filtered by recipient agent name."""
        if agent_name is None:
            return list(self._messages)
        return [m for m in self._messages if m["to"] == agent_name]

    def get_history(self) -> List[Dict[str, Any]]:
        """Return the full execution history."""
        return list(self._history)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the shared context to a plain dictionary."""
        return {
            "state": dict(self._state),
            "messages": list(self._messages),
            "history": list(self._history),
        }


class AgentOrchestrator:
    """Orchestrates the execution of a team of agents.

    Supports three strategies:
      - ``sequential``: Run agents in the order provided.
      - ``round_robin``: Cycle through agents for up to *max_rounds*.
      - ``dynamic``: Let each agent decide who runs next via ``_next_agent``.
    """

    def __init__(self, agents: List[AgentRole], strategy: str = "sequential"):
        if strategy not in ("sequential", "round_robin", "dynamic"):
            raise ValueError(f"Unknown strategy: {strategy}. Must be 'sequential', 'round_robin', or 'dynamic'.")
        self.agents: Dict[str, AgentRole] = {a.name: a for a in agents}
        self.agent_order: List[str] = [a.name for a in agents]
        self.shared_context = SharedContext()
        self.strategy = strategy
        self.max_rounds: int = 10

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_agent(self, agent_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single agent's task, injecting shared context."""
        agent = self.agents[agent_name]
        task = agent.task

        # Build the payload seen by the task's execute function
        enriched_input = dict(input_data)
        enriched_input["_shared_context"] = self.shared_context.to_dict()
        enriched_input["_agent_messages"] = self.shared_context.get_messages(agent_name)

        params = {"input_data": enriched_input}

        # Support both sync and async execute functions
        result = task.execute(params, None)
        if inspect.isawaitable(result):
            result = await result

        # Record in history
        self.shared_context._history.append({
            "agent": agent_name,
            "input": input_data,
            "output": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return result

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    async def _run_sequential(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(input_data)
        for name in self.agent_order:
            data = await self._execute_agent(name, data)
        return data

    async def _run_round_robin(self, input_data: Dict[str, Any], max_rounds: int) -> Dict[str, Any]:
        data = dict(input_data)
        for round_num in range(max_rounds):
            for name in self.agent_order:
                data = await self._execute_agent(name, data)
                if isinstance(data, dict) and data.get("_done"):
                    return data
        return data

    async def _run_dynamic(self, input_data: Dict[str, Any], max_rounds: int) -> Dict[str, Any]:
        data = dict(input_data)
        # Start with the first agent
        current_agent = self.agent_order[0]
        for _ in range(max_rounds):
            data = await self._execute_agent(current_agent, data)
            next_agent = data.get("_next_agent") if isinstance(data, dict) else None
            if not next_agent:
                break
            if next_agent not in self.agents:
                break
            # Validate delegation permission
            agent_role = self.agents[current_agent]
            if agent_role.can_delegate_to and next_agent not in agent_role.can_delegate_to:
                break
            current_agent = next_agent
        return data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, input_data: Dict[str, Any], max_rounds: int = None) -> Dict[str, Any]:
        """Run the agent team according to the configured strategy.

        Args:
            input_data: Initial input dictionary.
            max_rounds: Override for ``self.max_rounds``.

        Returns:
            The final output dictionary produced by the last agent to execute.
        """
        rounds = max_rounds if max_rounds is not None else self.max_rounds

        if self.strategy == "sequential":
            return await self._run_sequential(input_data)
        elif self.strategy == "round_robin":
            return await self._run_round_robin(input_data, rounds)
        elif self.strategy == "dynamic":
            return await self._run_dynamic(input_data, rounds)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def as_task(
        self,
        input_schema: Type[BaseModel] = None,
        output_schema: Type[BaseModel] = None,
    ) -> Task:
        """Convert this orchestrator into a Water Task.

        The returned Task can be used inside any Water Flow just like
        a regular task.
        """
        if input_schema is None:
            input_schema = type(
                "OrchestratorInput",
                (BaseModel,),
                {"__annotations__": {"data": Dict[str, Any]}},
            )
        if output_schema is None:
            output_schema = type(
                "OrchestratorOutput",
                (BaseModel,),
                {"__annotations__": {"data": Dict[str, Any]}},
            )

        orchestrator = self

        async def _execute(params, context):
            input_data = params["input_data"]
            return await orchestrator.run(input_data)

        return Task(
            id="agent_orchestrator",
            description=f"Multi-agent orchestrator ({self.strategy})",
            input_schema=input_schema,
            output_schema=output_schema,
            execute=_execute,
        )


def create_agent_team(
    agents: List[AgentRole],
    strategy: str = "sequential",
    max_rounds: int = 10,
    input_schema: Type[BaseModel] = None,
    output_schema: Type[BaseModel] = None,
) -> Task:
    """Convenience function to create a Task that runs a team of agents.

    Args:
        agents: List of ``AgentRole`` instances.
        strategy: One of ``"sequential"``, ``"round_robin"``, ``"dynamic"``.
        max_rounds: Maximum rounds for round_robin / dynamic strategies.
        input_schema: Optional Pydantic model for the task input.
        output_schema: Optional Pydantic model for the task output.

    Returns:
        A Water ``Task`` that, when executed, runs the agent team.
    """
    orchestrator = AgentOrchestrator(agents, strategy=strategy)
    orchestrator.max_rounds = max_rounds
    return orchestrator.as_task(input_schema=input_schema, output_schema=output_schema)
