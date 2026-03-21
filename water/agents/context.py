"""
Context Window Management for Agent Tasks.

Automatically handles conversation history truncation, summarization,
and token counting for LLM-powered agent tasks.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TruncationStrategy(str, Enum):
    """Strategy for managing context when it exceeds limits."""
    SLIDING_WINDOW = "sliding_window"
    SUMMARIZE = "summarize"
    PRIORITY = "priority"


class TokenCounter:
    """
    Provider-aware token counting.

    Uses tiktoken for OpenAI models and character-based estimation
    as a fallback for other providers.
    """

    def __init__(self, provider: str = "default", model: Optional[str] = None):
        self.provider = provider
        self.model = model
        self._encoder = None

    def count(self, text: str) -> int:
        """Count tokens in a text string."""
        if self.provider == "openai" and self.model:
            return self._count_tiktoken(text)
        # Fallback: ~4 chars per token
        return max(1, len(text) // 4)

    def count_messages(self, messages: List[Dict[str, str]]) -> int:
        """Count total tokens across all messages."""
        total = 0
        for msg in messages:
            # Message overhead (~4 tokens per message for role/formatting)
            total += 4
            total += self.count(msg.get("content", ""))
        return total

    def _count_tiktoken(self, text: str) -> int:
        """Count tokens using tiktoken (lazy import)."""
        try:
            if self._encoder is None:
                import tiktoken
                try:
                    self._encoder = tiktoken.encoding_for_model(self.model)
                except KeyError:
                    self._encoder = tiktoken.get_encoding("cl100k_base")
            return len(self._encoder.encode(text))
        except ImportError:
            # tiktoken not installed, fall back
            return max(1, len(text) // 4)


class ContextManager:
    """
    Manages conversation history with automatic truncation.

    Prevents context overflow and optimizes token usage by applying
    truncation strategies when messages exceed the token budget.

    Args:
        max_tokens: Maximum tokens allowed for context.
        strategy: How to truncate ("sliding_window", "summarize", "priority").
        reserve_tokens: Tokens to reserve for the LLM's response.
        provider: Provider name for token counting ("openai", "anthropic", etc.).
        model: Model name for accurate token counting.
        summarize_fn: Optional async function for summarization strategy.
            Signature: async (messages: list) -> str
    """

    def __init__(
        self,
        max_tokens: int = 8000,
        strategy: str = "sliding_window",
        reserve_tokens: int = 1000,
        provider: str = "default",
        model: Optional[str] = None,
        summarize_fn: Optional[Any] = None,
    ):
        self.max_tokens = max_tokens
        self.strategy = TruncationStrategy(strategy)
        self.reserve_tokens = reserve_tokens
        self.token_counter = TokenCounter(provider=provider, model=model)
        self.summarize_fn = summarize_fn
        self._total_tokens_used = 0

    @property
    def available_tokens(self) -> int:
        """Tokens available for context (max - reserve)."""
        return self.max_tokens - self.reserve_tokens

    @property
    def total_tokens_used(self) -> int:
        """Total tokens processed across all calls."""
        return self._total_tokens_used

    async def prepare_messages(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Prepare messages for an LLM call, truncating if necessary.

        Applies the configured truncation strategy to keep messages
        within the token budget.

        Args:
            messages: Full conversation messages.

        Returns:
            Truncated/processed messages within token budget.
        """
        token_count = self.token_counter.count_messages(messages)
        self._total_tokens_used += token_count

        if token_count <= self.available_tokens:
            return messages

        logger.info(
            f"Context exceeds budget ({token_count}/{self.available_tokens} tokens). "
            f"Applying {self.strategy.value} strategy."
        )

        if self.strategy == TruncationStrategy.SLIDING_WINDOW:
            return self._sliding_window(messages)
        elif self.strategy == TruncationStrategy.SUMMARIZE:
            return await self._summarize(messages)
        elif self.strategy == TruncationStrategy.PRIORITY:
            return self._priority(messages)
        else:
            return self._sliding_window(messages)

    def _sliding_window(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Keep system prompt + last N messages that fit."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        system_tokens = self.token_counter.count_messages(system_msgs)
        budget = self.available_tokens - system_tokens

        # Work backwards from the most recent messages
        kept = []
        running_tokens = 0
        for msg in reversed(other_msgs):
            msg_tokens = self.token_counter.count_messages([msg])
            if running_tokens + msg_tokens > budget:
                break
            kept.insert(0, msg)
            running_tokens += msg_tokens

        return system_msgs + kept

    async def _summarize(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Compress older messages into a summary."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        if len(other_msgs) <= 2:
            return self._sliding_window(messages)

        # Keep the most recent messages, summarize the rest
        split = max(1, len(other_msgs) // 2)
        old_msgs = other_msgs[:split]
        recent_msgs = other_msgs[split:]

        if self.summarize_fn:
            summary_text = await self.summarize_fn(old_msgs)
        else:
            # No summarize_fn provided -- fall back to naive truncation of
            # each message to 100 characters.  This is NOT a real summary;
            # callers should supply a summarize_fn for production use.
            logger.warning(
                "SUMMARIZE strategy requested but no summarize_fn provided. "
                "Falling back to truncation of %d older messages. "
                "Provide a summarize_fn for proper summarization.",
                len(old_msgs),
            )
            parts = [m.get("content", "")[:100] for m in old_msgs]
            summary_text = f"[Summary of {len(old_msgs)} earlier messages: {'; '.join(parts)}]"

        summary_msg = {"role": "system", "content": summary_text}
        result = system_msgs + [summary_msg] + recent_msgs

        # If still over budget, apply sliding window
        if self.token_counter.count_messages(result) > self.available_tokens:
            return self._sliding_window(result)

        return result

    def _priority(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Keep system prompt + recent + tool results, drop old user/assistant msgs."""
        priority_order = {"system": 0, "tool": 1, "assistant": 3, "user": 2}

        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        system_tokens = self.token_counter.count_messages(system_msgs)
        budget = self.available_tokens - system_tokens

        # Score messages: recent ones get higher priority
        scored = []
        for i, msg in enumerate(other_msgs):
            role_priority = priority_order.get(msg.get("role", "user"), 2)
            recency = i  # Higher index = more recent
            score = recency * 10 - role_priority
            scored.append((score, msg))

        # Sort by score descending (highest priority first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Take messages until budget is filled
        kept = []
        running_tokens = 0
        for score, msg in scored:
            msg_tokens = self.token_counter.count_messages([msg])
            if running_tokens + msg_tokens > budget:
                continue
            kept.append((score, msg))
            running_tokens += msg_tokens

        # Restore original order
        kept.sort(key=lambda x: x[0])
        return system_msgs + [msg for _, msg in kept]
