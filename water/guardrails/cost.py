"""
Cost guardrail.

Enforces token and cost budgets per flow or task execution.
Supports both pre-execution estimation and post-execution validation.
"""

import logging
from typing import Any, Dict, Optional

from water.guardrails.base import Guardrail, GuardrailResult

logger = logging.getLogger(__name__)


class CostGuardrail(Guardrail):
    """
    Enforce token/cost budgets.

    Tracks cumulative token usage and cost across calls. Fails when
    budget is exceeded. Also provides pre-execution cost estimation
    to block calls before they are made.

    Args:
        max_tokens: Maximum total tokens allowed (input + output).
        max_cost_usd: Maximum cost in USD (requires token pricing).
        token_key: Key in data where token usage is reported.
        cost_per_1k_tokens: Cost per 1000 tokens for budget calculation.
        action: What to do on failure.
        chars_per_token: Approximate characters per token for estimation
            (default 4). Used by :meth:`estimate_tokens`.
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
        chars_per_token: float = 4.0,
    ):
        super().__init__(name=name, action=action)
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.token_key = token_key
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self.chars_per_token = chars_per_token
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

    # ------------------------------------------------------------------
    # Pre-execution estimation
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in *text* using a simple heuristic.

        Uses ``len(text) / chars_per_token`` (default 4 characters per
        token). This is intentionally a rough estimate; for precise
        counts, use a real tokeniser.

        Args:
            text: The input text to estimate.

        Returns:
            Estimated token count (always at least 1 for non-empty text).
        """
        if not text:
            return 0
        return max(1, int(len(text) / self.chars_per_token))

    def estimate_cost(self, estimated_tokens: int) -> float:
        """
        Estimate the cost in USD for *estimated_tokens*.

        Args:
            estimated_tokens: Number of tokens to price.

        Returns:
            Estimated cost in USD.
        """
        return (estimated_tokens / 1000) * self.cost_per_1k_tokens

    def pre_check(
        self,
        text: str,
        estimated_output_tokens: Optional[int] = None,
        context: Optional[Any] = None,
    ) -> GuardrailResult:
        """
        Check whether an upcoming LLM call is likely to exceed the budget.

        This should be called **before** the LLM call is made. It
        estimates the input token count from *text*, optionally adds
        *estimated_output_tokens*, and checks against the configured
        token and cost limits (including tokens already consumed).

        Args:
            text: The input text that will be sent to the LLM.
            estimated_output_tokens: Optional expected output tokens. If
                not provided, defaults to the estimated input tokens
                (i.e. assumes output ~ input).
            context: Optional execution context.

        Returns:
            :class:`GuardrailResult` — ``passed=True`` if the call is
            within budget, ``passed=False`` otherwise.
        """
        input_tokens = self.estimate_tokens(text)
        output_tokens = estimated_output_tokens if estimated_output_tokens is not None else input_tokens
        estimated_total = input_tokens + output_tokens
        estimated_cost = self.estimate_cost(estimated_total)

        projected_tokens = self._total_tokens + estimated_total
        projected_cost = self._total_cost + estimated_cost

        logger.debug(
            "CostGuardrail pre_check: estimated_input=%d estimated_output=%d "
            "projected_total_tokens=%d projected_total_cost=$%.4f",
            input_tokens, output_tokens, projected_tokens, projected_cost,
        )

        if self.max_tokens and projected_tokens > self.max_tokens:
            result = GuardrailResult(
                passed=False,
                reason=(
                    f"Estimated tokens ({estimated_total}) would exceed budget: "
                    f"projected {projected_tokens}/{self.max_tokens}"
                ),
                details={
                    "estimated_tokens": estimated_total,
                    "projected_total_tokens": projected_tokens,
                    "limit": self.max_tokens,
                },
            )
            result.guardrail_name = self.name
            return result

        if self.max_cost_usd and projected_cost > self.max_cost_usd:
            result = GuardrailResult(
                passed=False,
                reason=(
                    f"Estimated cost (${estimated_cost:.4f}) would exceed budget: "
                    f"projected ${projected_cost:.4f}/${self.max_cost_usd:.4f}"
                ),
                details={
                    "estimated_cost": estimated_cost,
                    "projected_total_cost": projected_cost,
                    "limit": self.max_cost_usd,
                },
            )
            result.guardrail_name = self.name
            return result

        return GuardrailResult(
            passed=True,
            details={
                "estimated_tokens": estimated_total,
                "estimated_cost": estimated_cost,
                "projected_total_tokens": projected_tokens,
                "projected_total_cost": projected_cost,
            },
        )

    # ------------------------------------------------------------------
    # Post-execution validation (existing behaviour)
    # ------------------------------------------------------------------

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
