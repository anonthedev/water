"""
Evaluation strategies for scoring flow outputs.

Supports deterministic checks, LLM-as-judge, and semantic similarity.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalScore:
    """Result of a single evaluator on a single case."""
    evaluator: str
    passed: bool
    score: float  # 0.0 to 1.0
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class Evaluator(ABC):
    """Base class for evaluation strategies."""

    name: str = "evaluator"

    @abstractmethod
    async def evaluate(
        self,
        output: Dict[str, Any],
        expected: Dict[str, Any],
        input_data: Optional[Dict[str, Any]] = None,
    ) -> EvalScore:
        """
        Evaluate a flow output against expected results.

        Args:
            output: Actual output from the flow.
            expected: Expected output to compare against.
            input_data: Original input (for context).

        Returns:
            EvalScore with pass/fail and numeric score.
        """
        ...


class ExactMatch(Evaluator):
    """
    Deterministic equality check on specific keys.

    Args:
        key: Key in output/expected to compare. If None, compares all keys
            present in expected.
    """

    name = "exact_match"

    def __init__(self, key: Optional[str] = None):
        self.key = key

    async def evaluate(self, output, expected, input_data=None) -> EvalScore:
        if self.key:
            actual = output.get(self.key)
            exp = expected.get(self.key)
            passed = actual == exp
            return EvalScore(
                evaluator=self.name,
                passed=passed,
                score=1.0 if passed else 0.0,
                reason="" if passed else f"Key '{self.key}': expected {exp!r}, got {actual!r}",
            )

        # Compare all keys in expected
        mismatches = []
        for k, v in expected.items():
            if output.get(k) != v:
                mismatches.append(f"{k}: expected {v!r}, got {output.get(k)!r}")

        passed = len(mismatches) == 0
        match_count = len(expected) - len(mismatches)
        score = match_count / len(expected) if expected else 1.0
        return EvalScore(
            evaluator=self.name,
            passed=passed,
            score=score,
            reason="; ".join(mismatches) if mismatches else "",
        )


class ContainsMatch(Evaluator):
    """
    Check that output contains expected substrings or keys.

    Args:
        key: Key in output to check.
        substrings: List of substrings that must be present.
        keys: List of keys that must exist in output.
    """

    name = "contains_match"

    def __init__(
        self,
        key: Optional[str] = None,
        substrings: Optional[List[str]] = None,
        keys: Optional[List[str]] = None,
    ):
        self.key = key
        self.substrings = substrings or []
        self.keys = keys or []

    async def evaluate(self, output, expected, input_data=None) -> EvalScore:
        issues = []

        # Check substrings
        if self.substrings:
            text = str(output.get(self.key, output)) if self.key else str(output)
            for sub in self.substrings:
                if sub not in text:
                    issues.append(f"Missing substring: {sub!r}")

        # Check keys
        for k in self.keys:
            if k not in output:
                issues.append(f"Missing key: {k!r}")

        total = len(self.substrings) + len(self.keys)
        passed_count = total - len(issues)
        score = passed_count / total if total > 0 else 1.0
        return EvalScore(
            evaluator=self.name,
            passed=len(issues) == 0,
            score=score,
            reason="; ".join(issues) if issues else "",
        )


class LLMJudge(Evaluator):
    """
    Use an LLM to score output quality against a rubric.

    Args:
        provider: An LLMProvider instance.
        rubric: Scoring rubric or question for the judge.
        scale: Maximum score (default 5).
    """

    name = "llm_judge"

    def __init__(
        self,
        provider: Any = None,
        rubric: str = "Is the output accurate and complete?",
        scale: int = 5,
    ):
        self.provider = provider
        self.rubric = rubric
        self.scale = scale

    async def evaluate(self, output, expected, input_data=None) -> EvalScore:
        if self.provider is None:
            return EvalScore(
                evaluator=self.name,
                passed=False,
                score=0.0,
                reason="No LLM provider configured for judge",
            )

        prompt = (
            f"You are an evaluation judge. Score the following output on a scale of 0-{self.scale}.\n\n"
            f"Rubric: {self.rubric}\n\n"
            f"Input: {input_data}\n\n"
            f"Expected output: {expected}\n\n"
            f"Actual output: {output}\n\n"
            f"Respond with ONLY a number from 0 to {self.scale}."
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self.provider.complete(messages)
        response_text = response.get("text", "0").strip()

        try:
            raw_score = float(response_text)
            raw_score = max(0, min(self.scale, raw_score))
        except ValueError:
            raw_score = 0

        normalized = raw_score / self.scale
        return EvalScore(
            evaluator=self.name,
            passed=normalized >= 0.5,
            score=normalized,
            reason=f"LLM judge scored {raw_score}/{self.scale}",
            details={"raw_score": raw_score, "scale": self.scale},
        )


class SemanticSimilarity(Evaluator):
    """
    Embedding-based similarity scoring.

    Compares output text against expected text using a simple
    token overlap metric (Jaccard similarity) as a fallback.
    For production use, integrate with an embedding provider.

    Args:
        key: Key containing text to compare.
        threshold: Minimum similarity to pass (0.0-1.0).
    """

    name = "semantic_similarity"

    def __init__(self, key: Optional[str] = None, threshold: float = 0.5):
        self.key = key
        self.threshold = threshold

    async def evaluate(self, output, expected, input_data=None) -> EvalScore:
        out_text = str(output.get(self.key, output)) if self.key else str(output)
        exp_text = str(expected.get(self.key, expected)) if self.key else str(expected)

        score = self._jaccard_similarity(out_text, exp_text)
        passed = score >= self.threshold
        return EvalScore(
            evaluator=self.name,
            passed=passed,
            score=score,
            reason="" if passed else f"Similarity {score:.2f} below threshold {self.threshold}",
        )

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        """Token-level Jaccard similarity."""
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)
