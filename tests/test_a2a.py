"""Tests for A2A (Agent-to-Agent) protocol support."""

import pytest
from pydantic import BaseModel

from water.core.task import create_task
from water.core.flow import Flow
from water.integrations.a2a import (
    A2AServer,
    A2AClient,
    A2ATask,
    A2AMessage,
    AgentCard,
    AgentSkill,
    MessagePart,
    TaskState,
    create_a2a_task,
)


# --- Helpers ---

class EchoInput(BaseModel):
    prompt: str = ""

class EchoOutput(BaseModel):
    response: str = ""

def _make_echo_flow():
    """Create a simple echo flow for testing."""
    async def echo(params, ctx):
        data = params.get("input_data", params)
        return {"response": data.get("prompt", "no prompt")}

    task = create_task(
        id="echo",
        input_schema=EchoInput,
        output_schema=EchoOutput,
        execute=echo,
    )
    flow = Flow(id="echo_flow", description="Echo")
    flow.then(task).register()
    return flow


# --- AgentCard Tests ---

def test_agent_card_to_dict():
    skill = AgentSkill(id="s1", name="echo", description="Echoes input")
    card = AgentCard(
        name="Test Agent",
        description="A test agent",
        url="http://localhost:8000",
        skills=[skill],
    )
    d = card.to_dict()
    assert d["name"] == "Test Agent"
    assert len(d["skills"]) == 1
    assert d["skills"][0]["id"] == "s1"
    assert "none" in d["authentication"]["schemes"]


# --- MessagePart Tests ---

def test_message_part_text():
    part = MessagePart.text("hello")
    assert part.kind == "text"
    assert part.content == "hello"
    d = part.to_dict()
    assert d["kind"] == "text"

def test_message_part_data():
    part = MessagePart.data({"key": "value"})
    assert part.kind == "data"
    d = part.to_dict()
    assert d["mimeType"] == "application/json"


# --- A2AMessage Tests ---

def test_a2a_message_round_trip():
    msg = A2AMessage(role="user", parts=[MessagePart.text("hi")])
    d = msg.to_dict()
    restored = A2AMessage.from_dict(d)
    assert restored.role == "user"
    assert len(restored.parts) == 1
    assert restored.parts[0].content == "hi"


# --- A2AServer Tests ---

@pytest.mark.asyncio
async def test_server_agent_info():
    flow = _make_echo_flow()
    server = A2AServer(flow=flow, name="Echo Agent", description="Echoes")
    result = await server.handle_request({"method": "agent/info", "id": "1"})
    assert result["result"]["name"] == "Echo Agent"


@pytest.mark.asyncio
async def test_server_tasks_send():
    flow = _make_echo_flow()
    server = A2AServer(flow=flow, name="Echo Agent")

    request = {
        "jsonrpc": "2.0",
        "id": "req1",
        "method": "tasks/send",
        "params": {
            "id": "task1",
            "messages": [
                {"role": "user", "parts": [{"kind": "text", "content": "hello world"}]}
            ],
        },
    }
    result = await server.handle_request(request)
    assert "result" in result
    assert result["result"]["state"] == "completed"
    assert result["result"]["result"]["response"] == "hello world"


@pytest.mark.asyncio
async def test_server_tasks_get():
    flow = _make_echo_flow()
    server = A2AServer(flow=flow, name="Echo Agent")

    # Send first
    await server.handle_request({
        "method": "tasks/send",
        "id": "1",
        "params": {"id": "t1", "messages": [{"role": "user", "parts": [{"kind": "text", "content": "hi"}]}]},
    })

    # Get task
    result = await server.handle_request({
        "method": "tasks/get",
        "id": "2",
        "params": {"id": "t1"},
    })
    assert result["result"]["state"] == "completed"


@pytest.mark.asyncio
async def test_server_tasks_cancel():
    flow = _make_echo_flow()
    server = A2AServer(flow=flow, name="Echo Agent")

    await server.handle_request({
        "method": "tasks/send",
        "id": "1",
        "params": {"id": "t1", "messages": [{"role": "user", "parts": [{"kind": "text", "content": "hi"}]}]},
    })

    result = await server.handle_request({
        "method": "tasks/cancel",
        "id": "2",
        "params": {"id": "t1"},
    })
    assert result["result"]["state"] == "canceled"


@pytest.mark.asyncio
async def test_server_unknown_method():
    flow = _make_echo_flow()
    server = A2AServer(flow=flow, name="Echo Agent")
    result = await server.handle_request({"method": "bad/method", "id": "1"})
    assert "error" in result
    assert result["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_server_data_message():
    flow = _make_echo_flow()
    server = A2AServer(flow=flow, name="Echo Agent")

    request = {
        "jsonrpc": "2.0",
        "id": "req1",
        "method": "tasks/send",
        "params": {
            "id": "task2",
            "messages": [
                {
                    "role": "user",
                    "parts": [
                        {"kind": "data", "content": {"prompt": "data hello"}, "mimeType": "application/json"}
                    ],
                }
            ],
        },
    }
    result = await server.handle_request(request)
    assert result["result"]["state"] == "completed"
    assert result["result"]["result"]["response"] == "data hello"


def test_get_agent_card():
    flow = _make_echo_flow()
    skill = AgentSkill(id="echo", name="Echo", description="Echoes input")
    server = A2AServer(
        flow=flow, name="Echo Agent", skills=[skill], url="http://example.com"
    )
    card = server.get_agent_card()
    assert card["name"] == "Echo Agent"
    assert card["url"] == "http://example.com"
    assert len(card["skills"]) == 1
