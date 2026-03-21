"""Tests for the evaluation framework."""

import pytest
from pydantic import BaseModel

from water.core.task import create_task
from water.core.flow import Flow
from water.eval.suite import EvalSuite, EvalCase
from water.eval.evaluators import ExactMatch, ContainsMatch, SemanticSimilarity, EvalScore
from water.eval.report import EvalReport, CaseResult


# --- Helpers ---

class SimpleInput(BaseModel):
    query: str = ""

class SimpleOutput(BaseModel):
    status: str = ""
    answer: str = ""

def _make_flow():
    async def process(params, ctx):
        data = params.get("input_data", params)
        return {"status": "success", "answer": f"answer to {data.get('query', '')}"}

    task = create_task(id="process", input_schema=SimpleInput, output_schema=SimpleOutput, execute=process)
    flow = Flow(id="test_eval_flow")
    flow.then(task).register()
    return flow


# --- Evaluator tests ---

@pytest.mark.asyncio
async def test_exact_match_pass():
    em = ExactMatch(key="status")
    score = await em.evaluate({"status": "success"}, {"status": "success"})
    assert score.passed
    assert score.score == 1.0


@pytest.mark.asyncio
async def test_exact_match_fail():
    em = ExactMatch(key="status")
    score = await em.evaluate({"status": "error"}, {"status": "success"})
    assert not score.passed
    assert score.score == 0.0


@pytest.mark.asyncio
async def test_exact_match_all_keys():
    em = ExactMatch()
    score = await em.evaluate({"a": 1, "b": 2}, {"a": 1, "b": 2})
    assert score.passed
    assert score.score == 1.0


@pytest.mark.asyncio
async def test_exact_match_partial():
    em = ExactMatch()
    score = await em.evaluate({"a": 1, "b": 3}, {"a": 1, "b": 2})
    assert not score.passed
    assert score.score == 0.5


@pytest.mark.asyncio
async def test_contains_match_substrings():
    cm = ContainsMatch(key="text", substrings=["hello", "world"])
    score = await cm.evaluate({"text": "hello world"}, {})
    assert score.passed


@pytest.mark.asyncio
async def test_contains_match_missing():
    cm = ContainsMatch(key="text", substrings=["hello", "missing"])
    score = await cm.evaluate({"text": "hello world"}, {})
    assert not score.passed
    assert score.score == 0.5


@pytest.mark.asyncio
async def test_contains_match_keys():
    cm = ContainsMatch(keys=["status", "answer"])
    score = await cm.evaluate({"status": "ok", "answer": "yes"}, {})
    assert score.passed


@pytest.mark.asyncio
async def test_semantic_similarity():
    ss = SemanticSimilarity(key="text", threshold=0.3)
    score = await ss.evaluate(
        {"text": "the quick brown fox"},
        {"text": "the fast brown fox"},
    )
    assert score.score > 0.0


@pytest.mark.asyncio
async def test_semantic_similarity_identical():
    ss = SemanticSimilarity(key="text")
    score = await ss.evaluate({"text": "hello world"}, {"text": "hello world"})
    assert score.passed
    assert score.score == 1.0


# --- Suite tests ---

@pytest.mark.asyncio
async def test_eval_suite_run():
    flow = _make_flow()
    suite = EvalSuite(
        flow=flow,
        evaluators=[ExactMatch(key="status")],
        cases=[
            EvalCase(input={"query": "test"}, expected={"status": "success"}),
            EvalCase(input={"query": "other"}, expected={"status": "success"}),
        ],
    )
    report = await suite.run()
    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.avg_score == 1.0


@pytest.mark.asyncio
async def test_eval_suite_failure():
    flow = _make_flow()
    suite = EvalSuite(
        flow=flow,
        evaluators=[ExactMatch(key="status")],
        cases=[
            EvalCase(input={"query": "test"}, expected={"status": "error"}),
        ],
    )
    report = await suite.run()
    assert report.failed_cases == 1


@pytest.mark.asyncio
async def test_eval_suite_error_handling():
    """Flow that raises an error should be counted as errored."""
    async def failing_fn(params, ctx):
        raise RuntimeError("boom")

    task = create_task(id="fail", input_schema=SimpleInput, output_schema=SimpleOutput, execute=failing_fn)
    flow = Flow(id="fail_flow")
    flow.then(task).register()

    suite = EvalSuite(
        flow=flow,
        evaluators=[ExactMatch(key="status")],
        cases=[EvalCase(input={"query": "x"}, expected={"status": "success"})],
    )
    report = await suite.run()
    assert report.errored_cases == 1


# --- Report tests ---

def test_report_summary():
    report = EvalReport(total_cases=10, passed_cases=8, failed_cases=2, avg_score=0.85)
    summary = report.summary()
    assert "8/10" in summary
    assert "0.85" in summary


def test_report_compare():
    baseline = EvalReport(
        total_cases=2,
        passed_cases=2,
        case_results=[
            CaseResult(case_index=0, input_data={}, expected={}, actual={}, scores=[], passed=True, avg_score=0.9),
            CaseResult(case_index=1, input_data={}, expected={}, actual={}, scores=[], passed=True, avg_score=0.8),
        ],
    )
    current = EvalReport(
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        case_results=[
            CaseResult(case_index=0, input_data={}, expected={}, actual={}, scores=[], passed=False, avg_score=0.3),
            CaseResult(case_index=1, input_data={}, expected={}, actual={}, scores=[], passed=True, avg_score=0.8),
        ],
    )
    regressions = current.compare(baseline)
    assert len(regressions) == 1
    assert regressions[0]["type"] == "pass_to_fail"


def test_report_to_json():
    report = EvalReport(total_cases=1, passed_cases=1, avg_score=1.0)
    j = report.to_json()
    assert '"total_cases": 1' in j
