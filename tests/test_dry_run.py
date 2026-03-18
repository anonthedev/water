import pytest
from pydantic import BaseModel
from water import create_task, Flow


# --- Test Schemas ---

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int

class NameInput(BaseModel):
    name: str
    age: int


# --- Helper tasks ---

def _make_task(task_id="t1", input_schema=NumberInput, output_schema=NumberOutput):
    return create_task(
        id=task_id,
        description=f"Task {task_id}",
        input_schema=input_schema,
        output_schema=output_schema,
        execute=lambda params, context: {"value": 1},
    )


# --- Tests ---

@pytest.mark.asyncio
async def test_dry_run_valid_flow():
    """A simple valid flow passes dry run with valid=True."""
    task = _make_task("add")
    flow = Flow(id="valid_flow")
    flow.then(task).register()

    report = await flow.dry_run({"value": 42})

    assert report["flow_id"] == "valid_flow"
    assert report["valid"] is True
    assert len(report["nodes"]) == 1
    assert report["errors"] == []


@pytest.mark.asyncio
async def test_dry_run_reports_node_info():
    """Dry run reports correct node types and task ids."""
    t1 = _make_task("step1")
    t2 = _make_task("step2")
    flow = Flow(id="info_flow")
    flow.then(t1).then(t2).register()

    report = await flow.dry_run({"value": 1})

    assert len(report["nodes"]) == 2
    assert report["nodes"][0]["type"] == "sequential"
    assert report["nodes"][0]["task_id"] == "step1"
    assert report["nodes"][0]["index"] == 0
    assert report["nodes"][1]["type"] == "sequential"
    assert report["nodes"][1]["task_id"] == "step2"
    assert report["nodes"][1]["index"] == 1


@pytest.mark.asyncio
async def test_dry_run_validates_input_schema():
    """Invalid input data is reported in the dry run."""
    task = _make_task("strict", input_schema=NameInput)
    flow = Flow(id="schema_flow")
    flow.then(task).register()

    # Missing required fields: name and age
    report = await flow.dry_run({"value": 1})

    assert report["valid"] is False
    assert report["nodes"][0]["input_valid"] is False
    assert len(report["nodes"][0]["errors"]) > 0


@pytest.mark.asyncio
async def test_dry_run_branch_reports_conditions():
    """Branch nodes report which conditions match."""
    t_high = _make_task("high")
    t_low = _make_task("low")

    flow = Flow(id="branch_flow")
    flow.branch([
        (lambda data: data.get("value", 0) > 10, t_high),
        (lambda data: data.get("value", 0) <= 10, t_low),
    ]).register()

    report = await flow.dry_run({"value": 20})

    node = report["nodes"][0]
    assert node["type"] == "branch"
    assert len(node["branches"]) == 2
    assert node["branches"][0]["task_id"] == "high"
    assert node["branches"][0]["condition_matches"] is True
    assert node["branches"][1]["task_id"] == "low"
    assert node["branches"][1]["condition_matches"] is False


@pytest.mark.asyncio
async def test_dry_run_parallel_reports_tasks():
    """Parallel nodes list all task ids."""
    t1 = _make_task("p1")
    t2 = _make_task("p2")
    t3 = _make_task("p3")

    flow = Flow(id="parallel_flow")
    flow.parallel([t1, t2, t3]).register()

    report = await flow.dry_run({"value": 5})

    node = report["nodes"][0]
    assert node["type"] == "parallel"
    assert node["task_ids"] == ["p1", "p2", "p3"]


@pytest.mark.asyncio
async def test_dry_run_requires_registration():
    """Dry run raises RuntimeError if flow is not registered."""
    task = _make_task("unreg")
    flow = Flow(id="unreg_flow")
    flow.then(task)

    with pytest.raises(RuntimeError, match="Flow must be registered before running"):
        await flow.dry_run({"value": 1})


@pytest.mark.asyncio
async def test_dry_run_loop_reports_task():
    """Loop nodes report task id without simulating iterations."""
    task = _make_task("loop_task")
    flow = Flow(id="loop_flow")
    flow.loop(condition=lambda data: data.get("value", 0) < 10, task=task).register()

    report = await flow.dry_run({"value": 1})

    node = report["nodes"][0]
    assert node["type"] == "loop"
    assert node["task_id"] == "loop_task"
    assert node["input_valid"] is True


@pytest.mark.asyncio
async def test_dry_run_map_reports_over():
    """Map nodes report task id and over key."""
    task = _make_task("map_task")
    flow = Flow(id="map_flow")
    flow.map(task, over="items").register()

    report = await flow.dry_run({"value": 1})

    node = report["nodes"][0]
    assert node["type"] == "map"
    assert node["task_id"] == "map_task"
    assert node["over"] == "items"


@pytest.mark.asyncio
async def test_dry_run_dag_detects_cycles():
    """DAG nodes detect circular dependencies."""
    t1 = _make_task("a")
    t2 = _make_task("b")

    flow = Flow(id="dag_flow")
    flow.dag([t1, t2], dependencies={"a": ["b"], "b": ["a"]}).register()

    report = await flow.dry_run({"value": 1})

    node = report["nodes"][0]
    assert node["type"] == "dag"
    assert node["input_valid"] is False
    assert any("circular" in e.lower() for e in node["errors"])
