"""
Agentic Loop Flow Example: Model-Controlled Iteration (ReAct Pattern)

This example demonstrates Water's agentic loop where the LLM controls
the iteration — deciding when to use tools and when to stop. It shows:
  - Using flow.agentic_loop() for model-controlled loops
  - Using create_agentic_task() as a standalone task
  - The __done__ stop tool for explicit completion signaling
  - Tool use within the loop
  - Chaining agentic loops with regular tasks

NOTE: This example uses MockProvider so it runs without real API keys.
"""

import asyncio
import json
from typing import Any, Dict

from pydantic import BaseModel

from water.core import Flow, create_task
from water.agents import MockProvider, create_agentic_task
from water.agents.tools import Tool, Toolkit


# ---------------------------------------------------------------------------
# Shared tools used across examples
# ---------------------------------------------------------------------------

def search_web(query: str) -> dict:
    """Simulated web search."""
    results = {
        "python async": [
            "Python asyncio docs — official guide to async/await",
            "Real Python — Async IO in Python: A Complete Walkthrough",
        ],
        "water framework": [
            "Water — lightweight Python workflow framework",
            "GitHub: manthanguptaa/water — agent orchestration",
        ],
    }
    matched = results.get(query.lower(), [f"No results for '{query}'"])
    return {"query": query, "results": matched}


def calculate(expression: str) -> dict:
    """Simulated calculator."""
    try:
        result = eval(expression, {"__builtins__": {}})
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


def get_weather(city: str) -> dict:
    """Simulated weather lookup."""
    weather = {
        "san francisco": {"temp_f": 62, "condition": "foggy"},
        "new york": {"temp_f": 75, "condition": "sunny"},
        "london": {"temp_f": 55, "condition": "rainy"},
    }
    return weather.get(city.lower(), {"temp_f": 70, "condition": "unknown"})


search_tool = Tool(name="search", description="Search the web", execute=search_web)
calc_tool = Tool(name="calculator", description="Evaluate a math expression", execute=calculate)
weather_tool = Tool(name="get_weather", description="Get weather for a city", execute=get_weather)


# ---------------------------------------------------------------------------
# Example 1: Basic agentic loop with flow.agentic_loop()
# ---------------------------------------------------------------------------

async def example_basic_agentic_loop():
    """
    The LLM decides to call tools, gets results, and eventually responds
    without tool calls to signal completion.
    """
    print("=== Example 1: Basic Agentic Loop (flow.agentic_loop) ===\n")

    # Mock provider that simulates a ReAct loop:
    #   Round 1: calls search tool
    #   Round 2: responds with final answer (no tool calls)
    call_count = 0

    async def mock_complete(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": "Let me search for that.",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "search",
                        "arguments": {"query": "water framework"},
                    },
                }],
            }
        return {
            "content": "Water is a lightweight Python workflow framework for agent orchestration. "
                       "You can find it on GitHub at manthanguptaa/water.",
        }

    mock = MockProvider(default_response="")
    mock.complete = mock_complete

    flow = Flow(id="research_flow", description="Research agent with tools")
    flow.agentic_loop(
        provider=mock,
        tools=[search_tool],
        system_prompt="You are a helpful research assistant. Use tools to find information.",
        prompt_template="Research this topic: {topic}",
        max_iterations=5,
    ).register()

    result = await flow.run({"topic": "water framework"})

    print(f"Response:   {result['response']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Tools used: {len(result['tool_history'])}")
    for entry in result["tool_history"]:
        print(f"  Round {entry['iteration']}: {entry['tool']}({entry['arguments']}) -> {entry['result']}")
    print()


# ---------------------------------------------------------------------------
# Example 2: Multi-tool reasoning loop
# ---------------------------------------------------------------------------

async def example_multi_tool_reasoning():
    """
    The LLM uses multiple tools across iterations to answer a question
    that requires combining information.
    """
    print("=== Example 2: Multi-Tool Reasoning ===\n")

    call_count = 0

    async def mock_complete(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First: check weather
            return {
                "content": "Let me check the weather first.",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "San Francisco"},
                    },
                }],
            }
        elif call_count == 2:
            # Then: do a calculation
            return {
                "content": "Now let me convert that to Celsius.",
                "tool_calls": [{
                    "id": "call_2",
                    "function": {
                        "name": "calculator",
                        "arguments": {"expression": "(62 - 32) * 5 / 9"},
                    },
                }],
            }
        # Final answer
        return {
            "content": "The weather in San Francisco is 62°F (16.7°C) and foggy.",
        }

    mock = MockProvider(default_response="")
    mock.complete = mock_complete

    flow = Flow(id="weather_flow", description="Weather agent with unit conversion")
    flow.agentic_loop(
        provider=mock,
        tools=[weather_tool, calc_tool],
        system_prompt="You are a weather assistant. Always convert temperatures to both F and C.",
        prompt_template="{question}",
        max_iterations=10,
    ).register()

    result = await flow.run({"question": "What's the weather in San Francisco in Celsius?"})

    print(f"Response:   {result['response']}")
    print(f"Iterations: {result['iterations']}")
    for entry in result["tool_history"]:
        print(f"  Round {entry['iteration']}: {entry['tool']}({entry['arguments']})")
    print()


# ---------------------------------------------------------------------------
# Example 3: Using __done__ stop tool for explicit completion
# ---------------------------------------------------------------------------

async def example_stop_tool():
    """
    With stop_tool=True, a __done__ tool is injected. The LLM calls it
    to explicitly signal completion with a structured final answer.
    """
    print("=== Example 3: Explicit Stop via __done__ Tool ===\n")

    call_count = 0

    async def mock_complete(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": "Searching for information...",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "search",
                        "arguments": {"query": "python async"},
                    },
                }],
            }
        # Use __done__ to explicitly signal completion with metadata
        return {
            "content": "",
            "tool_calls": [{
                "id": "call_2",
                "function": {
                    "name": "__done__",
                    "arguments": {
                        "final_answer": "Python's asyncio module provides async/await syntax for concurrent programming.",
                        "metadata": {"confidence": 0.95, "sources": ["python docs", "real python"]},
                    },
                },
            }],
        }

    mock = MockProvider(default_response="")
    mock.complete = mock_complete

    flow = Flow(id="stop_tool_flow", description="Agent with explicit stop signal")
    flow.agentic_loop(
        provider=mock,
        tools=[search_tool],
        system_prompt="Research the topic. When done, use __done__ to provide your answer.",
        prompt_template="Research: {topic}",
        max_iterations=5,
        stop_tool=True,  # Injects __done__ tool
    ).register()

    result = await flow.run({"topic": "Python async programming"})

    print(f"Response:   {result['response']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Metadata:   {result.get('metadata', {})}")
    print(f"Tools used: {len(result['tool_history'])}")
    print()


# ---------------------------------------------------------------------------
# Example 4: create_agentic_task() as standalone task in a flow
# ---------------------------------------------------------------------------

async def example_standalone_task():
    """
    Use create_agentic_task() to build a reusable agentic task,
    then chain it with regular tasks in a flow.
    """
    print("=== Example 4: create_agentic_task() in a Flow Chain ===\n")

    call_count = 0

    async def mock_complete(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "search",
                        "arguments": {"query": "water framework"},
                    },
                }],
            }
        return {
            "content": "Water is a Python framework for building AI workflows and agent orchestration.",
        }

    mock = MockProvider(default_response="")
    mock.complete = mock_complete

    # Create the agentic task
    research_agent = create_agentic_task(
        id="researcher",
        provider=mock,
        tools=[search_tool],
        system_prompt="You are a research assistant.",
        prompt_template="Research: {topic}",
        max_iterations=5,
    )

    # Create a formatting task to process the agent's output
    class AgentResult(BaseModel):
        response: str = ""
        iterations: int = 0
        tool_history: list = []

    class ReportOutput(BaseModel):
        report: str

    def format_report(params, context):
        data = params["input_data"]
        return {
            "report": f"## Research Report\n\n"
                      f"**Answer:** {data['response']}\n\n"
                      f"**Iterations:** {data['iterations']}\n"
                      f"**Tools used:** {len(data['tool_history'])}",
        }

    formatter = create_task(
        id="formatter",
        description="Format research into a report",
        input_schema=AgentResult,
        output_schema=ReportOutput,
        execute=format_report,
    )

    # Chain: agentic task -> formatter
    flow = Flow(id="research_pipeline", description="Research then format")
    flow.then(research_agent).then(formatter).register()

    result = await flow.run({"topic": "water framework"})

    print(result["report"])
    print()


# ---------------------------------------------------------------------------
# Example 5: Max iterations safety limit
# ---------------------------------------------------------------------------

async def example_max_iterations():
    """
    Demonstrates the safety limit: if the LLM keeps calling tools
    without stopping, the loop exits after max_iterations.
    """
    print("=== Example 5: Max Iterations Safety Limit ===\n")

    async def always_uses_tools(messages, **kwargs):
        """Mock that always returns tool calls (never stops on its own)."""
        return {
            "content": "Let me search for more...",
            "tool_calls": [{
                "id": f"call_{len(messages)}",
                "function": {
                    "name": "search",
                    "arguments": {"query": "more information"},
                },
            }],
        }

    mock = MockProvider(default_response="")
    mock.complete = always_uses_tools

    flow = Flow(id="bounded_flow", description="Agent with safety limit")
    flow.agentic_loop(
        provider=mock,
        tools=[search_tool],
        system_prompt="You are a research assistant.",
        prompt_template="{prompt}",
        max_iterations=3,  # Safety limit
    ).register()

    result = await flow.run({"prompt": "Research everything about AI"})

    print(f"Response:   '{result['response']}'")
    print(f"Iterations: {result['iterations']} (hit max_iterations=3)")
    print(f"Tools used: {len(result['tool_history'])}")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_basic_agentic_loop()
    await example_multi_tool_reasoning()
    await example_stop_tool()
    await example_standalone_task()
    await example_max_iterations()
    print("All agentic loop examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
