import pytest
from pydantic import BaseModel
from water import create_task, Flow


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_subflow_as_task():
    """A registered flow can be used as a task in another flow."""
    add_one = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )
    double = create_task(
        id="double",
        description="Double",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] * 2},
    )

    # Sub-flow: add 1 then double
    sub = Flow(id="sub", description="Add and double")
    sub.then(add_one).then(double).register()

    # Outer flow uses sub-flow as a task
    add_ten = create_task(
        id="add_ten",
        description="Add 10",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 10},
    )

    outer = Flow(id="outer", description="Outer flow with sub-flow")
    outer.then(add_ten).then(sub).register()

    # (5 + 10) => sub-flow: (15 + 1) * 2 = 32
    result = await outer.run({"value": 5})
    assert result["value"] == 32

@pytest.mark.asyncio
async def test_subflow_explicit_as_task():
    """Test explicit .as_task() call."""
    task1 = create_task(
        id="t1",
        description="Add 5",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 5},
    )

    sub = Flow(id="sub_explicit", description="Sub")
    sub.then(task1).register()

    sub_task = sub.as_task(input_schema=NumberInput, output_schema=NumberOutput)
    assert sub_task.id == "subflow_sub_explicit"

    outer = Flow(id="outer_explicit", description="Outer")
    outer.then(sub_task).register()

    result = await outer.run({"value": 10})
    assert result["value"] == 15

@pytest.mark.asyncio
async def test_subflow_in_parallel():
    """Sub-flows can run in parallel."""
    add_one = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )
    double = create_task(
        id="double",
        description="Double",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] * 2},
    )

    sub1 = Flow(id="sub_add", description="Sub add")
    sub1.then(add_one).register()

    sub2 = Flow(id="sub_double", description="Sub double")
    sub2.then(double).register()

    outer = Flow(id="parallel_sub", description="Parallel sub-flows")
    outer.parallel([sub1, sub2]).register()

    result = await outer.run({"value": 10})
    assert result["subflow_sub_add"]["value"] == 11
    assert result["subflow_sub_double"]["value"] == 20

@pytest.mark.asyncio
async def test_subflow_in_branch():
    """Sub-flows can be used in branches."""
    add_task = create_task(
        id="add",
        description="Add 100",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 100},
    )
    sub = Flow(id="branch_sub", description="Branch sub-flow")
    sub.then(add_task).register()

    noop = create_task(
        id="noop",
        description="No op",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"]},
    )

    outer = Flow(id="branch_outer", description="Branch with sub-flow")
    outer.branch([
        (lambda d: d["value"] > 5, sub),
        (lambda d: d["value"] <= 5, noop),
    ]).register()

    result = await outer.run({"value": 10})
    assert result["value"] == 110

def test_subflow_must_be_registered():
    """Unregistered sub-flow cannot be converted to task."""
    sub = Flow(id="unreg", description="Unregistered")
    task = create_task(
        id="t",
        description="T",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )
    sub.then(task)  # Not registered

    with pytest.raises(RuntimeError, match="Sub-flow must be registered"):
        sub.as_task()
