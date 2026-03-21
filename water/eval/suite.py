"""
Evaluation suite for Water flows.

Collection of test cases with expected outputs that can be run
against a flow to measure quality.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from water.eval.evaluators import Evaluator, EvalScore
from water.eval.report import EvalReport, CaseResult


@dataclass
class EvalCase:
    """Single input/expected-output pair with optional metadata."""
    input: Dict[str, Any]
    expected: Dict[str, Any]
    name: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvalSuite:
    """
    Collection of eval cases to run against a flow.

    Args:
        flow: A registered Water Flow to evaluate.
        evaluators: List of Evaluator instances for scoring.
        cases: List of EvalCase instances.
        name: Optional suite name.
    """

    def __init__(
        self,
        flow: Any,
        evaluators: List[Evaluator],
        cases: List[EvalCase],
        name: Optional[str] = None,
    ):
        self.flow = flow
        self.evaluators = evaluators
        self.cases = cases
        self.name = name or f"eval_{flow.id}"

    async def run(self) -> EvalReport:
        """
        Run all cases through the flow and evaluate results.

        Returns:
            EvalReport with aggregate metrics and per-case results.
        """
        report = EvalReport()
        report.total_cases = len(self.cases)

        for i, case in enumerate(self.cases):
            try:
                output = await self.flow.run(case.input)
            except Exception as e:
                report.errored_cases += 1
                report.case_results.append(CaseResult(
                    case_index=i,
                    input_data=case.input,
                    expected=case.expected,
                    actual={},
                    scores=[],
                    passed=False,
                    avg_score=0.0,
                    error=str(e),
                ))
                continue

            # Run all evaluators
            scores: List[EvalScore] = []
            for evaluator in self.evaluators:
                score = await evaluator.evaluate(output, case.expected, case.input)
                scores.append(score)

            all_passed = all(s.passed for s in scores)
            avg_score = sum(s.score for s in scores) / len(scores) if scores else 0.0

            if all_passed:
                report.passed_cases += 1
            else:
                report.failed_cases += 1

            report.case_results.append(CaseResult(
                case_index=i,
                input_data=case.input,
                expected=case.expected,
                actual=output,
                scores=scores,
                passed=all_passed,
                avg_score=avg_score,
            ))

        # Compute overall average score
        if report.case_results:
            report.avg_score = sum(
                cr.avg_score for cr in report.case_results
            ) / len(report.case_results)

        return report
