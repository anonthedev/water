"""
Cookbook: Sub-Agent Isolation
=============================

Demonstrates how to create isolated sub-agents that run their own
Think-Act-Observe-Repeat loops while being callable as tools from a
parent agent.

Usage:
    python cookbook/agents/sub_agent_flow.py
"""

import asyncio
from water.agents.tools import Tool, Toolkit
from water.agents.subagent import SubAgentConfig, create_sub_agent_tool
from water.agents.react import create_agentic_task


# ---------------------------------------------------------------------------
# 1. Mock provider that simulates LLM responses
# ---------------------------------------------------------------------------

class MockSubAgentProvider:
    """Simulates an LLM that calls tools and then responds."""

    def __init__(self, name="mock"):
        self.name = name
        self._call_count = 0

    async def complete(self, **kwargs):
        self._call_count += 1
        messages = kwargs.get("messages", [])
        tools = kwargs.get("tools", [])

        # First call: use a tool if available
        if self._call_count == 1 and tools:
            tool_name = tools[0]["function"]["name"]
            return {
                "content": f"[{self.name}] Let me use {tool_name}.",
                "tool_calls": [
                    {
                        "id": f"call_{self._call_count}",
                        "function": {
                            "name": tool_name,
                            "arguments": {"query": "test"},
                        },
                    }
                ],
            }

        # Second call: return final answer
        return {"content": f"[{self.name}] Task complete after {self._call_count} calls.", "tool_calls": []}


# ---------------------------------------------------------------------------
# 2. Define tools for the sub-agent
# ---------------------------------------------------------------------------

search_tool = Tool(
    name="search",
    description="Search for information on a topic.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    execute=lambda query: f"Results for '{query}': [item1, item2, item3]",
)

summarize_tool = Tool(
    name="summarize",
    description="Summarize a piece of text.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    execute=lambda query: f"Summary: '{query}' condensed into key points.",
)


# ---------------------------------------------------------------------------
# 3. Create a sub-agent tool
# ---------------------------------------------------------------------------

researcher_config = SubAgentConfig(
    id="researcher",
    provider=MockSubAgentProvider(name="researcher"),
    tools=[search_tool, summarize_tool],
    system_prompt="You are a research assistant. Search for information and summarize findings.",
    max_iterations=5,
)

researcher_tool = create_sub_agent_tool(researcher_config)


# ---------------------------------------------------------------------------
# 4. Parent agent uses the sub-agent as a tool
# ---------------------------------------------------------------------------

class ParentProvider:
    """Parent LLM that delegates to the researcher sub-agent."""

    def __init__(self):
        self._call_count = 0

    async def complete(self, **kwargs):
        self._call_count += 1
        tools = kwargs.get("tools", [])

        if self._call_count == 1:
            # Delegate to the researcher sub-agent
            return {
                "content": "I need to research this topic. Let me delegate to my researcher.",
                "tool_calls": [
                    {
                        "id": "call_parent_1",
                        "function": {
                            "name": "researcher",
                            "arguments": {"task": "Find information about water framework features"},
                        },
                    }
                ],
            }

        return {
            "content": "Based on my researcher's findings, here is the summary.",
            "tool_calls": [],
        }


async def main():
    print("=" * 60)
    print("Sub-Agent Isolation Demo")
    print("=" * 60)

    # -- Example 1: Direct sub-agent tool usage -------------------------
    print("\n--- Example 1: Direct sub-agent invocation ---")
    result = await researcher_tool.run({"task": "Research Python async patterns"})
    print(f"  Success: {result.success}")
    print(f"  Output: {result.output}")

    # -- Example 2: Parent agent delegates to sub-agent -----------------
    print("\n--- Example 2: Parent agent with sub-agent tool ---")
    parent_task = create_agentic_task(
        id="parent-agent",
        provider=ParentProvider(),
        tools=[researcher_tool],
        system_prompt="You are a manager agent. Delegate research tasks to your researcher.",
        max_iterations=5,
    )

    result = await parent_task.execute({"input_data": {"prompt": "Write a report about async Python"}}, None)
    print(f"  Response: {result['response']}")
    print(f"  Iterations: {result['iterations']}")
    print(f"  Tools used: {[h['tool'] for h in result['tool_history']]}")

    # -- Example 3: Multiple sub-agents ---------------------------------
    print("\n--- Example 3: Multiple sub-agents ---")
    writer_config = SubAgentConfig(
        id="writer",
        provider=MockSubAgentProvider(name="writer"),
        tools=[summarize_tool],
        system_prompt="You are a technical writer.",
        max_iterations=3,
    )
    writer_tool = create_sub_agent_tool(writer_config)

    # Run both sub-agents concurrently
    research_result, write_result = await asyncio.gather(
        researcher_tool.run({"task": "Research topic A"}),
        writer_tool.run({"task": "Write about topic B"}),
    )

    print(f"  Researcher: {research_result.output}")
    print(f"  Writer: {write_result.output}")

    print("\nAll examples passed!")


if __name__ == "__main__":
    asyncio.run(main())
