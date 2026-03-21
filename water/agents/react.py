"""ReAct (Reason + Act) agentic loop pattern.

Provides create_agentic_task() for creating tasks where the LLM controls
the iteration loop, deciding when to use tools and when to stop.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from water.agents.tools import Tool, Toolkit

logger = logging.getLogger(__name__)

__all__ = ["create_agentic_task"]


def create_agentic_task(
    id: str = None,
    provider=None,
    tools: Optional[List[Tool]] = None,
    toolkit: Optional[Toolkit] = None,
    system_prompt: str = "",
    prompt_template: str = "",
    max_iterations: int = 10,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    stop_tool: bool = False,
    output_parser: Optional[Callable] = None,
    retry_count: int = 0,
    timeout: Optional[float] = None,
):
    """Create a task that runs a model-controlled agentic loop (ReAct pattern).

    The LLM decides when to continue iterating (by calling tools) and when to
    stop (by responding without tool calls or by calling __done__).

    Args:
        id: Task identifier.
        provider: LLM provider instance.
        tools: List of Tool objects.
        toolkit: Toolkit instance (alternative to tools list).
        system_prompt: System prompt for the agent.
        prompt_template: Template with {variable} placeholders for input data.
        max_iterations: Safety limit on loop iterations.
        temperature: LLM temperature.
        max_tokens: Max tokens per LLM response.
        stop_tool: If True, inject a __done__ tool for explicit stop signaling.
        output_parser: Optional function to parse the final response.
        retry_count: Number of retries on failure.
        timeout: Timeout in seconds.

    Returns:
        A Task instance that can be used with flow.then().
    """
    from water.core.task import Task

    # Build toolkit
    all_tools = tools or []
    if toolkit:
        all_tools = list(toolkit) + all_tools

    if stop_tool:
        done_tool = Tool(
            name="__done__",
            description="Call this tool when you have completed the task and want to provide your final answer.",
            input_schema={
                "type": "object",
                "properties": {
                    "final_answer": {"type": "string", "description": "Your final answer to the user's request"},
                    "metadata": {"type": "object", "description": "Optional metadata about the result", "default": {}},
                },
                "required": ["final_answer"],
            },
            execute=lambda final_answer, metadata=None: {"final_answer": final_answer, "metadata": metadata or {}},
        )
        all_tools.append(done_tool)

    final_toolkit = Toolkit(tools=all_tools) if all_tools else None
    tools_schema = final_toolkit.to_openai_tools() if final_toolkit else None

    async def execute(data):
        if max_iterations <= 0:
            raise ValueError(f"max_iterations must be > 0, got {max_iterations}")

        # Build user message
        if prompt_template:
            try:
                user_message = prompt_template.format(**data) if isinstance(data, dict) else prompt_template.format(input=data)
            except (KeyError, IndexError):
                user_message = str(data)
        else:
            user_message = data.get("prompt", str(data)) if isinstance(data, dict) else str(data)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        tool_history = []
        last_response = None

        for iteration in range(max_iterations):
            # Call LLM
            call_kwargs = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            if tools_schema:
                call_kwargs["tools"] = tools_schema

            response = await provider.complete(**call_kwargs)
            last_response = response

            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                result = {"response": response.get("content", ""), "tool_history": tool_history, "iterations": iteration + 1}
                return output_parser(result) if output_parser else result

            # Process tool calls
            assistant_msg = {"role": "assistant", "content": response.get("content", ""), "tool_calls": tool_calls}
            messages.append(assistant_msg)

            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {})
                tool_call_id = tc.get("id", "")

                if tool_name == "__done__":
                    result = {
                        "response": tool_args.get("final_answer", ""),
                        "tool_history": tool_history,
                        "iterations": iteration + 1,
                        "metadata": tool_args.get("metadata", {}),
                    }
                    return output_parser(result) if output_parser else result

                if final_toolkit:
                    tool = final_toolkit._tools.get(tool_name)
                    if tool:
                        try:
                            if isinstance(tool_args, str):
                                tool_args = json.loads(tool_args)
                            result = tool.execute(**tool_args) if not asyncio.iscoroutinefunction(tool.execute) else await tool.execute(**tool_args)
                            tool_result = {"success": True, "result": result}
                        except Exception as e:
                            tool_result = {"success": False, "error": str(e)}
                    else:
                        tool_result = {"success": False, "error": f"Tool '{tool_name}' not found"}
                else:
                    tool_result = {"success": False, "error": "No tools available"}

                tool_history.append({"iteration": iteration + 1, "tool": tool_name, "arguments": tool_args, "result": tool_result})
                messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": str(tool_result.get("result", tool_result.get("error", "")))})

        logger.warning(f"Agentic loop reached max_iterations ({max_iterations})")
        result = {"response": last_response.get("content", "") if last_response else "", "tool_history": tool_history, "iterations": max_iterations}
        return output_parser(result) if output_parser else result

    task = Task(
        id=id or "agentic_task",
        execute=execute,
        retry_count=retry_count,
        timeout=timeout,
    )
    return task
