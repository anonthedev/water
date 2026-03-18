import pytest
from pydantic import BaseModel
from water import create_task
from water.flow import Flow


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int

class ListInput(BaseModel):
    items: list

class ListOutput(BaseModel):
    results: list


# --- Conditional skip tests ---

@pytest.mark.asyncio
async def test_then_with_when_condition_true():
    task = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="when_true", description="Test when=True")
    flow.then(task, when=lambda d: d["value"] > 0).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6

@pytest.mark.asyncio
async def test_then_with_when_condition_false_skips():
    task = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="when_false", description="Test when=False")
    flow.then(task, when=lambda d: d["value"] > 100).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 5  # Skipped, data passes through

@pytest.mark.asyncio
async def test_then_without_when_always_executes():
    task = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
    )

    flow = Flow(id="no_when", description="No when")
    flow.then(task).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6

@pytest.mark.asyncio
async def test_conditional_skip_in_chain():
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
    add_ten = create_task(
        id="add_ten",
        description="Add 10",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 10},
    )

    flow = Flow(id="chain_skip", description="Chain with skip")
    flow.then(add_one) \
        .then(double, when=lambda d: d["value"] > 10) \
        .then(add_ten) \
        .register()

    # value=5 -> 6 -> skip double (6 <= 10) -> 16
    result = await flow.run({"value": 5})
    assert result["value"] == 16

    # value=15 -> 16 -> double (16 > 10) = 32 -> 42
    result = await flow.run({"value": 15})
    assert result["value"] == 42


# --- Map/fan-out tests ---

@pytest.mark.asyncio
async def test_map_basic():
    double = create_task(
        id="double_item",
        description="Double the item",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["items"] * 2},
    )

    flow = Flow(id="map_flow", description="Test map")
    flow.map(double, over="items").register()

    result = await flow.run({"items": [1, 2, 3]})
    assert result["results"] == [
        {"value": 2},
        {"value": 4},
        {"value": 6},
    ]

@pytest.mark.asyncio
async def test_map_empty_list():
    task = create_task(
        id="t",
        description="Task",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )

    flow = Flow(id="map_empty", description="Empty map")
    flow.map(task, over="items").register()

    result = await flow.run({"items": []})
    assert result["results"] == []

@pytest.mark.asyncio
async def test_map_preserves_other_data():
    """Each map invocation gets the full data dict with only the 'over' key changed."""
    def check_context(p, c):
        data = p["input_data"]
        return {"value": data["items"] + data["base"]}

    task = create_task(
        id="add_base",
        description="Add base to item",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=check_context,
    )

    flow = Flow(id="map_context", description="Map with context")
    flow.map(task, over="items").register()

    result = await flow.run({"items": [1, 2, 3], "base": 10})
    assert result["results"] == [
        {"value": 11},
        {"value": 12},
        {"value": 13},
    ]

@pytest.mark.asyncio
async def test_map_then_sequential():
    double = create_task(
        id="double_item",
        description="Double",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["items"] * 2},
    )

    count = create_task(
        id="count_results",
        description="Count results",
        input_schema=ListInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"count": len(p["input_data"]["results"])},
    )

    flow = Flow(id="map_then", description="Map then count")
    flow.map(double, over="items").then(count).register()

    result = await flow.run({"items": [1, 2, 3]})
    assert result["count"] == 3

def test_map_empty_over_key():
    task = create_task(
        id="t",
        description="T",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )
    flow = Flow(id="bad_map", description="Bad map")
    with pytest.raises(ValueError, match="Map 'over' key cannot be empty"):
        flow.map(task, over="")

@pytest.mark.asyncio
async def test_map_non_list_raises():
    task = create_task(
        id="t",
        description="T",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )
    flow = Flow(id="non_list_map", description="Non-list map")
    flow.map(task, over="items").register()

    with pytest.raises(ValueError, match="must reference a list"):
        await flow.run({"items": "not_a_list"})
