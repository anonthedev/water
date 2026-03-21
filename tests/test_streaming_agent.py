"""Tests for Async Streaming LLM Agent Tasks."""

import pytest
import asyncio
from typing import Dict, Any, List

from pydantic import BaseModel

from water.agents.streaming import (
    StreamChunk,
    StreamingResponse,
    StreamingProvider,
    MockStreamProvider,
    OpenAIStreamProvider,
    AnthropicStreamProvider,
    create_streaming_agent_task,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TopicInput(BaseModel):
    topic: str


class TopicOutput(BaseModel):
    response: str
    topic: str


# ---------------------------------------------------------------------------
# StreamChunk tests
# ---------------------------------------------------------------------------

def test_stream_chunk_defaults():
    """StreamChunk initialises with sensible defaults."""
    chunk = StreamChunk()
    assert chunk.delta == ""
    assert chunk.finish_reason is None
    assert chunk.metadata == {}


def test_stream_chunk_with_values():
    """StreamChunk stores the provided values."""
    chunk = StreamChunk(delta="hello", finish_reason="stop", metadata={"idx": 0})
    assert chunk.delta == "hello"
    assert chunk.finish_reason == "stop"
    assert chunk.metadata == {"idx": 0}


# ---------------------------------------------------------------------------
# StreamingResponse tests
# ---------------------------------------------------------------------------

def test_streaming_response_empty():
    """Empty StreamingResponse returns empty text and no finish_reason."""
    sr = StreamingResponse()
    assert sr.text == ""
    assert sr.finish_reason is None
    assert sr.metadata == {}


def test_streaming_response_collects_chunks():
    """StreamingResponse concatenates deltas from multiple chunks."""
    sr = StreamingResponse()
    sr.add(StreamChunk(delta="Hello"))
    sr.add(StreamChunk(delta=" "))
    sr.add(StreamChunk(delta="world", finish_reason="stop", metadata={"tok": 3}))

    assert sr.text == "Hello world"
    assert sr.finish_reason == "stop"
    assert sr.metadata == {"tok": 3}
    assert len(sr.chunks) == 3


def test_streaming_response_metadata_merge():
    """Later chunk metadata overrides earlier keys."""
    sr = StreamingResponse()
    sr.add(StreamChunk(delta="a", metadata={"k": 1, "x": 10}))
    sr.add(StreamChunk(delta="b", metadata={"k": 2}))

    assert sr.metadata == {"k": 2, "x": 10}


# ---------------------------------------------------------------------------
# MockStreamProvider tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_stream_provider_default():
    """MockStreamProvider yields words from the default response."""
    provider = MockStreamProvider(default_response="hello world")

    chunks: List[StreamChunk] = []
    async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    # "hello world" -> two words -> two chunks
    assert len(chunks) == 2
    assert chunks[0].delta == "hello"
    assert chunks[1].delta == " world"
    # Reassembled text
    assert "".join(c.delta for c in chunks) == "hello world"
    # Last chunk has finish_reason
    assert chunks[-1].finish_reason == "stop"
    assert chunks[0].finish_reason is None


@pytest.mark.asyncio
async def test_mock_stream_provider_multiple_responses():
    """MockStreamProvider cycles through configured responses."""
    provider = MockStreamProvider(responses=["first reply", "second reply"])

    # First call
    text1_parts = []
    async for chunk in provider.stream([{"role": "user", "content": "a"}]):
        text1_parts.append(chunk.delta)
    assert "".join(text1_parts) == "first reply"

    # Second call
    text2_parts = []
    async for chunk in provider.stream([{"role": "user", "content": "b"}]):
        text2_parts.append(chunk.delta)
    assert "".join(text2_parts) == "second reply"

    # Third call cycles back
    text3_parts = []
    async for chunk in provider.stream([{"role": "user", "content": "c"}]):
        text3_parts.append(chunk.delta)
    assert "".join(text3_parts) == "first reply"


@pytest.mark.asyncio
async def test_mock_stream_provider_call_history():
    """MockStreamProvider records call history."""
    provider = MockStreamProvider()
    messages = [{"role": "user", "content": "test"}]

    async for _ in provider.stream(messages):
        pass

    assert len(provider.call_history) == 1
    assert provider.call_history[0] == messages


@pytest.mark.asyncio
async def test_mock_stream_provider_complete_fallback():
    """MockStreamProvider.complete() collects stream into a dict."""
    provider = MockStreamProvider(default_response="collected text")
    result = await provider.complete([{"role": "user", "content": "hi"}])

    assert result == {"text": "collected text"}


# ---------------------------------------------------------------------------
# create_streaming_agent_task tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_streaming_agent_task_basic():
    """Basic streaming agent task collects chunks and returns dict."""
    mock = MockStreamProvider(default_response="streamed answer")

    task = create_streaming_agent_task(
        id="stream_basic",
        description="A streaming agent",
        prompt_template="Tell me about {topic}",
        provider_instance=mock,
    )

    assert task.id == "stream_basic"

    result = await task.execute({"input_data": {"topic": "water"}}, None)
    assert result["response"] == "streamed answer"
    assert result["topic"] == "water"

    # Verify provider received the formatted prompt
    assert len(mock.call_history) == 1
    assert mock.call_history[0][-1]["content"] == "Tell me about water"


@pytest.mark.asyncio
async def test_streaming_agent_task_on_chunk_callback():
    """on_chunk callback is invoked for every chunk."""
    received: List[StreamChunk] = []

    def my_callback(chunk: StreamChunk):
        received.append(chunk)

    mock = MockStreamProvider(default_response="a b c")

    task = create_streaming_agent_task(
        id="cb_test",
        prompt_template="{prompt}",
        provider_instance=mock,
        on_chunk=my_callback,
    )

    result = await task.execute({"input_data": {"prompt": "go"}}, None)

    # "a b c" -> 3 words -> 3 chunks
    assert len(received) == 3
    assert received[0].delta == "a"
    assert received[1].delta == " b"
    assert received[2].delta == " c"
    assert result["response"] == "a b c"


@pytest.mark.asyncio
async def test_streaming_agent_task_system_prompt():
    """System prompt is included as the first message."""
    mock = MockStreamProvider(default_response="ok")

    task = create_streaming_agent_task(
        id="sys_stream",
        prompt_template="Do something",
        system_prompt="You are helpful.",
        provider_instance=mock,
    )

    await task.execute({"input_data": {}}, None)

    messages = mock.call_history[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful."
    assert messages[1]["role"] == "user"


@pytest.mark.asyncio
async def test_streaming_agent_task_no_template():
    """Without a template the 'prompt' key is used."""
    mock = MockStreamProvider(default_response="done")

    task = create_streaming_agent_task(
        id="no_tpl_stream",
        provider_instance=mock,
    )

    result = await task.execute(
        {"input_data": {"prompt": "Tell me a joke"}}, None
    )

    sent = mock.call_history[0][-1]["content"]
    assert sent == "Tell me a joke"
    assert result["response"] == "done"


@pytest.mark.asyncio
async def test_streaming_agent_task_missing_template_variable():
    """Missing template variable raises ValueError."""
    mock = MockStreamProvider()

    task = create_streaming_agent_task(
        id="bad_tpl_stream",
        prompt_template="Hello {missing_var}",
        provider_instance=mock,
    )

    with pytest.raises(ValueError, match="not found in input data"):
        await task.execute({"input_data": {"other": "value"}}, None)


@pytest.mark.asyncio
async def test_streaming_agent_task_default_provider():
    """Omitting provider_instance falls back to MockStreamProvider."""
    task = create_streaming_agent_task(
        id="default_prov",
        prompt_template="{prompt}",
    )

    result = await task.execute({"input_data": {"prompt": "hi"}}, None)
    # Default MockStreamProvider response
    assert result["response"] == "mock streaming response"


# ---------------------------------------------------------------------------
# Provider instantiation tests
# ---------------------------------------------------------------------------

def test_openai_stream_provider_instantiation():
    """OpenAIStreamProvider can be instantiated with parameters."""
    provider = OpenAIStreamProvider(
        model="gpt-4", api_key="test-key", temperature=0.5, max_tokens=512
    )
    assert provider.model == "gpt-4"
    assert provider.api_key == "test-key"
    assert provider.temperature == 0.5
    assert provider.max_tokens == 512


def test_anthropic_stream_provider_instantiation():
    """AnthropicStreamProvider can be instantiated with parameters."""
    provider = AnthropicStreamProvider(
        model="claude-3-opus-20240229",
        api_key="test-key",
        temperature=0.3,
        max_tokens=2048,
    )
    assert provider.model == "claude-3-opus-20240229"
    assert provider.api_key == "test-key"
    assert provider.temperature == 0.3
    assert provider.max_tokens == 2048
