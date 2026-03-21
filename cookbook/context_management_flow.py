"""
Context Window Management Flow Example: Managing LLM Conversation History

This example demonstrates Water's context window management for keeping
conversation history within token budgets. It shows:
  - TokenCounter for counting tokens (with fallback estimation)
  - ContextManager with sliding_window strategy
  - ContextManager with summarize strategy
  - ContextManager with priority strategy
  - Tracking total token usage across calls

NOTE: This example uses the built-in character-based token estimator
      (no tiktoken dependency required).
"""

import asyncio
from typing import Any, Dict, List

from water.agents.context import ContextManager, TokenCounter, TruncationStrategy


# ---------------------------------------------------------------------------
# Example 1: TokenCounter basics
# ---------------------------------------------------------------------------

async def example_token_counter():
    """Count tokens in text and messages using the fallback estimator."""
    print("=== Example 1: TokenCounter ===\n")

    counter = TokenCounter(provider="default")

    # Count tokens in a simple string
    text = "Water is a lightweight Python workflow framework for building AI agent pipelines."
    tokens = counter.count(text)
    print(f"Text:     '{text}'")
    print(f"Tokens:   {tokens} (estimated at ~4 chars/token)")
    print()

    # Count tokens across a conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the Water framework?"},
        {"role": "assistant", "content": "Water is a Python framework for building workflows and AI agent pipelines."},
        {"role": "user", "content": "How do I create a flow?"},
    ]
    total = counter.count_messages(messages)
    print(f"Conversation ({len(messages)} messages): {total} tokens")
    print()


# ---------------------------------------------------------------------------
# Example 2: Sliding window truncation
# ---------------------------------------------------------------------------

async def example_sliding_window():
    """Truncate conversation history using a sliding window strategy."""
    print("=== Example 2: Sliding Window Strategy ===\n")

    ctx = ContextManager(
        max_tokens=100,        # small budget for demonstration
        strategy="sliding_window",
        reserve_tokens=20,
        provider="default",
    )

    print(f"Max tokens:      {ctx.max_tokens}")
    print(f"Available tokens: {ctx.available_tokens}")
    print()

    # Build a long conversation
    messages = [
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Message 1: Hello, can you help me?"},
        {"role": "assistant", "content": "Message 2: Of course! What do you need?"},
        {"role": "user", "content": "Message 3: I need help with Python async programming."},
        {"role": "assistant", "content": "Message 4: Async in Python uses asyncio. You define coroutines with async def."},
        {"role": "user", "content": "Message 5: Can you show me an example with gather?"},
        {"role": "assistant", "content": "Message 6: Sure! asyncio.gather runs multiple coroutines concurrently."},
        {"role": "user", "content": "Message 7: What about error handling in async code?"},
    ]

    token_count = ctx.token_counter.count_messages(messages)
    print(f"Original conversation: {len(messages)} messages, ~{token_count} tokens")

    prepared = await ctx.prepare_messages(messages)
    prepared_tokens = ctx.token_counter.count_messages(prepared)
    print(f"After sliding window:  {len(prepared)} messages, ~{prepared_tokens} tokens")
    print(f"Kept messages:")
    for msg in prepared:
        role = msg["role"]
        content = msg["content"][:50]
        print(f"  [{role}] {content}...")
    print()


# ---------------------------------------------------------------------------
# Example 3: Summarize strategy
# ---------------------------------------------------------------------------

async def example_summarize():
    """Compress older messages into a summary to save tokens."""
    print("=== Example 3: Summarize Strategy ===\n")

    # Custom summarize function
    async def mock_summarize(messages: list) -> str:
        topics = []
        for m in messages:
            content = m.get("content", "")
            if "Python" in content:
                topics.append("Python basics")
            elif "async" in content:
                topics.append("async programming")
            elif "error" in content:
                topics.append("error handling")
            else:
                topics.append("general discussion")
        return f"[Summary: Earlier conversation covered {', '.join(set(topics))}]"

    ctx = ContextManager(
        max_tokens=120,
        strategy="summarize",
        reserve_tokens=20,
        provider="default",
        summarize_fn=mock_summarize,
    )

    messages = [
        {"role": "system", "content": "You are a Python tutor."},
        {"role": "user", "content": "Teach me Python basics."},
        {"role": "assistant", "content": "Python is a versatile language. Let's start with variables and functions."},
        {"role": "user", "content": "Now teach me about async programming."},
        {"role": "assistant", "content": "Async programming in Python uses asyncio for concurrent code execution."},
        {"role": "user", "content": "How do I handle errors in async functions?"},
        {"role": "assistant", "content": "Use try/except blocks inside async functions, and handle exceptions from gather."},
        {"role": "user", "content": "Great, now show me a complete async web scraper example."},
    ]

    token_count = ctx.token_counter.count_messages(messages)
    print(f"Original: {len(messages)} messages, ~{token_count} tokens")

    prepared = await ctx.prepare_messages(messages)
    prepared_tokens = ctx.token_counter.count_messages(prepared)
    print(f"After summarization: {len(prepared)} messages, ~{prepared_tokens} tokens")
    print()
    for msg in prepared:
        role = msg["role"]
        content = msg["content"][:80]
        print(f"  [{role}] {content}{'...' if len(msg['content']) > 80 else ''}")
    print()
    print(f"Total tokens processed so far: {ctx.total_tokens_used}")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_token_counter()
    await example_sliding_window()
    await example_summarize()
    print("All context management examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
