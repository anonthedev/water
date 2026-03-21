"""
Flow-level Cost & Token Tracking for Water flows.

Provides middleware-compatible cost tracking that records token usage and
computes per-task costs based on configurable model pricing.  Supports
budget limits with configurable warn/stop behaviour.
"""

import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from water.middleware.base import Middleware

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD)
DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
}


class BudgetExceededError(Exception):
    """Raised when the cumulative cost exceeds the configured budget limit."""


@dataclass
class TokenUsage:
    """Tracks input and output token counts for a single interaction."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TaskCost:
    """Cost record for a single task execution."""

    task_id: str
    model: str = "unknown"
    tokens: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "model": self.model,
            "input_tokens": self.tokens.input_tokens,
            "output_tokens": self.tokens.output_tokens,
            "total_tokens": self.tokens.total_tokens,
            "cost_usd": self.cost_usd,
            "timestamp": self.timestamp,
        }


@dataclass
class CostSummary:
    """Aggregated cost summary across all tracked tasks."""

    total_cost_usd: float = 0.0
    total_tokens: TokenUsage = field(default_factory=TokenUsage)
    task_costs: List[TaskCost] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=== Cost Summary ===",
            f"Total cost:   ${self.total_cost_usd:.6f}",
            f"Total tokens: {self.total_tokens.total_tokens} "
            f"(input: {self.total_tokens.input_tokens}, "
            f"output: {self.total_tokens.output_tokens})",
            f"Tasks tracked: {len(self.task_costs)}",
        ]
        if self.task_costs:
            lines.append("")
            lines.append("Per-task breakdown:")
            for tc in self.task_costs:
                lines.append(
                    f"  - {tc.task_id} [{tc.model}]: "
                    f"${tc.cost_usd:.6f} "
                    f"({tc.tokens.total_tokens} tokens)"
                )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_tokens.input_tokens,
            "total_output_tokens": self.total_tokens.output_tokens,
            "total_tokens": self.total_tokens.total_tokens,
            "tasks": [tc.to_dict() for tc in self.task_costs],
        }


class CostTracker(Middleware):
    """Middleware that tracks token usage and cost for every task in a flow.

    Parameters
    ----------
    pricing:
        Optional dict mapping model names to ``{"input": <price>, "output": <price>}``
        where prices are USD per 1 million tokens.  Merged on top of
        ``DEFAULT_PRICING``.
    budget_limit:
        Optional maximum cumulative spend (USD).  When exceeded the tracker
        either warns or raises ``BudgetExceededError`` depending on
        *on_budget_exceeded*.
    on_budget_exceeded:
        ``"warn"`` (default) to emit a warning, or ``"stop"`` to raise
        ``BudgetExceededError``.
    """

    def __init__(
        self,
        pricing: Optional[Dict[str, Dict[str, float]]] = None,
        budget_limit: Optional[float] = None,
        on_budget_exceeded: str = "warn",
    ) -> None:
        self.pricing: Dict[str, Dict[str, float]] = {
            **DEFAULT_PRICING,
            **(pricing or {}),
        }
        self.budget_limit = budget_limit
        self.on_budget_exceeded = on_budget_exceeded
        self._task_costs: List[TaskCost] = []

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def calculate_cost(self, model: str, tokens: TokenUsage) -> float:
        """Return the USD cost for the given model and token usage.

        If the model is not found in the pricing table the cost is 0.0.
        """
        rates = self.pricing.get(model)
        if rates is None:
            return 0.0
        input_cost = (tokens.input_tokens / 1_000_000) * rates.get("input", 0.0)
        output_cost = (tokens.output_tokens / 1_000_000) * rates.get("output", 0.0)
        return input_cost + output_cost

    def record(self, task_id: str, model: str, tokens: TokenUsage) -> TaskCost:
        """Record a cost entry and enforce budget limits."""
        cost = self.calculate_cost(model, tokens)
        entry = TaskCost(
            task_id=task_id,
            model=model,
            tokens=tokens,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._task_costs.append(entry)
        self._check_budget()
        return entry

    def get_summary(self) -> CostSummary:
        """Return an aggregated ``CostSummary`` over all recorded tasks."""
        total_input = sum(tc.tokens.input_tokens for tc in self._task_costs)
        total_output = sum(tc.tokens.output_tokens for tc in self._task_costs)
        total_cost = sum(tc.cost_usd for tc in self._task_costs)
        return CostSummary(
            total_cost_usd=total_cost,
            total_tokens=TokenUsage(
                input_tokens=total_input, output_tokens=total_output
            ),
            task_costs=list(self._task_costs),
        )

    def reset(self) -> None:
        """Clear all recorded cost entries."""
        self._task_costs.clear()

    # ------------------------------------------------------------------
    # Middleware interface
    # ------------------------------------------------------------------

    async def before_task(
        self, task_id: str, data: dict, context: Any
    ) -> dict:
        """Pass-through; cost is recorded after the task completes."""
        return data

    async def after_task(
        self, task_id: str, data: dict, result: dict, context: Any
    ) -> dict:
        """Extract token usage from the task result and record cost."""
        usage_info = None
        if isinstance(result, dict):
            usage_info = result.get("usage") or result.get("token_usage")
        if usage_info and isinstance(usage_info, dict):
            tokens = TokenUsage(
                input_tokens=usage_info.get("input_tokens", 0),
                output_tokens=usage_info.get("output_tokens", 0),
            )
            model = (
                result.get("model", "unknown")
                if isinstance(result, dict)
                else "unknown"
            )
            self.record(task_id, model, tokens)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_budget(self) -> None:
        if self.budget_limit is None:
            return
        total = sum(tc.cost_usd for tc in self._task_costs)
        if total > self.budget_limit:
            msg = (
                f"Budget exceeded: ${total:.6f} > "
                f"${self.budget_limit:.6f} limit"
            )
            if self.on_budget_exceeded == "stop":
                raise BudgetExceededError(msg)
            else:
                warnings.warn(msg, stacklevel=2)
                logger.warning(msg)
