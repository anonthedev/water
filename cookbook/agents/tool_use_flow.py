"""
Tool Use Flow Example: Function Calling with LLM Agents

This example demonstrates Water's tool use abstraction for LLM function
calling. It shows:
  - Defining Tools with input schemas and execute functions
  - Organizing tools into a Toolkit
  - Using ToolExecutor to run the LLM <-> tool call loop
  - Cross-provider schema generation (OpenAI and Anthropic formats)

NOTE: This example uses MockProvider so it runs without real API keys.
"""

import asyncio
import json
from typing import Any, Dict

from pydantic import BaseModel

from water.agents import MockProvider
from water.agents.tools import Tool, Toolkit, ToolResult, ToolExecutor


# ---------------------------------------------------------------------------
# Example 1: Defining tools and running them directly
# ---------------------------------------------------------------------------

async def example_tool_basics():
    """Create tools and execute them directly."""
    print("=== Example 1: Tool Basics ===\n")

    # Define a calculator tool with a Pydantic schema
    class CalcInput(BaseModel):
        operation: str
        a: float
        b: float

    def calculate(operation: str, a: float, b: float) -> dict:
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else float("inf"),
        }
        result = ops.get(operation, 0)
        return {"result": result, "expression": f"{a} {operation} {b} = {result}"}

    calc_tool = Tool(
        name="calculator",
        description="Perform basic arithmetic operations",
        input_schema=CalcInput,
        execute=calculate,
    )

    # Run the tool directly
    result = await calc_tool.run({"operation": "multiply", "a": 7, "b": 6})
    print(f"Tool:    {result.tool_name}")
    print(f"Output:  {result.output}")
    print(f"Success: {result.success}")
    print()

    # Define an async tool
    async def fetch_weather(city: str) -> dict:
        # Simulated weather lookup
        weather = {
            "new york": {"temp": 72, "condition": "sunny"},
            "london": {"temp": 58, "condition": "cloudy"},
            "tokyo": {"temp": 80, "condition": "humid"},
        }
        data = weather.get(city.lower(), {"temp": 65, "condition": "unknown"})
        return {"city": city, **data}

    weather_tool = Tool(
        name="get_weather",
        description="Get current weather for a city",
        execute=fetch_weather,
    )

    result = await weather_tool.run({"city": "Tokyo"})
    print(f"Weather: {result.output}")

    # Error handling
    bad_tool = Tool(name="broken", description="Always fails", execute=None)
    result = await bad_tool.run({})
    print(f"Bad tool: success={result.success}, error='{result.error}'")
    print()


# ---------------------------------------------------------------------------
# Example 2: Toolkit and schema generation
# ---------------------------------------------------------------------------

async def example_toolkit():
    """Organize tools into a Toolkit and generate provider schemas."""
    print("=== Example 2: Toolkit & Schema Generation ===\n")

    class SearchInput(BaseModel):
        query: str
        max_results: int = 5

    def search(query: str, max_results: int = 5) -> list:
        return [f"Result {i+1} for '{query}'" for i in range(min(max_results, 3))]

    def get_time() -> str:
        return "2026-03-21T10:30:00Z"

    toolkit = Toolkit(name="assistant_tools")
    toolkit.add(Tool(
        name="web_search",
        description="Search the web for information",
        input_schema=SearchInput,
        execute=search,
    ))
    toolkit.add(Tool(
        name="get_current_time",
        description="Get the current date and time",
        execute=get_time,
    ))

    print(f"Toolkit '{toolkit.name}' has {len(toolkit)} tools")
    print(f"Tool names: {[t.name for t in toolkit]}")
    print()

    # Generate OpenAI-compatible schemas
    openai_tools = toolkit.to_openai_tools()
    print("OpenAI format:")
    for t in openai_tools:
        print(f"  {t['function']['name']}: {t['function']['description']}")
    print()

    # Generate Anthropic-compatible schemas
    anthropic_tools = toolkit.to_anthropic_tools()
    print("Anthropic format:")
    for t in anthropic_tools:
        print(f"  {t['name']}: {t['description']}")
    print()

    # Look up and run a tool by name
    search_tool = toolkit.get("web_search")
    if search_tool:
        result = await search_tool.run({"query": "Water framework", "max_results": 2})
        print(f"Search results: {result.output}")
    print()


# ---------------------------------------------------------------------------
# Example 3: ToolExecutor with MockProvider
# ---------------------------------------------------------------------------

async def example_tool_executor():
    """Run the full LLM <-> tool call loop using ToolExecutor."""
    print("=== Example 3: ToolExecutor (LLM <-> Tool Loop) ===\n")

    # Define tools
    def lookup_user(user_id: str) -> dict:
        users = {
            "u001": {"name": "Alice", "email": "alice@example.com", "plan": "pro"},
            "u002": {"name": "Bob", "email": "bob@example.com", "plan": "free"},
        }
        return users.get(user_id, {"error": "User not found"})

    def check_subscription(plan: str) -> dict:
        limits = {"pro": {"api_calls": 10000}, "free": {"api_calls": 100}}
        return limits.get(plan, {"api_calls": 0})

    toolkit = Toolkit(name="user_tools", tools=[
        Tool(name="lookup_user", description="Look up user by ID", execute=lookup_user),
        Tool(name="check_subscription", description="Check plan limits", execute=check_subscription),
    ])

    # MockProvider that first returns a tool call, then a final response
    # First call: provider asks to use the lookup_user tool
    # Second call: provider gives the final text answer
    mock = MockProvider(default_response="Alice is on the Pro plan with 10,000 API calls per month.")

    # Patch the mock to return tool calls on first invocation
    call_count = 0
    original_complete = mock.complete

    async def mock_complete_with_tools(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate LLM requesting a tool call
            return {
                "text": "",
                "tool_calls": [{
                    "id": "call_001",
                    "function": {
                        "name": "lookup_user",
                        "arguments": json.dumps({"user_id": "u001"}),
                    },
                }],
            }
        # After getting tool result, return final answer
        return {"text": "Alice is on the Pro plan with 10,000 API calls per month."}

    mock.complete = mock_complete_with_tools

    executor = ToolExecutor(provider=mock, tools=toolkit, max_rounds=3)

    result = await executor.run(
        messages=[{"role": "user", "content": "What plan is user u001 on?"}],
    )

    print(f"Final response: {result['text']}")
    print(f"Rounds:         {result['rounds']}")
    print(f"Tool calls:     {len(result['tool_calls'])}")
    for tc in result["tool_calls"]:
        print(f"  - {tc['tool']}({tc['arguments']}) -> {tc['result']['output']}")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_tool_basics()
    await example_toolkit()
    await example_tool_executor()
    print("All tool use examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
