"""Sub-agent isolation for the Water framework.

Allows creating Tool instances that delegate work to isolated agentic loops.
Each sub-agent gets its own context window, tools, and configuration, keeping
parent and child state cleanly separated.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from water.agents.context import ContextManager
from water.agents.tools import Tool, Toolkit

logger = logging.getLogger(__name__)

__all__ = ["SubAgentConfig", "create_sub_agent_tool"]


@dataclass
class SubAgentConfig:
    """Configuration for a sub-agent.

    Args:
        id: Unique identifier for the sub-agent.
        provider: LLM provider instance used by the sub-agent.
        tools: List of Tool objects available to the sub-agent.
        toolkit: Optional Toolkit (merged with tools list).
        system_prompt: System prompt that frames the sub-agent's behaviour.
        max_iterations: Safety cap on ReAct loop iterations.
        temperature: LLM sampling temperature.
        max_tokens: Max tokens per LLM response.
        context_config: Optional dict with keys ``max_tokens``,
            ``strategy``, and ``reserve_tokens`` forwarded to a fresh
            ContextManager for the sub-agent.
    """

    id: str
    provider: Any
    tools: List[Tool] = field(default_factory=list)
    toolkit: Optional[Toolkit] = None
    system_prompt: str = ""
    max_iterations: int = 10
    temperature: float = 0.7
    max_tokens: int = 1024
    context_config: Optional[Dict[str, Any]] = None


def create_sub_agent_tool(config: SubAgentConfig) -> Tool:
    """Create a Tool that runs an isolated sub-agent when invoked.

    The returned Tool accepts a single ``task`` string argument describing
    what the sub-agent should accomplish.  Internally it spins up its own
    ReAct loop (via ``create_agentic_task``) with a dedicated
    ``ContextManager``, ensuring full isolation from the parent agent's
    conversation state.

    Args:
        config: A ``SubAgentConfig`` describing the sub-agent.

    Returns:
        A ``Tool`` whose ``run()`` method executes the sub-agent and returns
        a summary dict with ``response``, ``iterations``, and
        ``tool_names_used``.
    """

    async def _execute(task: str) -> Dict[str, Any]:
        from water.agents.react import create_agentic_task

        # Build an isolated ContextManager for the sub-agent.
        ctx_kwargs: Dict[str, Any] = {}
        if config.context_config:
            ctx_kwargs.update(config.context_config)
        context_manager = ContextManager(**ctx_kwargs)

        # Merge toolkit and explicit tools list.
        all_tools: List[Tool] = list(config.tools)
        if config.toolkit:
            all_tools = list(config.toolkit) + all_tools

        sub_task = create_agentic_task(
            id=config.id,
            provider=config.provider,
            tools=all_tools,
            system_prompt=config.system_prompt,
            max_iterations=config.max_iterations,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        logger.debug("Sub-agent '%s' starting with task: %s", config.id, task)

        result = await sub_task.execute({"input_data": {"prompt": task}}, None)

        # Extract tool names used across iterations.
        tool_names_used: List[str] = []
        for entry in result.get("tool_history", []):
            name = entry.get("tool", "")
            if name and name not in tool_names_used:
                tool_names_used.append(name)

        summary = {
            "response": result.get("response", ""),
            "iterations": result.get("iterations", 0),
            "tool_names_used": tool_names_used,
        }

        logger.debug(
            "Sub-agent '%s' finished in %d iterations",
            config.id,
            summary["iterations"],
        )
        return summary

    return Tool(
        name=config.id,
        description=f"Delegate a task to the '{config.id}' sub-agent. "
        f"Provide a 'task' string describing what needs to be done.",
        input_schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "A natural-language description of the task for the sub-agent.",
                },
            },
            "required": ["task"],
        },
        execute=_execute,
    )
