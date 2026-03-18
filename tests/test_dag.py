import pytest
import asyncio
import time
from pydantic import BaseModel
from water import create_task, Flow


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_dag_no_dependencies():
    """All tasks run in parallel when no dependencies are specified."""
    order = []

    def make_task(name, delay=0):
        async def execute(p, c):
            if delay:
                await asyncio.sleep(delay)
            order.append(name)
            return {"value": 1}
        return create_task(
            id=name, description=name,
            input_schema=NumberInput, output_schema=NumberOutput,
            execute=execute,
        )

    a = make_task("a", 0.05)
    b = make_task("b", 0.01)

    flow = Flow(id="dag_no_deps", description="No deps")
    flow.dag([a, b]).register()

    result = await flow.run({"value": 0})
    assert "a" in result
    assert "b" in result
    # b should finish before a since it has shorter delay
    assert order.index("b") < order.index("a")


@pytest.mark.asyncio
async def test_dag_with_dependencies():
    """Tasks respect dependency ordering."""
    order = []

    def make_task(name):
        def execute(p, c):
            order.append(name)
            return {"value": 1}
        return create_task(
            id=name, description=name,
            input_schema=NumberInput, output_schema=NumberOutput,
            execute=execute,
        )

    a = make_task("a")
    b = make_task("b")
    c = make_task("c")

    # c depends on a and b; a and b have no deps
    flow = Flow(id="dag_deps", description="With deps")
    flow.dag([a, b, c], dependencies={"c": ["a", "b"]}).register()

    result = await flow.run({"value": 0})
    assert result["a"] == {"value": 1}
    assert result["b"] == {"value": 1}
    assert result["c"] == {"value": 1}
    # c must run after both a and b
    assert order.index("c") > order.index("a")
    assert order.index("c") > order.index("b")


@pytest.mark.asyncio
async def test_dag_linear_chain():
    """DAG can express a linear chain: a -> b -> c."""
    order = []

    def make_task(name):
        def execute(p, c):
            order.append(name)
            return {"value": 1}
        return create_task(
            id=name, description=name,
            input_schema=NumberInput, output_schema=NumberOutput,
            execute=execute,
        )

    a = make_task("a")
    b = make_task("b")
    c = make_task("c")

    flow = Flow(id="dag_chain", description="Chain")
    flow.dag([a, b, c], dependencies={"b": ["a"], "c": ["b"]}).register()

    result = await flow.run({"value": 0})
    assert order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_dag_diamond():
    """Diamond dependency: a -> b,c -> d."""
    order = []

    def make_task(name):
        def execute(p, c):
            order.append(name)
            return {"value": 1}
        return create_task(
            id=name, description=name,
            input_schema=NumberInput, output_schema=NumberOutput,
            execute=execute,
        )

    a = make_task("a")
    b = make_task("b")
    c = make_task("c")
    d = make_task("d")

    flow = Flow(id="dag_diamond", description="Diamond")
    flow.dag(
        [a, b, c, d],
        dependencies={"b": ["a"], "c": ["a"], "d": ["b", "c"]},
    ).register()

    result = await flow.run({"value": 0})
    assert order[0] == "a"
    assert order[-1] == "d"
    assert set(result.keys()) == {"a", "b", "c", "d"}


@pytest.mark.asyncio
async def test_dag_upstream_output_available():
    """Downstream tasks can access upstream outputs via data keys."""
    def task_a_exec(p, c):
        return {"value": 10}

    def task_b_exec(p, c):
        upstream = p["input_data"].get("_a_output", {})
        return {"value": upstream.get("value", 0) + 5}

    a = create_task(id="a", description="A", input_schema=NumberInput, output_schema=NumberOutput, execute=task_a_exec)
    b = create_task(id="b", description="B", input_schema=NumberInput, output_schema=NumberOutput, execute=task_b_exec)

    flow = Flow(id="dag_upstream", description="Upstream")
    flow.dag([a, b], dependencies={"b": ["a"]}).register()

    result = await flow.run({"value": 0})
    assert result["a"]["value"] == 10
    assert result["b"]["value"] == 15


def test_dag_empty_tasks():
    flow = Flow(id="dag_empty", description="Empty")
    with pytest.raises(ValueError, match="DAG task list cannot be empty"):
        flow.dag([])


@pytest.mark.asyncio
async def test_dag_unknown_dependency():
    a = create_task(id="a", description="A", input_schema=NumberInput, output_schema=NumberOutput, execute=lambda p, c: {"value": 1})

    flow = Flow(id="dag_bad", description="Bad dep")
    flow.dag([a], dependencies={"a": ["nonexistent"]}).register()

    with pytest.raises(ValueError, match="unknown task"):
        await flow.run({"value": 0})
