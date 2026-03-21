"""
Content filtering guardrails.

Blocks or flags PII patterns, prompt injection attempts, and profanity.
"""

import re
from typing import Any, Dict, List, Optional

from water.guardrails.base import Guardrail, GuardrailResult


# Common PII patterns
_PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
}

# Common prompt injection patterns
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior\s+(instructions|context)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
]


class ContentFilter(Guardrail):
    """
    Filter content for PII, prompt injection, and profanity.

    Args:
        block_pii: Block messages containing PII patterns.
        block_injection: Block prompt injection attempts.
        block_profanity: Block profanity (requires custom word list).
        pii_types: Which PII types to check (default: all).
        profanity_words: Custom list of blocked words.
        action: What to do on failure ("block", "warn", "retry", "fallback").
    """

    name = "content_filter"

    def __init__(
        self,
        block_pii: bool = False,
        block_injection: bool = False,
        block_profanity: bool = False,
        pii_types: Optional[List[str]] = None,
        profanity_words: Optional[List[str]] = None,
        action: str = "block",
        name: Optional[str] = None,
    ):
        super().__init__(name=name, action=action)
        self.block_pii = block_pii
        self.block_injection = block_injection
        self.block_profanity = block_profanity
        self.pii_types = pii_types
        self.profanity_words = [w.lower() for w in (profanity_words or [])]

    def validate(self, data: Dict[str, Any], context: Optional[Any] = None) -> GuardrailResult:
        text = self._extract_text(data)
        if not text:
            return GuardrailResult(passed=True)

        # PII check
        if self.block_pii:
            pii_found = self._check_pii(text)
            if pii_found:
                return GuardrailResult(
                    passed=False,
                    reason=f"PII detected: {', '.join(pii_found)}",
                    details={"pii_types": pii_found},
                )

        # Injection check
        if self.block_injection:
            if self._check_injection(text):
                return GuardrailResult(
                    passed=False,
                    reason="Potential prompt injection detected",
                    details={"text_snippet": text[:100]},
                )

        # Profanity check
        if self.block_profanity and self.profanity_words:
            found = self._check_profanity(text)
            if found:
                return GuardrailResult(
                    passed=False,
                    reason=f"Profanity detected",
                    details={"words_found": found},
                )

        return GuardrailResult(passed=True)

    def _extract_text(self, data: Dict[str, Any]) -> str:
        """Extract all text content from data dict."""
        parts = []
        for value in data.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                parts.append(self._extract_text(value))
        return " ".join(parts)

    def _check_pii(self, text: str) -> List[str]:
        """Check for PII patterns. Returns list of types found."""
        found = []
        check_types = self.pii_types or list(_PII_PATTERNS.keys())
        for pii_type in check_types:
            pattern = _PII_PATTERNS.get(pii_type)
            if pattern and pattern.search(text):
                found.append(pii_type)
        return found

    def _check_injection(self, text: str) -> bool:
        """Check for prompt injection patterns."""
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _check_profanity(self, text: str) -> List[str]:
        """Check for profanity words."""
        text_lower = text.lower()
        return [w for w in self.profanity_words if w in text_lower]
