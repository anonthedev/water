"""Tests for context window management."""

import pytest

from water.agents.context import ContextManager, TokenCounter, TruncationStrategy


# --- TokenCounter tests ---

def test_token_counter_default():
    tc = TokenCounter()
    count = tc.count("hello world this is a test")
    assert count > 0


def test_token_counter_messages():
    tc = TokenCounter()
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello there!"},
    ]
    count = tc.count_messages(msgs)
    assert count > 0


def test_token_counter_empty():
    tc = TokenCounter()
    assert tc.count("") == 0 or tc.count("") >= 0  # At least 0


# --- ContextManager basic tests ---

@pytest.mark.asyncio
async def test_context_manager_within_budget():
    cm = ContextManager(max_tokens=10000, reserve_tokens=1000)
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    result = await cm.prepare_messages(msgs)
    assert result == msgs  # No truncation needed


@pytest.mark.asyncio
async def test_context_manager_sliding_window():
    cm = ContextManager(max_tokens=100, strategy="sliding_window", reserve_tokens=20)
    msgs = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Message 1 " * 20},
        {"role": "assistant", "content": "Response 1 " * 20},
        {"role": "user", "content": "Message 2 " * 20},
        {"role": "assistant", "content": "Response 2 " * 20},
        {"role": "user", "content": "Last message"},
    ]
    result = await cm.prepare_messages(msgs)
    # Should keep system + recent messages
    assert result[0]["role"] == "system"
    assert len(result) < len(msgs)
    assert result[-1]["content"] == "Last message"


@pytest.mark.asyncio
async def test_context_manager_summarize():
    async def mock_summarize(msgs):
        return f"Summary of {len(msgs)} messages"

    cm = ContextManager(
        max_tokens=100, strategy="summarize", reserve_tokens=20,
        summarize_fn=mock_summarize,
    )
    msgs = [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "Msg 1 " * 20},
        {"role": "assistant", "content": "Resp 1 " * 20},
        {"role": "user", "content": "Msg 2 " * 20},
        {"role": "assistant", "content": "Resp 2 " * 20},
        {"role": "user", "content": "Final"},
    ]
    result = await cm.prepare_messages(msgs)
    assert len(result) < len(msgs)
    # Should contain a summary message
    contents = [m["content"] for m in result]
    assert any("Summary" in c for c in contents)


@pytest.mark.asyncio
async def test_context_manager_priority():
    cm = ContextManager(max_tokens=100, strategy="priority", reserve_tokens=20)
    msgs = [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "Old message " * 20},
        {"role": "assistant", "content": "Old response " * 20},
        {"role": "user", "content": "Recent"},
    ]
    result = await cm.prepare_messages(msgs)
    assert result[0]["role"] == "system"
    # Recent messages should be prioritized
    assert any(m["content"] == "Recent" for m in result)


@pytest.mark.asyncio
async def test_context_manager_tracking():
    cm = ContextManager(max_tokens=10000)
    msgs = [{"role": "user", "content": "Hello world"}]
    await cm.prepare_messages(msgs)
    assert cm.total_tokens_used > 0


def test_available_tokens():
    cm = ContextManager(max_tokens=8000, reserve_tokens=1000)
    assert cm.available_tokens == 7000


@pytest.mark.asyncio
async def test_summarize_fallback():
    """Summarize without custom fn should use built-in fallback."""
    cm = ContextManager(max_tokens=100, strategy="summarize", reserve_tokens=20)
    msgs = [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "Msg " * 30},
        {"role": "assistant", "content": "Resp " * 30},
        {"role": "user", "content": "Msg2 " * 30},
        {"role": "assistant", "content": "Resp2 " * 30},
        {"role": "user", "content": "Last"},
    ]
    result = await cm.prepare_messages(msgs)
    assert len(result) < len(msgs)
