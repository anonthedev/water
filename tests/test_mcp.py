"""Tests for MCP (Model Context Protocol) server and client integration."""

import pytest
import json
from pydantic import BaseModel

from water import create_task, Flow
from water.mcp import MCPServer, MCPClient, create_mcp_task


# --- Test Schemas ---

class AddInput(BaseModel):
    a: int
    b: int

class AddOutput(BaseModel):
    result: int

class GreetInput(BaseModel):
    name: str

class GreetOutput(BaseModel):
    message: str


# --- Helpers ---

def _make_add_flow() -> Flow:
    """Create a simple registered flow that adds two numbers."""
    add_task = create_task(
        id="add",
        description="Add two numbers",
        input_schema=AddInput,
        output_schema=AddOutput,
        execute=lambda params, ctx: {"result": params["input_data"]["a"] + params["input_data"]["b"]},
    )
    flow = Flow(id="add_numbers", description="Adds a and b together")
    flow.then(add_task).register()
    return flow


def _make_greet_flow() -> Flow:
    """Create a simple registered flow that greets a user."""
    greet_task = create_task(
        id="greet",
        description="Greet someone",
        input_schema=GreetInput,
        output_schema=GreetOutput,
        execute=lambda params, ctx: {"message": f"Hello, {params['input_data']['name']}!"},
    )
    flow = Flow(id="greet_user", description="Greets a user by name")
    flow.then(greet_task).register()
    return flow


# --- MCPServer Tests ---

class TestMCPServerToolDefinitions:
    def test_mcp_server_tool_definitions(self):
        """Server lists flows as tools with correct schemas."""
        add_flow = _make_add_flow()
        greet_flow = _make_greet_flow()
        server = MCPServer(flows=[add_flow, greet_flow])

        tools = server.get_tool_definitions()

        assert len(tools) == 2

        add_tool = next(t for t in tools if t["name"] == "add_numbers")
        assert add_tool["description"] == "Adds a and b together"
        assert "properties" in add_tool["inputSchema"]
        assert "a" in add_tool["inputSchema"]["properties"]
        assert "b" in add_tool["inputSchema"]["properties"]

        greet_tool = next(t for t in tools if t["name"] == "greet_user")
        assert greet_tool["description"] == "Greets a user by name"
        assert "name" in greet_tool["inputSchema"]["properties"]


class TestMCPServerHandleInitialize:
    def test_mcp_server_handle_initialize(self):
        """Server responds to initialize request with server info."""
        server = MCPServer(flows=[], name="test-server", version="2.0.0")
        response = server.handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        result = response["result"]
        assert result["serverInfo"]["name"] == "test-server"
        assert result["serverInfo"]["version"] == "2.0.0"
        assert "protocolVersion" in result
        assert "capabilities" in result


class TestMCPServerHandlePing:
    def test_mcp_server_handle_ping(self):
        """Server responds to ping with an empty result."""
        server = MCPServer(flows=[])
        response = server.handle_request({
            "jsonrpc": "2.0",
            "id": 42,
            "method": "ping",
            "params": {},
        })

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 42
        assert response["result"] == {}


class TestMCPServerHandleToolsList:
    def test_mcp_server_handle_tools_list(self):
        """Server returns tool list via tools/list method."""
        add_flow = _make_add_flow()
        server = MCPServer(flows=[add_flow])

        response = server.handle_request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        tools = response["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "add_numbers"


class TestMCPServerHandleToolsCall:
    @pytest.mark.asyncio
    async def test_mcp_server_handle_tools_call(self):
        """Server executes a flow and returns result via tools/call."""
        add_flow = _make_add_flow()
        server = MCPServer(flows=[add_flow])

        response = await server.handle_request_async({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "add_numbers",
                "arguments": {"a": 5, "b": 3},
            },
        })

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 3
        content = response["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        result_data = json.loads(content[0]["text"])
        assert result_data["result"] == 8


class TestMCPServerUnknownTool:
    @pytest.mark.asyncio
    async def test_mcp_server_unknown_tool(self):
        """Server returns error for unknown tool."""
        server = MCPServer(flows=[])

        response = await server.handle_request_async({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "nonexistent_tool",
                "arguments": {},
            },
        })

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 4
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "nonexistent_tool" in response["error"]["message"]


# --- MCPClient Tests ---

class TestMCPClientAsTask:
    @pytest.mark.asyncio
    async def test_mcp_client_as_task(self):
        """Client tool converts to a runnable Water task."""
        client = MCPClient()
        client.register_mock_tool(
            name="multiply",
            handler=lambda args: {"product": args["x"] * args["y"]},
            description="Multiply two numbers",
        )

        task = client.as_task(
            tool_name="multiply",
            input_schema=AddInput,
            output_schema=AddOutput,
        )

        assert task.id == "mcp_multiply"
        assert task.description == "MCP tool: multiply"

        # Execute the task directly
        result = await task.execute(
            {"input_data": {"x": 4, "y": 7}},
            None,  # context
        )
        assert result["product"] == 28


class TestMCPClientCallTool:
    @pytest.mark.asyncio
    async def test_mcp_client_call_tool(self):
        """Client calls tool and returns result."""
        client = MCPClient()
        client.register_mock_tool(
            name="echo",
            handler=lambda args: {"echoed": args},
            description="Echo input",
        )

        result = await client.call_tool("echo", {"msg": "hello"})
        assert result == {"echoed": {"msg": "hello"}}

    @pytest.mark.asyncio
    async def test_mcp_client_call_unknown_tool(self):
        """Client raises error for unknown tool with no server."""
        client = MCPClient()
        with pytest.raises(RuntimeError, match="No handler available"):
            await client.call_tool("missing", {})

    @pytest.mark.asyncio
    async def test_mcp_client_list_tools(self):
        """Client lists mock tools."""
        client = MCPClient()
        client.register_mock_tool(
            name="tool_a",
            handler=lambda args: {},
            description="Tool A",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        client.register_mock_tool(
            name="tool_b",
            handler=lambda args: {},
            description="Tool B",
        )

        tools = await client.list_tools()
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "tool_a" in names
        assert "tool_b" in names


# --- create_mcp_task Tests ---

class TestCreateMCPTask:
    @pytest.mark.asyncio
    async def test_create_mcp_task(self):
        """Factory creates a working task backed by an MCP tool."""
        client = MCPClient()
        client.register_mock_tool(
            name="uppercase",
            handler=lambda args: {"text": args["text"].upper()},
            description="Uppercase a string",
        )

        task = create_mcp_task(
            tool_name="uppercase",
            mcp_client=client,
            input_schema=GreetInput,
            output_schema=GreetOutput,
        )

        assert task.id == "mcp_uppercase"

        result = await task.execute(
            {"input_data": {"text": "hello world"}},
            None,
        )
        assert result["text"] == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_create_mcp_task_in_flow(self):
        """MCP task works inside a Water flow."""
        client = MCPClient()
        client.register_mock_tool(
            name="double",
            handler=lambda args: {"result": args["value"] * 2},
            description="Double a number",
        )

        mcp_task = create_mcp_task(
            tool_name="double",
            mcp_client=client,
            input_schema=AddInput,
            output_schema=AddOutput,
        )

        flow = Flow(id="mcp_flow", description="Flow using MCP task")
        flow.then(mcp_task).register()

        result = await flow.run({"value": 21})
        assert result["result"] == 42
