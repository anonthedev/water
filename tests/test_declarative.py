import pytest
import json
from pydantic import BaseModel
from water import create_task, load_flow_from_dict, load_flow_from_json


# --- Schemas ---

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int

class ListInput(BaseModel):
    items: list
    value: int = 0

class ListOutput(BaseModel):
    items: list
    value: int = 0


# --- Helper tasks ---

def _make_add_one():
    return create_task(
        id="add_one",
        description="Add one",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1},
    )

def _make_double():
    return create_task(
        id="double",
        description="Double",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] * 2},
    )

def _make_triple():
    return create_task(
        id="triple",
        description="Triple",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda params, ctx: {"value": params["input_data"]["value"] * 3},
    )


# --- Tests ---

@pytest.mark.asyncio
async def test_load_sequential_from_dict():
    add_one = _make_add_one()
    double = _make_double()

    config = {
        "id": "seq_flow",
        "description": "Sequential add then double",
        "steps": [
            {"type": "sequential", "task": "add_one"},
            {"type": "sequential", "task": "double"},
        ],
    }

    flow = load_flow_from_dict(config, {"add_one": add_one, "double": double})
    assert flow.id == "seq_flow"
    assert flow._registered is True

    result = await flow.run({"value": 5})
    assert result["value"] == 12  # (5 + 1) * 2


@pytest.mark.asyncio
async def test_load_parallel_from_dict():
    double = _make_double()
    triple = _make_triple()

    config = {
        "id": "par_flow",
        "description": "Parallel double and triple",
        "steps": [
            {"type": "parallel", "tasks": ["double", "triple"]},
        ],
    }

    flow = load_flow_from_dict(config, {"double": double, "triple": triple})
    result = await flow.run({"value": 4})
    # Parallel returns keyed results by task id
    assert result["double"]["value"] == 8
    assert result["triple"]["value"] == 12


@pytest.mark.asyncio
async def test_load_branch_from_dict():
    double = _make_double()
    triple = _make_triple()

    def is_big(data):
        return data.get("value", 0) > 10

    def is_small(data):
        return data.get("value", 0) <= 10

    config = {
        "id": "branch_flow",
        "description": "Branch on value size",
        "steps": [
            {
                "type": "branch",
                "branches": [
                    {"condition": "is_big", "task": "double"},
                    {"condition": "is_small", "task": "triple"},
                ],
            },
        ],
    }

    registry = {
        "double": double,
        "triple": triple,
        "is_big": is_big,
        "is_small": is_small,
    }

    flow = load_flow_from_dict(config, registry)

    result = await flow.run({"value": 5})
    assert result["value"] == 15  # small -> triple -> 5 * 3

    # Rebuild for big value
    flow2 = load_flow_from_dict(config, registry)
    result2 = await flow2.run({"value": 20})
    assert result2["value"] == 40  # big -> double -> 20 * 2


@pytest.mark.asyncio
async def test_load_map_from_dict():
    process_item = create_task(
        id="process_item",
        description="Double the item value",
        input_schema=ListInput,
        output_schema=ListOutput,
        execute=lambda params, ctx: {
            "items": params["input_data"]["items"],
            "value": params["input_data"].get("value", 0) * 2,
        },
    )

    config = {
        "id": "map_flow",
        "description": "Map over items",
        "steps": [
            {"type": "map", "task": "process_item", "over": "items"},
        ],
    }

    flow = load_flow_from_dict(config, {"process_item": process_item})
    result = await flow.run({"items": [1, 2, 3], "value": 10})
    # Map returns {"results": [...]} with one entry per item
    assert "results" in result
    assert len(result["results"]) == 3


@pytest.mark.asyncio
async def test_load_dag_from_dict():
    add_one = _make_add_one()
    double = _make_double()

    config = {
        "id": "dag_flow",
        "description": "DAG with dependency",
        "steps": [
            {
                "type": "dag",
                "tasks": ["add_one", "double"],
                "dependencies": {"double": ["add_one"]},
            },
        ],
    }

    flow = load_flow_from_dict(config, {"add_one": add_one, "double": double})
    result = await flow.run({"value": 3})
    # DAG returns keyed results by task id
    assert result["add_one"]["value"] == 4
    assert result["double"]["value"] == 6


@pytest.mark.asyncio
async def test_load_from_json():
    add_one = _make_add_one()
    double = _make_double()

    config = {
        "id": "json_flow",
        "description": "Flow from JSON",
        "steps": [
            {"type": "sequential", "task": "add_one"},
            {"type": "sequential", "task": "double"},
        ],
    }

    json_str = json.dumps(config)
    flow = load_flow_from_json(json_str, {"add_one": add_one, "double": double})
    assert flow.id == "json_flow"
    result = await flow.run({"value": 10})
    assert result["value"] == 22  # (10 + 1) * 2


def test_unknown_task_raises():
    config = {
        "id": "bad_flow",
        "description": "References unknown task",
        "steps": [
            {"type": "sequential", "task": "nonexistent"},
        ],
    }

    with pytest.raises(ValueError, match="Unknown task 'nonexistent'"):
        load_flow_from_dict(config, {})


@pytest.mark.asyncio
async def test_flow_runs_after_load():
    """End-to-end test: load a multi-step flow from dict and verify execution."""
    add_one = _make_add_one()
    double = _make_double()
    triple = _make_triple()

    def always_true(data):
        return True

    config = {
        "id": "full_pipeline",
        "description": "A pipeline that adds one then conditionally doubles",
        "version": "1.0",
        "steps": [
            {"type": "sequential", "task": "add_one"},
            {
                "type": "branch",
                "branches": [
                    {"condition": "always_true", "task": "double"},
                ],
            },
            {"type": "sequential", "task": "triple"},
        ],
    }

    registry = {
        "add_one": add_one,
        "double": double,
        "triple": triple,
        "always_true": always_true,
    }

    flow = load_flow_from_dict(config, registry)
    assert flow.version == "1.0"

    result = await flow.run({"value": 4})
    # 4 -> add_one -> 5 -> branch(always_true -> double) -> 10 -> triple -> 30
    assert result["value"] == 30
