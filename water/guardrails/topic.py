"""
Topic guardrail.

Keeps agents on-topic by checking content against allowed/blocked topics
using keyword matching.
"""

import re
from typing import Any, Dict, List, Optional

from water.guardrails.base import Guardrail, GuardrailResult


class TopicGuardrail(Guardrail):
    """
    Keep agents on-topic with keyword/pattern matching.

    Args:
        allowed_topics: List of allowed topic keywords. If set, content must
            match at least one.
        blocked_topics: List of blocked topic keywords. Content matching any
            is rejected.
        case_sensitive: Whether matching is case-sensitive.
        action: What to do on failure.
    """

    name = "topic_guardrail"

    def __init__(
        self,
        allowed_topics: Optional[List[str]] = None,
        blocked_topics: Optional[List[str]] = None,
        case_sensitive: bool = False,
        action: str = "block",
        name: Optional[str] = None,
    ):
        super().__init__(name=name, action=action)
        self.allowed_topics = allowed_topics or []
        self.blocked_topics = blocked_topics or []
        self.case_sensitive = case_sensitive

    def validate(self, data: Dict[str, Any], context: Optional[Any] = None) -> GuardrailResult:
        text = self._extract_text(data)
        if not text:
            return GuardrailResult(passed=True)

        compare_text = text if self.case_sensitive else text.lower()

        # Check blocked topics first
        for topic in self.blocked_topics:
            compare_topic = topic if self.case_sensitive else topic.lower()
            if compare_topic in compare_text:
                return GuardrailResult(
                    passed=False,
                    reason=f"Blocked topic detected: {topic}",
                    details={"blocked_topic": topic},
                )

        # Check allowed topics
        if self.allowed_topics:
            for topic in self.allowed_topics:
                compare_topic = topic if self.case_sensitive else topic.lower()
                if compare_topic in compare_text:
                    return GuardrailResult(passed=True)
            return GuardrailResult(
                passed=False,
                reason="Content does not match any allowed topics",
                details={"allowed_topics": self.allowed_topics},
            )

        return GuardrailResult(passed=True)

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        """Extract all text from a data dict."""
        parts = []
        for value in data.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                parts.append(TopicGuardrail._extract_text(value))
        return " ".join(parts)
