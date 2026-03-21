"""
Cost guardrail.

Enforces token and cost budgets per flow or task execution.
"""

from typing import Any, Dict, Optional

from water.guardrails.base import Guardrail, GuardrailResult


class CostGuardrail(Guardrail):
    """
    Enforce token/cost budgets.

    Tracks cumulative token usage and cost across calls. Fails when
    budget is exceeded.

    Args:
        max_tokens: Maximum total tokens allowed (input + output).
        max_cost_usd: Maximum cost in USD (requires token pricing).
        token_key: Key in data where token usage is reported.
        cost_per_1k_tokens: Cost per 1000 tokens for budget calculation.
        action: What to do on failure.
    """

    name = "cost_guardrail"

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        max_cost_usd: Optional[float] = None,
        token_key: str = "usage",
        cost_per_1k_tokens: float = 0.002,
        action: str = "block",
        name: Optional[str] = None,
    ):
        super().__init__(name=name, action=action)
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.token_key = token_key
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self._total_tokens = 0
        self._total_cost = 0.0

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def reset(self) -> None:
        """Reset cumulative counters."""
        self._total_tokens = 0
        self._total_cost = 0.0

    def validate(self, data: Dict[str, Any], context: Optional[Any] = None) -> GuardrailResult:
        usage = data.get(self.token_key, {})
        tokens = 0

        if isinstance(usage, dict):
            tokens = usage.get("total_tokens", 0)
            if not tokens:
                tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        elif isinstance(usage, (int, float)):
            tokens = int(usage)

        self._total_tokens += tokens
        cost = (tokens / 1000) * self.cost_per_1k_tokens
        self._total_cost += cost

        if self.max_tokens and self._total_tokens > self.max_tokens:
            return GuardrailResult(
                passed=False,
                reason=f"Token budget exceeded: {self._total_tokens}/{self.max_tokens}",
                details={"total_tokens": self._total_tokens, "limit": self.max_tokens},
            )

        if self.max_cost_usd and self._total_cost > self.max_cost_usd:
            return GuardrailResult(
                passed=False,
                reason=f"Cost budget exceeded: ${self._total_cost:.4f}/${self.max_cost_usd:.4f}",
                details={"total_cost": self._total_cost, "limit": self.max_cost_usd},
            )

        return GuardrailResult(
            passed=True,
            details={"total_tokens": self._total_tokens, "total_cost": self._total_cost},
        )
