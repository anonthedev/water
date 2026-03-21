"""
Evaluation report.

Summarizes eval results with pass/fail counts, average scores,
and regression detection.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from water.eval.evaluators import EvalScore


@dataclass
class CaseResult:
    """Result of evaluating a single case."""
    case_index: int
    input_data: Dict[str, Any]
    expected: Dict[str, Any]
    actual: Dict[str, Any]
    scores: List[EvalScore]
    passed: bool
    avg_score: float
    error: Optional[str] = None


@dataclass
class EvalReport:
    """Summary of an evaluation suite run."""

    case_results: List[CaseResult] = field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    errored_cases: int = 0
    avg_score: float = 0.0
    baseline: Optional["EvalReport"] = None
    regressions: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary string."""
        lines = [
            f"Pass: {self.passed_cases}/{self.total_cases} | "
            f"Avg Score: {self.avg_score:.2f} | "
            f"Regressions: {len(self.regressions)}",
        ]
        if self.errored_cases:
            lines.append(f"Errors: {self.errored_cases}")
        return "\n".join(lines)

    def compare(self, baseline: "EvalReport") -> List[Dict[str, Any]]:
        """
        Compare this report against a baseline, detecting regressions.

        A regression is when a case that passed in the baseline now fails,
        or the score dropped significantly.
        """
        regressions = []
        for i, current in enumerate(self.case_results):
            if i >= len(baseline.case_results):
                break
            prev = baseline.case_results[i]
            if prev.passed and not current.passed:
                regressions.append({
                    "case_index": i,
                    "type": "pass_to_fail",
                    "baseline_score": prev.avg_score,
                    "current_score": current.avg_score,
                })
            elif current.avg_score < prev.avg_score - 0.1:
                regressions.append({
                    "case_index": i,
                    "type": "score_drop",
                    "baseline_score": prev.avg_score,
                    "current_score": current.avg_score,
                })
        self.regressions = regressions
        self.baseline = baseline
        return regressions

    def to_dict(self) -> Dict[str, Any]:
        """Serialize report for storage/export."""
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "errored_cases": self.errored_cases,
            "avg_score": self.avg_score,
            "regressions": self.regressions,
            "cases": [
                {
                    "index": cr.case_index,
                    "passed": cr.passed,
                    "avg_score": cr.avg_score,
                    "error": cr.error,
                    "scores": [
                        {"evaluator": s.evaluator, "passed": s.passed, "score": s.score, "reason": s.reason}
                        for s in cr.scores
                    ],
                }
                for cr in self.case_results
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Export report as JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
