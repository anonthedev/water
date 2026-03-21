"""
Retry with Feedback Loop for Water guardrails.

Provides a strategy that re-executes a callable when guardrails fail with
action=RETRY, feeding violation details back so the next attempt can
self-correct.  Supports configurable feedback templates, maximum retries,
and optional exponential backoff.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from water.guardrails.base import GuardrailResult
from water.core.types import SerializableMixin


@dataclass
class RetryContext(SerializableMixin):
    """Snapshot of state available inside a retry iteration."""

    attempt: int
    max_retries: int
    violations: List[GuardrailResult]
    original_input: Dict[str, Any]
    feedback: str = ""


class RetryWithFeedback:
    """Execute a callable in a guardrail retry loop.

    When a guardrail check returns failures whose action is ``RETRY``, the
    strategy formats the violation reasons into a feedback string and injects
    it into the parameters for the next attempt.

    Args:
        max_retries: Maximum number of retry attempts (not counting the
            initial execution).
        feedback_template: A string where ``{{reason}}`` is replaced with
            the concatenated violation reasons.
        backoff_factor: Multiplicative factor for inter-retry delay.
            The delay before attempt *n* is ``backoff_factor * n`` seconds.
            Set to ``0`` to disable sleeping entirely.
        feedback_key: Key used to inject the feedback string into *params*
            on retries.
        on_retry: Optional async callback invoked with the current
            :class:`RetryContext` before each retry execution.
    """

    def __init__(
        self,
        max_retries: int = 3,
        feedback_template: str = (
            "Your previous response was rejected: {{reason}}. "
            "Please fix and try again."
        ),
        backoff_factor: float = 1.0,
        feedback_key: str = "feedback",
        on_retry: Optional[Callable[["RetryContext"], Awaitable[None]]] = None,
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.max_retries = max_retries
        self.feedback_template = feedback_template
        self.backoff_factor = backoff_factor
        self.feedback_key = feedback_key
        self.on_retry = on_retry

    # ------------------------------------------------------------------
    # Feedback formatting
    # ------------------------------------------------------------------

    def format_feedback(self, violations: List[GuardrailResult]) -> str:
        """Format violation details into a feedback string.

        Each violation's ``reason`` is joined with ``"; "`` and substituted
        into the configured ``feedback_template``.

        Args:
            violations: List of failed :class:`GuardrailResult` instances.

        Returns:
            The rendered feedback string.
        """
        if not violations:
            return ""

        combined_reason = "; ".join(
            v.reason for v in violations if v.reason
        )
        return self.feedback_template.replace("{{reason}}", combined_reason)

    # ------------------------------------------------------------------
    # Core retry loop
    # ------------------------------------------------------------------

    async def execute_with_retry(
        self,
        execute_fn: Callable[..., Awaitable[Dict[str, Any]]],
        check_fn: Callable[[Dict[str, Any]], List[GuardrailResult]],
        params: Dict[str, Any],
        context: Any = None,
        execution_id: Optional[str] = None,
        flow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute *execute_fn* in a guardrail-driven retry loop.

        1. Call ``execute_fn(params, context)`` to obtain a result dict.
        2. Pass the result to ``check_fn`` which returns a list of
           :class:`GuardrailResult`.
        3. If all results passed, return the result immediately.
        4. Otherwise, format feedback from failures, inject it into *params*,
           and retry up to ``max_retries`` times.
        5. If retries are exhausted, return the last result along with a
           ``__retry_exhausted`` flag and the accumulated violations.

        Args:
            execute_fn: Async callable ``(params, context) -> dict``.
            check_fn: Callable that validates the result and returns a list
                of :class:`GuardrailResult`.
            params: Initial parameters forwarded to *execute_fn*.
            context: Optional context forwarded to *execute_fn*.

        Returns:
            The result dict from the last invocation of *execute_fn*.  On
            exhaustion an extra key ``__retry_exhausted`` is set to ``True``
            and ``__violations`` contains all accumulated failures.
        """
        log_extra = {"execution_id": execution_id, "flow_id": flow_id}
        all_violations: List[GuardrailResult] = []
        current_params = dict(params)  # shallow copy so we don't mutate caller

        for attempt in range(1 + self.max_retries):
            logger.info(
                "Executing attempt %d/%d (execution_id=%s, flow_id=%s)",
                attempt + 1,
                1 + self.max_retries,
                execution_id,
                flow_id,
                extra=log_extra,
            )
            result = await execute_fn(current_params, context)

            # --- guardrail check ---
            check_results = check_fn(result)
            failures = [r for r in check_results if not r.passed]

            if not failures:
                logger.info(
                    "Attempt %d passed all guardrails (execution_id=%s, flow_id=%s)",
                    attempt + 1,
                    execution_id,
                    flow_id,
                    extra=log_extra,
                )
                return result

            all_violations.extend(failures)
            failure_reasons = "; ".join(v.reason for v in failures if v.reason)

            logger.warning(
                "Attempt %d failed guardrails: %s (execution_id=%s, flow_id=%s)",
                attempt + 1,
                failure_reasons,
                execution_id,
                flow_id,
                extra=log_extra,
            )

            # If we've used all our retries, stop.
            if attempt >= self.max_retries:
                break

            # --- prepare retry ---
            feedback = self.format_feedback(failures)

            retry_ctx = RetryContext(
                attempt=attempt + 1,
                max_retries=self.max_retries,
                violations=list(all_violations),
                original_input=params,
                feedback=feedback,
            )

            if self.on_retry is not None:
                await self.on_retry(retry_ctx)

            # Backoff delay
            if self.backoff_factor > 0:
                delay = self.backoff_factor * (attempt + 1)
                logger.debug(
                    "Backing off %.1fs before retry (execution_id=%s, flow_id=%s)",
                    delay,
                    execution_id,
                    flow_id,
                    extra=log_extra,
                )
                await asyncio.sleep(delay)

            # Inject feedback for next attempt
            current_params = dict(params)
            current_params[self.feedback_key] = feedback

        # Retries exhausted -- return last result with metadata
        logger.error(
            "All %d retries exhausted, returning last result "
            "(execution_id=%s, flow_id=%s)",
            self.max_retries,
            execution_id,
            flow_id,
            extra=log_extra,
        )
        result["__retry_exhausted"] = True
        result["__violations"] = all_violations
        return result
