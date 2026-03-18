import pytest
from pydantic import BaseModel
from water import create_task, Flow


# --- Test Schemas ---

class SimpleInput(BaseModel):
    value: str

class SimpleOutput(BaseModel):
    result: str


# --- Stub Services ---

class FakeDatabaseClient:
    def query(self, sql: str) -> str:
        return f"db_result_for({sql})"


class FakeAPIClient:
    def get(self, url: str) -> str:
        return f"api_response_from({url})"


# --- Tests ---

@pytest.mark.asyncio
async def test_inject_service_available_in_task():
    """A task can access an injected service via context.get_service()."""
    db = FakeDatabaseClient()

    async def use_db_fn(params, context):
        client = context.get_service("db")
        return {"result": client.query(params["input_data"]["value"])}

    use_db = create_task(
        id="use_db",
        description="Uses the database service",
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
        execute=use_db_fn,
    )

    flow = (
        Flow(id="di_flow")
        .inject("db", db)
        .then(use_db)
        .register()
    )

    result = await flow.run({"value": "SELECT 1"})
    assert result["result"] == "db_result_for(SELECT 1)"


@pytest.mark.asyncio
async def test_multiple_services():
    """Multiple services can be injected and accessed independently."""
    db = FakeDatabaseClient()
    api = FakeAPIClient()

    async def use_both_fn(params, context):
        db_client = context.get_service("db")
        api_client = context.get_service("api")
        db_result = db_client.query("users")
        api_result = api_client.get("https://example.com")
        return {"result": f"{db_result} | {api_result}"}

    use_both = create_task(
        id="use_both",
        description="Uses both database and API services",
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
        execute=use_both_fn,
    )

    flow = (
        Flow(id="multi_svc_flow")
        .inject("db", db)
        .inject("api", api)
        .then(use_both)
        .register()
    )

    result = await flow.run({"value": "ignored"})
    assert result["result"] == "db_result_for(users) | api_response_from(https://example.com)"


def test_service_not_found():
    """context.get_service raises KeyError for an unknown service name."""
    from water.context import ExecutionContext

    ctx = ExecutionContext(flow_id="test")
    with pytest.raises(KeyError, match="Service 'missing' not found"):
        ctx.get_service("missing")


def test_has_service():
    """context.has_service returns the correct boolean."""
    from water.context import ExecutionContext

    ctx = ExecutionContext(flow_id="test")
    assert ctx.has_service("db") is False

    ctx.register_service("db", FakeDatabaseClient())
    assert ctx.has_service("db") is True


@pytest.mark.asyncio
async def test_no_services_by_default():
    """A flow works normally without any injected services."""

    plain_task = create_task(
        id="plain_task",
        description="Does not use services",
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
        execute=lambda params, context: {"result": params["input_data"]["value"].upper()},
    )

    flow = (
        Flow(id="no_svc_flow")
        .then(plain_task)
        .register()
    )

    result = await flow.run({"value": "hello"})
    assert result["result"] == "HELLO"
