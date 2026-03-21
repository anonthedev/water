"""
Guardrails base classes for Water.

Provides the foundation for input/output validation, filtering,
and constraint enforcement at the harness level.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GuardrailAction(str, Enum):
    """Action to take when a guardrail fails."""
    BLOCK = "block"
    WARN = "warn"
    RETRY = "retry"
    FALLBACK = "fallback"


@dataclass
class GuardrailResult:
    """Result of a guardrail validation check."""
    passed: bool
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    guardrail_name: str = ""

    def __bool__(self) -> bool:
        return self.passed


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails with action='block'."""

    def __init__(self, result: GuardrailResult):
        self.result = result
        super().__init__(
            f"Guardrail violation ({result.guardrail_name}): {result.reason}"
        )


class Guardrail(ABC):
    """
    Base class for input/output validation rules.

    Subclass and implement ``validate`` to create custom guardrails.
    """

    name: str = "guardrail"
    action: GuardrailAction = GuardrailAction.BLOCK

    def __init__(
        self,
        name: Optional[str] = None,
        action: str = "block",
    ):
        if name:
            self.name = name
        self.action = GuardrailAction(action)

    @abstractmethod
    def validate(self, data: Dict[str, Any], context: Optional[Any] = None) -> GuardrailResult:
        """
        Validate data against this guardrail.

        Args:
            data: The data to validate (input or output).
            context: Optional execution context.

        Returns:
            GuardrailResult indicating pass/fail.
        """
        ...

    def check(self, data: Dict[str, Any], context: Optional[Any] = None) -> GuardrailResult:
        """Run validation and handle the action policy."""
        result = self.validate(data, context)
        result.guardrail_name = self.name

        if not result.passed and self.action == GuardrailAction.BLOCK:
            raise GuardrailViolation(result)

        return result


class GuardrailChain:
    """
    Compose multiple guardrails in sequence.

    All guardrails are checked in order. The chain fails if any
    guardrail with action='block' fails.
    """

    def __init__(self, guardrails: Optional[List[Guardrail]] = None):
        self.guardrails: List[Guardrail] = guardrails or []

    def add(self, guardrail: Guardrail) -> "GuardrailChain":
        """Add a guardrail to the chain."""
        self.guardrails.append(guardrail)
        return self

    def check(self, data: Dict[str, Any], context: Optional[Any] = None) -> List[GuardrailResult]:
        """
        Run all guardrails in sequence.

        Returns:
            List of GuardrailResults. Raises GuardrailViolation on first
            blocking failure.
        """
        results = []
        for guardrail in self.guardrails:
            result = guardrail.check(data, context)
            results.append(result)
        return results

    def __len__(self) -> int:
        return len(self.guardrails)
