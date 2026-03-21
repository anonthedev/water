"""
Cookbook: Semantic Tool Search
==============================

Demonstrates TF-IDF based tool selection to narrow down large tool sets
to the most relevant subset for each query, reducing LLM context noise.

Usage:
    python cookbook/agents/tool_search_flow.py
"""

import asyncio
from water.agents.tools import Tool, Toolkit
from water.agents.tool_search import (
    TFIDFScorer,
    SemanticToolSelector,
    create_tool_selector,
)


# ---------------------------------------------------------------------------
# 1. Create a large set of tools (simulating 20+ tools)
# ---------------------------------------------------------------------------

def make_tool(name: str, description: str) -> Tool:
    return Tool(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
        execute=lambda input: f"[{name}] processed: {input}",
    )


ALL_TOOLS = [
    make_tool("web_search", "Search the web for information using Google or Bing"),
    make_tool("calculator", "Perform mathematical calculations and arithmetic"),
    make_tool("weather_api", "Get current weather data for any city or location"),
    make_tool("send_email", "Send an email message to a recipient"),
    make_tool("read_file", "Read contents of a file from disk"),
    make_tool("write_file", "Write content to a file on disk"),
    make_tool("database_query", "Execute SQL queries against a database"),
    make_tool("http_request", "Make HTTP GET/POST requests to APIs"),
    make_tool("json_parser", "Parse and transform JSON data"),
    make_tool("text_summarizer", "Summarize long text into key points"),
    make_tool("code_executor", "Execute Python code in a sandbox"),
    make_tool("image_generator", "Generate images from text descriptions"),
    make_tool("translation", "Translate text between languages"),
    make_tool("sentiment_analysis", "Analyze sentiment of text (positive/negative/neutral)"),
    make_tool("pdf_reader", "Extract text content from PDF documents"),
    make_tool("csv_processor", "Parse, filter, and transform CSV data"),
    make_tool("git_command", "Execute git commands for version control"),
    make_tool("docker_manager", "Manage Docker containers and images"),
    make_tool("slack_messenger", "Send messages to Slack channels"),
    make_tool("calendar_event", "Create and manage calendar events"),
]


async def main():
    print("=" * 60)
    print("Semantic Tool Search Demo")
    print("=" * 60)

    # -- Example 1: Raw TF-IDF scoring ----------------------------------
    print("\n--- Example 1: TF-IDF scoring ---")
    documents = [t.description for t in ALL_TOOLS]
    scorer = TFIDFScorer(documents)

    query = "search the internet for weather data"
    scores = scorer.score_all(query)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    print(f"  Query: '{query}'")
    print("  Top 5 matches:")
    for idx, score in ranked[:5]:
        print(f"    {score:.4f}  {ALL_TOOLS[idx].name}: {ALL_TOOLS[idx].description[:50]}")

    # -- Example 2: SemanticToolSelector --------------------------------
    print("\n--- Example 2: Tool selection ---")
    selector = SemanticToolSelector(tools=ALL_TOOLS, top_k=3)

    query = "I need to read a PDF and summarize it"
    selected = selector.select(query)
    print(f"  Query: '{query}'")
    print(f"  Selected {len(selected)} tools: {[t.name for t in selected]}")

    query = "send a message on Slack and email"
    selected = selector.select(query)
    print(f"  Query: '{query}'")
    print(f"  Selected {len(selected)} tools: {[t.name for t in selected]}")

    # -- Example 3: always_include tools --------------------------------
    print("\n--- Example 3: Always-include tools ---")
    selector = SemanticToolSelector(
        tools=ALL_TOOLS,
        top_k=3,
        always_include=["web_search", "calculator"],
    )

    query = "deploy docker containers"
    selected = selector.select(query)
    names = [t.name for t in selected]
    print(f"  Query: '{query}'")
    print(f"  Selected: {names}")
    assert "web_search" in names, "web_search should always be included"
    assert "calculator" in names, "calculator should always be included"
    assert "docker_manager" in names, "docker_manager should be top match"

    # -- Example 4: to_toolkit() for LLM calls --------------------------
    print("\n--- Example 4: Dynamic toolkit generation ---")
    selector = create_tool_selector(tools=ALL_TOOLS, top_k=4)

    query = "analyze data from a CSV file and run some calculations"
    toolkit = selector.to_toolkit(query)
    print(f"  Query: '{query}'")
    print(f"  Toolkit '{toolkit.name}' has {len(toolkit)} tools:")
    for t in toolkit:
        print(f"    - {t.name}: {t.description[:60]}")

    schemas = toolkit.to_openai_tools()
    print(f"  OpenAI tool schemas generated: {len(schemas)}")

    # -- Example 5: Different queries select different tools ------------
    print("\n--- Example 5: Query-dependent selection ---")
    selector = create_tool_selector(tools=ALL_TOOLS, top_k=3)

    queries = [
        "write Python code to process files",
        "communicate with the team via messaging",
        "manage source code and deploy",
    ]
    for q in queries:
        selected = selector.select(q)
        print(f"  '{q}'")
        print(f"    -> {[t.name for t in selected]}")

    # -- Example 6: Integration with agentic task -----------------------
    print("\n--- Example 6: Tool selector with agentic task ---")
    from water.agents.react import create_agentic_task

    class MockProvider:
        async def complete(self, **kwargs):
            tools = kwargs.get("tools", [])
            tool_names = [t["function"]["name"] for t in tools]
            # Show that only a subset of tools was sent
            return {
                "content": f"I received {len(tools)} tools: {tool_names}. Task done.",
                "tool_calls": [],
            }

    selector = create_tool_selector(tools=ALL_TOOLS, top_k=3)
    task = create_agentic_task(
        id="smart-agent",
        provider=MockProvider(),
        tools=ALL_TOOLS,
        tool_selector=selector,
        system_prompt="You are a helpful assistant.",
        max_iterations=3,
    )

    result = await task.execute({"input_data": {"prompt": "Help me read and summarize a PDF document"}}, None)
    print(f"  Response: {result['response']}")
    print(f"  (Agent only saw a subset of {len(ALL_TOOLS)} total tools)")

    print("\nAll examples passed!")


if __name__ == "__main__":
    asyncio.run(main())
