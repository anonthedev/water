import pytest
from pydantic import BaseModel
from water import create_task, Flow


# --- Schemas ---

class InputA(BaseModel):
    text: str

class OutputA(BaseModel):
    text: str
    score: float

class InputB(BaseModel):
    text: str
    score: float

class OutputB(BaseModel):
    result: str

class InputC(BaseModel):
    text: str
    score: float
    extra: int

class OutputC(BaseModel):
    text: str


# --- Helpers ---

async def noop_execute(params, context):
    return params


def _make_task(tid, input_schema, output_schema):
    return create_task(
        id=tid,
        input_schema=input_schema,
        output_schema=output_schema,
        execute=noop_execute,
    )


# --- Tests ---

def test_valid_contracts():
    """Matching schemas produce no violations."""
    task_a = _make_task("a", InputA, OutputA)
    task_b = _make_task("b", InputB, OutputB)

    flow = Flow(id="valid")
    flow.then(task_a).then(task_b).register()

    violations = flow.validate_contracts()
    assert violations == []


def test_missing_field_violation():
    """Output missing a field that input expects produces a violation."""
    task_a = _make_task("a", InputA, OutputC)  # OutputC only has 'text'
    task_b = _make_task("b", InputB, OutputB)  # InputB needs 'text' and 'score'

    flow = Flow(id="missing")
    flow.then(task_a).then(task_b).register()

    violations = flow.validate_contracts()
    assert len(violations) == 1
    assert "score" in violations[0]["missing_fields"]


def test_validate_contracts_returns_details():
    """Violation has correct from_task, to_task, missing_fields."""
    task_a = _make_task("task_a", InputA, OutputC)  # output: text
    task_b = _make_task("task_b", InputC, OutputB)  # input: text, score, extra

    flow = Flow(id="details")
    flow.then(task_a).then(task_b).register()

    violations = flow.validate_contracts()
    assert len(violations) == 1
    v = violations[0]
    assert v["from_task"] == "task_a"
    assert v["to_task"] == "task_b"
    assert sorted(v["missing_fields"]) == ["extra", "score"]
    assert "message" in v


def test_strict_contracts_raises():
    """With strict_contracts=True, register raises ValueError."""
    task_a = _make_task("a", InputA, OutputC)
    task_b = _make_task("b", InputB, OutputB)

    flow = Flow(id="strict", strict_contracts=True)
    flow.then(task_a).then(task_b)

    with pytest.raises(ValueError, match="Data contract violations found"):
        flow.register()


def test_non_sequential_skipped():
    """Parallel/branch nodes don't cause false violations."""
    task_a = _make_task("a", InputA, OutputC)
    task_b = _make_task("b", InputB, OutputB)
    task_c = _make_task("c", InputA, OutputA)

    flow = Flow(id="parallel_test")
    flow.then(task_c).parallel([task_a, task_b]).register()

    # Only one sequential task (task_c), so no sequential pairs to check
    violations = flow.validate_contracts()
    assert violations == []


def test_partial_overlap_ok():
    """Output has extra fields beyond what input needs -- still valid."""
    task_a = _make_task("a", InputA, OutputA)  # output: text, score
    task_b = _make_task("b", InputA, OutputB)  # input: text (subset of output)

    flow = Flow(id="partial")
    flow.then(task_a).then(task_b).register()

    violations = flow.validate_contracts()
    assert violations == []
