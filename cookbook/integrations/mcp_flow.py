"""
MCP (Model Context Protocol) Flow Example

This example demonstrates how to:
1. Create Water flows and expose them as MCP-compatible tools via MCPServer
2. Use MCPClient to call external tools and integrate them as tasks in a flow
3. Combine local flows with remote MCP tools in a single pipeline

The MCP protocol allows AI models to discover and invoke tools in a
standardized way. Water's MCP integration makes it easy to both
publish and consume tools using this protocol.
"""

import asyncio
import json
from typing import Dict, Any

from pydantic import BaseModel

from water.core import Flow, create_task
from water.integrations.mcp import MCPServer, MCPClient, create_mcp_task


# ---------------------------------------------------------------------------
# Part 1: Define flows and expose them as MCP tools
# ---------------------------------------------------------------------------

# Schemas for a text processing flow
class TextInput(BaseModel):
    text: str

class WordCountOutput(BaseModel):
    text: str
    word_count: int

class AnalysisOutput(BaseModel):
    text: str
    word_count: int
    char_count: int
    uppercase: str


# Task: count words in a string
count_words_task = create_task(
    id="count_words",
    description="Count the number of words in the input text",
    input_schema=TextInput,
    output_schema=WordCountOutput,
    execute=lambda params, ctx: {
        "text": params["input_data"]["text"],
        "word_count": len(params["input_data"]["text"].split()),
    },
)

# Task: perform a fuller analysis
analyze_task = create_task(
    id="analyze_text",
    description="Produce character count and uppercase version",
    input_schema=WordCountOutput,
    output_schema=AnalysisOutput,
    execute=lambda params, ctx: {
        "text": params["input_data"]["text"],
        "word_count": params["input_data"]["word_count"],
        "char_count": len(params["input_data"]["text"]),
        "uppercase": params["input_data"]["text"].upper(),
    },
)

# Build and register the text analysis flow
text_analysis_flow = Flow(
    id="text_analysis",
    description="Analyze text: count words, characters, and produce uppercase",
)
text_analysis_flow.then(count_words_task).then(analyze_task).register()


# Schemas for a math flow
class MathInput(BaseModel):
    a: float
    b: float

class MathOutput(BaseModel):
    sum: float
    product: float

math_task = create_task(
    id="math_ops",
    description="Compute sum and product of two numbers",
    input_schema=MathInput,
    output_schema=MathOutput,
    execute=lambda params, ctx: {
        "sum": params["input_data"]["a"] + params["input_data"]["b"],
        "product": params["input_data"]["a"] * params["input_data"]["b"],
    },
)

math_flow = Flow(id="math", description="Basic math operations on two numbers")
math_flow.then(math_task).register()


# Create an MCP server that exposes both flows as tools
server = MCPServer(
    flows=[text_analysis_flow, math_flow],
    name="water-demo",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Part 2: Use MCPClient to consume external MCP tools as Water tasks
# ---------------------------------------------------------------------------

# For this example we simulate an external MCP server by registering
# mock tool handlers on the client. In production you would point
# MCPClient at a real server URL or stdio command.
client = MCPClient()

# Simulate an external "translate" tool
client.register_mock_tool(
    name="translate",
    handler=lambda args: {
        "translated": f"[translated to {args.get('target_lang', 'es')}] {args['text']}"
    },
    description="Translate text to another language",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "target_lang": {"type": "string"},
        },
        "required": ["text"],
    },
)


# Schemas for the translation task
class TranslateInput(BaseModel):
    text: str
    target_lang: str = "es"

class TranslateOutput(BaseModel):
    translated: str


# Convert the external MCP tool into a Water task
translate_task = client.as_task(
    tool_name="translate",
    input_schema=TranslateInput,
    output_schema=TranslateOutput,
)

# Build a flow that uses the MCP-backed task
translation_flow = Flow(
    id="translate_pipeline",
    description="Translate text using an external MCP tool",
)
translation_flow.then(translate_task).register()


# ---------------------------------------------------------------------------
# Part 3: Run everything
# ---------------------------------------------------------------------------

async def main():
    # --- Demonstrate the MCP server ---
    print("=== MCP Server: tool definitions ===")
    tools = server.get_tool_definitions()
    for tool in tools:
        print(f"  Tool: {tool['name']} - {tool['description']}")

    print("\n=== MCP Server: handle initialize ===")
    init_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })
    print(f"  Server: {init_resp['result']['serverInfo']['name']} "
          f"v{init_resp['result']['serverInfo']['version']}")

    print("\n=== MCP Server: call text_analysis tool ===")
    call_resp = await server.handle_request_async({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "text_analysis",
            "arguments": {"text": "Water makes workflow orchestration simple and powerful"},
        },
    })
    result_text = call_resp["result"]["content"][0]["text"]
    print(f"  Result: {result_text}")

    print("\n=== MCP Server: call math tool ===")
    math_resp = await server.handle_request_async({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "math",
            "arguments": {"a": 7, "b": 6},
        },
    })
    math_text = math_resp["result"]["content"][0]["text"]
    print(f"  Result: {math_text}")

    # --- Demonstrate the MCP client ---
    print("\n=== MCP Client: list available tools ===")
    available = await client.list_tools()
    for t in available:
        print(f"  Tool: {t['name']} - {t['description']}")

    print("\n=== MCP Client: call translate tool directly ===")
    translate_result = await client.call_tool("translate", {
        "text": "Hello, world!",
        "target_lang": "fr",
    })
    print(f"  Result: {translate_result}")

    print("\n=== MCP Client: run translation flow (MCP task inside Water) ===")
    flow_result = await translation_flow.run({
        "text": "Workflows are great",
        "target_lang": "de",
    })
    print(f"  Result: {flow_result}")

    print("\nAll examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
