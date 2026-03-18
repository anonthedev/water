import pytest
from pydantic import BaseModel
from water import create_task, Flow, InMemoryStorage


class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int


def test_flow_version_stored_in_metadata():
    flow = Flow(id="v_flow", description="Versioned", version="1.0.0")
    assert flow.version == "1.0.0"

def test_flow_version_defaults_to_none():
    flow = Flow(id="no_v", description="No version")
    assert flow.version is None

@pytest.mark.asyncio
async def test_version_in_metadata_after_run():
    task = create_task(
        id="t1",
        description="T",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )
    flow = Flow(id="v_run", description="Versioned run", version="2.1.0")
    flow.then(task).register()

    await flow.run({"value": 0})
    assert flow.metadata.get("_flow_version") == "2.1.0"

@pytest.mark.asyncio
async def test_version_stored_in_session():
    storage = InMemoryStorage()
    task = create_task(
        id="t1",
        description="T",
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=lambda p, c: {"value": 1},
    )
    flow = Flow(id="v_session", description="V", version="3.0.0", storage=storage)
    flow.then(task).register()

    await flow.run({"value": 0})

    sessions = await storage.list_sessions()
    assert len(sessions) == 1
