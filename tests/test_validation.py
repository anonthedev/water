import pytest
from pydantic import BaseModel
from water import create_task, Flow


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_validate_schema_passes_valid_data():
    task = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": p["input_data"]["value"] + 1},
        validate_schema=True,
    )

    flow = Flow(id="valid_flow", description="Valid")
    flow.then(task).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 6


@pytest.mark.asyncio
async def test_validate_schema_rejects_invalid_input():
    task = create_task(
        id="add_one",
        description="Add 1",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
        validate_schema=True,
    )

    flow = Flow(id="bad_input", description="Bad input")
    flow.then(task).register()

    with pytest.raises(ValueError, match="input validation failed"):
        await flow.run({"not_value": "hello"})


@pytest.mark.asyncio
async def test_validate_schema_rejects_invalid_output():
    task = create_task(
        id="bad_output",
        description="Bad output",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"wrong_key": "not_a_number"},
        validate_schema=True,
    )

    flow = Flow(id="bad_output_flow", description="Bad output")
    flow.then(task).register()

    with pytest.raises(ValueError, match="output validation failed"):
        await flow.run({"value": 5})


@pytest.mark.asyncio
async def test_validate_schema_off_by_default():
    """When validate_schema is False (default), invalid data passes through."""
    task = create_task(
        id="no_validate",
        description="No validate",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"anything": "goes"},
    )

    flow = Flow(id="no_val_flow", description="No validation")
    flow.then(task).register()

    result = await flow.run({"random": "data"})
    assert result["anything"] == "goes"


@pytest.mark.asyncio
async def test_validate_schema_input_type_coercion():
    """Pydantic coerces compatible types during validation (e.g., string '5' to int 5).
    Validation passes, but the raw data dict is still passed to the task unchanged."""
    task = create_task(
        id="coerce",
        description="Coerce",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": int(p["input_data"]["value"]) + 1},
        validate_schema=True,
    )

    flow = Flow(id="coerce_flow", description="Coerce")
    flow.then(task).register()

    # "5" passes Pydantic validation (coerced to int), task receives raw "5"
    result = await flow.run({"value": "5"})
    assert result["value"] == 6
