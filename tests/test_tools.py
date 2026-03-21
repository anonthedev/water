"""Tests for tool use and function calling abstraction."""

import pytest
from pydantic import BaseModel

from water.agents.tools import Tool, Toolkit, ToolResult, ToolExecutor
from water.agents.llm import MockProvider


# --- Tool tests ---

class CalcInput(BaseModel):
    a: float
    b: float

def test_tool_creation():
    tool = Tool(name="calc", description="Calculator", input_schema=CalcInput, execute=lambda a, b: a + b)
    assert tool.name == "calc"

@pytest.mark.asyncio
async def test_tool_run_sync():
    tool = Tool(name="add", description="Add", execute=lambda a, b: a + b)
    result = await tool.run({"a": 2, "b": 3})
    assert result.success
    assert result.output == 5

@pytest.mark.asyncio
async def test_tool_run_async():
    async def async_add(a, b):
        return a + b
    tool = Tool(name="add", description="Add", execute=async_add)
    result = await tool.run({"a": 2, "b": 3})
    assert result.success
    assert result.output == 5

@pytest.mark.asyncio
async def test_tool_run_error():
    def bad_fn(**kwargs):
        raise ValueError("boom")
    tool = Tool(name="bad", description="Bad", execute=bad_fn)
    result = await tool.run({})
    assert not result.success
    assert "boom" in result.error

@pytest.mark.asyncio
async def test_tool_run_no_execute():
    tool = Tool(name="empty", description="No fn")
    result = await tool.run({})
    assert not result.success

def test_tool_openai_schema():
    tool = Tool(name="search", description="Search the web", input_schema=CalcInput)
    schema = tool.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search"
    assert "properties" in schema["function"]["parameters"]

def test_tool_anthropic_schema():
    tool = Tool(name="search", description="Search the web", input_schema=CalcInput)
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "search"
    assert "input_schema" in schema

def test_tool_dict_schema():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    tool = Tool(name="search", description="Search", input_schema=schema)
    assert tool._schema_to_json_schema() == schema

def test_tool_no_schema():
    tool = Tool(name="test", description="Test")
    schema = tool._schema_to_json_schema()
    assert schema["type"] == "object"


# --- Toolkit tests ---

def test_toolkit_creation():
    t1 = Tool(name="a", description="A")
    t2 = Tool(name="b", description="B")
    tk = Toolkit(name="test", tools=[t1, t2])
    assert len(tk) == 2

def test_toolkit_get():
    t1 = Tool(name="a", description="A")
    tk = Toolkit(name="test", tools=[t1])
    assert tk.get("a") is t1
    assert tk.get("x") is None

def test_toolkit_add():
    tk = Toolkit(name="test")
    tk.add(Tool(name="x", description="X"))
    assert len(tk) == 1

def test_toolkit_openai_tools():
    tk = Toolkit(name="test", tools=[Tool(name="a", description="A")])
    schemas = tk.to_openai_tools()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "a"

def test_toolkit_anthropic_tools():
    tk = Toolkit(name="test", tools=[Tool(name="a", description="A")])
    schemas = tk.to_anthropic_tools()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "a"

def test_toolkit_iter():
    t1 = Tool(name="a", description="A")
    tk = Toolkit(name="test", tools=[t1])
    tools = list(tk)
    assert len(tools) == 1


# --- ToolResult tests ---

def test_tool_result_to_dict():
    r = ToolResult(tool_name="test", output=42, success=True)
    d = r.to_dict()
    assert d["tool_name"] == "test"
    assert d["output"] == 42
    assert "error" not in d

def test_tool_result_with_error():
    r = ToolResult(tool_name="test", output=None, error="fail", success=False)
    d = r.to_dict()
    assert d["error"] == "fail"


# --- ToolExecutor tests ---

@pytest.mark.asyncio
async def test_tool_executor_no_tool_calls():
    """When provider returns no tool calls, executor returns immediately."""
    provider = MockProvider(default_response="just text")
    tk = Toolkit(name="test", tools=[Tool(name="a", description="A")])
    executor = ToolExecutor(provider=provider, tools=tk)
    result = await executor.run([{"role": "user", "content": "hello"}])
    assert result["text"] == "just text"
    assert result["tool_calls"] == []
    assert result["rounds"] == 1
