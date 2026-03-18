"""
Tests for the Water chat integration module.

All tests use InMemoryAdapter — no real platform SDKs are required.
"""

import pytest
from pydantic import BaseModel

from water.core import Flow
from water.core import create_task
from water.integrations.chat import (
    ChatBot,
    ChatMessage,
    FlowNotification,
    InMemoryAdapter,
)


# --- Schemas ----------------------------------------------------------------

class TextInput(BaseModel):
    text: str
    channel: str = ""
    user: str = ""


class TextOutput(BaseModel):
    result: str


# --- Helpers ----------------------------------------------------------------

def _make_echo_task(task_id: str = "echo"):
    """Create a simple task that echoes the input text."""
    return create_task(
        id=task_id,
        description="Echo input text",
        input_schema=TextInput,
        output_schema=TextOutput,
        execute=lambda params, ctx: {"result": f"echo: {params['input_data']['text']}"},
    )


def _make_echo_flow(flow_id: str = "echo_flow") -> Flow:
    """Build and register a minimal echo flow."""
    task = _make_echo_task()
    flow = Flow(id=flow_id, description="Echoes text back")
    flow.then(task).register()
    return flow


def _make_error_flow(flow_id: str = "error_flow") -> Flow:
    """Build and register a flow that always raises."""

    def _boom(params, ctx):
        raise RuntimeError("something went wrong")

    task = create_task(
        id="boom",
        description="Always fails",
        input_schema=TextInput,
        output_schema=TextOutput,
        execute=_boom,
    )
    flow = Flow(id=flow_id, description="Always fails")
    flow.then(task).register()
    return flow


# --- Tests ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chatbot_register_flow():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)
    flow = _make_echo_flow()

    bot.register_flow("echo", flow, description="Echo command")

    assert "echo" in bot.flows
    assert bot.flows["echo"]["description"] == "Echo command"


@pytest.mark.asyncio
async def test_chatbot_handle_message_triggers_flow():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)
    flow = _make_echo_flow()
    bot.register_flow("echo", flow)

    msg = ChatMessage(text="echo hello", channel="#general", user="alice")
    result = await bot.handle_message(msg)

    assert result is not None
    # The adapter should have sent a response to the channel
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0]["channel"] == "#general"


@pytest.mark.asyncio
async def test_chatbot_custom_handler():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)

    @bot.on_message(r"^ping$")
    async def pong(message: ChatMessage):
        return "pong"

    msg = ChatMessage(text="ping", channel="#test", user="bob")
    result = await bot.handle_message(msg)

    assert result == "pong"
    assert adapter.sent_messages[0]["text"] == "pong"


@pytest.mark.asyncio
async def test_chatbot_help_command():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)
    flow = _make_echo_flow()
    bot.register_flow("echo", flow, description="Echo command")

    msg = ChatMessage(text="help", channel="#general", user="alice")
    result = await bot.handle_message(msg)

    assert "Available commands:" in result
    assert "echo" in result
    assert "Echo command" in result


@pytest.mark.asyncio
async def test_chatbot_unknown_command():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)

    msg = ChatMessage(text="foobar", channel="#general", user="alice")
    result = await bot.handle_message(msg)

    assert "Unknown command" in result
    assert adapter.sent_messages[0]["text"].startswith("Unknown command")


@pytest.mark.asyncio
async def test_chatbot_flow_result_sent():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)
    flow = _make_echo_flow()
    bot.register_flow("echo", flow)

    msg = ChatMessage(text="echo world", channel="#out", user="carol")
    await bot.handle_message(msg)

    assert len(adapter.sent_messages) == 1
    sent_text = adapter.sent_messages[0]["text"]
    # The flow returns a dict with 'result' key — it should appear in the sent text
    assert "echo: world" in sent_text


@pytest.mark.asyncio
async def test_in_memory_adapter_send():
    adapter = InMemoryAdapter()
    await adapter.send_message("#chan", "hello")
    await adapter.send_message("#chan", "world", thread_ts="123")

    assert len(adapter.sent_messages) == 2
    assert adapter.sent_messages[0] == {"channel": "#chan", "text": "hello"}
    assert adapter.sent_messages[1] == {
        "channel": "#chan",
        "text": "world",
        "thread_ts": "123",
    }


@pytest.mark.asyncio
async def test_flow_notification_complete():
    adapter = InMemoryAdapter()
    notifier = FlowNotification(adapter=adapter, channel="#alerts")

    await notifier.notify_complete("my_flow", "exec-1", {"status": "ok"})

    assert len(adapter.sent_messages) == 1
    text = adapter.sent_messages[0]["text"]
    assert "my_flow" in text
    assert "completed" in text
    assert "exec-1" in text


@pytest.mark.asyncio
async def test_flow_notification_error():
    adapter = InMemoryAdapter()
    notifier = FlowNotification(adapter=adapter, channel="#alerts")

    await notifier.notify_error("my_flow", "exec-2", "timeout")

    assert len(adapter.sent_messages) == 1
    text = adapter.sent_messages[0]["text"]
    assert "my_flow" in text
    assert "failed" in text
    assert "timeout" in text


@pytest.mark.asyncio
async def test_chatbot_parse_args():
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)

    # Create a flow that echoes back the parsed key=value args
    task = create_task(
        id="args_task",
        description="Return parsed args",
        input_schema=TextInput,
        output_schema=TextOutput,
        execute=lambda params, ctx: {
            "result": f"name={params['input_data'].get('name', '')}"
        },
    )
    flow = Flow(id="greet", description="Greet by name")
    flow.then(task).register()
    bot.register_flow("greet", flow)

    msg = ChatMessage(text="greet name=Alice", channel="#general", user="dave")
    await bot.handle_message(msg)

    sent_text = adapter.sent_messages[0]["text"]
    assert "name=Alice" in sent_text


@pytest.mark.asyncio
async def test_chatbot_flow_error_sent():
    """When a flow raises, the error is sent back to the channel."""
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)
    flow = _make_error_flow()
    bot.register_flow("boom", flow)

    msg = ChatMessage(text="boom", channel="#general", user="eve")
    result = await bot.handle_message(msg)

    assert "failed" in result
    assert "something went wrong" in result
    assert len(adapter.sent_messages) == 1


@pytest.mark.asyncio
async def test_inject_message_via_adapter():
    """InMemoryAdapter.inject_message routes through ChatBot.handle_message."""
    adapter = InMemoryAdapter()
    bot = ChatBot(adapter=adapter)
    flow = _make_echo_flow()
    bot.register_flow("echo", flow)

    msg = ChatMessage(text="echo injected", channel="#ci", user="bot")
    result = await adapter.inject_message(msg)

    assert result is not None
    assert "echo: injected" in result
