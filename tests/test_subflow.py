import pytest
import asyncio
from pydantic import BaseModel
from water.core.task import Task, create_task
from water.core.flow import Flow
from water.core.subflow import SubFlow, compose_flows


# --- Schemas ---

class TextInput(BaseModel):
    text: str

class TextOutput(BaseModel):
    text: str

class NumberInput(BaseModel):
    value: int

class NumberOutput(BaseModel):
    value: int

class MappedInput(BaseModel):
    source_text: str

class MappedOutput(BaseModel):
    result_text: str


# --- Helpers ---

async def uppercase_execute(params, context):
    data = params.get("input_data", params)
    return {"text": data["text"].upper()}

async def add_suffix_execute(params, context):
    data = params.get("input_data", params)
    return {"text": data["text"] + "_suffix"}

async def double_execute(params, context):
    data = params.get("input_data", params)
    return {"value": data["value"] * 2}

async def increment_execute(params, context):
    data = params.get("input_data", params)
    return {"value": data["value"] + 1}

async def passthrough_execute(params, context):
    data = params.get("input_data", params)
    return dict(data)


def _make_upper_task(tid="upper"):
    return create_task(
        id=tid,
        input_schema=TextInput,
        output_schema=TextOutput,
        execute=uppercase_execute,
    )

def _make_suffix_task(tid="suffix"):
    return create_task(
        id=tid,
        input_schema=TextInput,
        output_schema=TextOutput,
        execute=add_suffix_execute,
    )

def _make_double_task(tid="double"):
    return create_task(
        id=tid,
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=double_execute,
    )

def _make_increment_task(tid="increment"):
    return create_task(
        id=tid,
        input_schema=NumberInput,
        output_schema=NumberOutput,
        execute=increment_execute,
    )

def _make_inner_flow(flow_id="inner_flow"):
    """Create a registered inner flow for testing."""
    flow = Flow(id=flow_id)
    flow.then(_make_upper_task())
    flow.register()
    return flow

def _make_number_flow(flow_id="number_flow"):
    """Create a registered flow that doubles a value."""
    flow = Flow(id=flow_id)
    flow.then(_make_double_task())
    flow.register()
    return flow


# --- Tests ---

class TestSubFlowCreation:
    def test_subflow_creation_basic(self):
        """SubFlow can be created with a flow instance."""
        inner = _make_inner_flow()
        sub = SubFlow(inner)
        assert sub.flow is inner
        assert sub.input_mapping == {}
        assert sub.output_mapping == {}

    def test_subflow_creation_with_mappings(self):
        """SubFlow can be created with input/output mappings."""
        inner = _make_inner_flow()
        sub = SubFlow(
            inner,
            input_mapping={"text": "source_text"},
            output_mapping={"result_text": "text"},
        )
        assert sub.input_mapping == {"text": "source_text"}
        assert sub.output_mapping == {"result_text": "text"}

    def test_subflow_creation_with_custom_id_description(self):
        """SubFlow accepts custom id and description."""
        inner = _make_inner_flow()
        sub = SubFlow(inner, id="my_sub", description="My custom subflow")
        assert sub._id == "my_sub"
        assert sub._description == "My custom subflow"


class TestSubFlowAsTask:
    def test_as_task_returns_task(self):
        """SubFlow.as_task() returns a Task instance."""
        inner = _make_inner_flow()
        sub = SubFlow(inner)
        task = sub.as_task()
        assert isinstance(task, Task)

    def test_as_task_custom_id(self):
        """Task created from SubFlow uses the custom id."""
        inner = _make_inner_flow()
        sub = SubFlow(inner, id="custom_id")
        task = sub.as_task()
        assert task.id == "custom_id"

    def test_as_task_custom_description(self):
        """Task created from SubFlow uses the custom description."""
        inner = _make_inner_flow()
        sub = SubFlow(inner, description="Custom description")
        task = sub.as_task()
        assert task.description == "Custom description"

    def test_as_task_default_description(self):
        """Task uses flow id in default description."""
        inner = _make_inner_flow("my_flow")
        sub = SubFlow(inner)
        task = sub.as_task()
        assert "my_flow" in task.description


class TestSubFlowExecution:
    @pytest.mark.asyncio
    async def test_subflow_runs_inner_flow(self):
        """SubFlow execution runs the inner flow."""
        inner = _make_inner_flow()
        sub = SubFlow(inner)
        task = sub.as_task()
        # Engine wraps data as {"input_data": data}
        result = await task.execute({"input_data": {"text": "hello"}}, None)
        assert result["text"] == "HELLO"

    @pytest.mark.asyncio
    async def test_subflow_with_input_mapping(self):
        """SubFlow applies input mapping before running inner flow."""
        inner = _make_inner_flow()
        sub = SubFlow(inner, input_mapping={"text": "source_text"})
        task = sub.as_task()
        result = await task.execute({"input_data": {"source_text": "hello"}}, None)
        assert result["text"] == "HELLO"

    @pytest.mark.asyncio
    async def test_subflow_with_output_mapping(self):
        """SubFlow applies output mapping to inner flow results."""
        inner = _make_inner_flow()
        sub = SubFlow(inner, output_mapping={"result_text": "text"})
        task = sub.as_task()
        result = await task.execute({"input_data": {"text": "hello"}}, None)
        assert result == {"result_text": "HELLO"}

    @pytest.mark.asyncio
    async def test_subflow_with_both_mappings(self):
        """SubFlow applies both input and output mappings."""
        inner = _make_inner_flow()
        sub = SubFlow(
            inner,
            input_mapping={"text": "source_text"},
            output_mapping={"result_text": "text"},
        )
        task = sub.as_task()
        result = await task.execute({"input_data": {"source_text": "hello"}}, None)
        assert result == {"result_text": "HELLO"}

    @pytest.mark.asyncio
    async def test_subflow_empty_mappings(self):
        """SubFlow with empty mappings passes data through directly."""
        inner = _make_inner_flow()
        sub = SubFlow(inner, input_mapping={}, output_mapping={})
        task = sub.as_task()
        result = await task.execute({"input_data": {"text": "hello"}}, None)
        assert result["text"] == "HELLO"


class TestSubFlowSchemaInference:
    def test_infers_input_schema_from_first_task(self):
        """SubFlow infers input schema from the inner flow's first task."""
        inner = _make_inner_flow()
        sub = SubFlow(inner)
        task = sub.as_task()
        assert task.input_schema is TextInput

    def test_infers_output_schema_from_last_task(self):
        """SubFlow infers output schema from the inner flow's last task."""
        inner = _make_inner_flow()
        sub = SubFlow(inner)
        task = sub.as_task()
        assert task.output_schema is TextOutput

    def test_fallback_schema_when_no_tasks(self):
        """SubFlow uses fallback schema when flow has no tasks to inspect."""
        flow = Flow(id="empty")
        # Don't add tasks -- schema inference should use fallback
        sub = SubFlow(flow)
        task = sub.as_task()
        assert issubclass(task.input_schema, BaseModel)
        assert issubclass(task.output_schema, BaseModel)


class TestSubFlowInChain:
    @pytest.mark.asyncio
    async def test_subflow_in_then_chain(self):
        """SubFlow task can be used in a .then() chain."""
        inner = _make_inner_flow()
        sub = SubFlow(inner)

        outer = Flow(id="outer")
        outer.then(_make_suffix_task()).then(sub.as_task())
        outer.register()

        result = await outer.run({"text": "hello"})
        # suffix adds "_suffix", then inner uppercases
        assert result["text"] == "HELLO_SUFFIX"

    @pytest.mark.asyncio
    async def test_subflow_number_flow_in_chain(self):
        """A number-based SubFlow can be chained."""
        inner = _make_number_flow()
        sub = SubFlow(inner)

        outer = Flow(id="outer_num")
        outer.then(_make_increment_task()).then(sub.as_task())
        outer.register()

        result = await outer.run({"value": 5})
        # increment: 5+1=6, then double: 6*2=12
        assert result["value"] == 12


class TestComposeFlows:
    @pytest.mark.asyncio
    async def test_compose_two_flows(self):
        """compose_flows combines two flows sequentially."""
        flow_a = _make_inner_flow("flow_a")       # uppercase
        flow_b = _make_inner_flow("flow_b")        # uppercase again (no-op on already upper)

        composed = compose_flows(flow_a, flow_b, id="composed_ab")
        composed.register()

        result = await composed.run({"text": "hello"})
        assert result["text"] == "HELLO"

    @pytest.mark.asyncio
    async def test_compose_number_flows(self):
        """compose_flows combines number flows."""
        flow_a = _make_number_flow("num_a")   # double
        flow_b = _make_number_flow("num_b")   # double again

        composed = compose_flows(flow_a, flow_b, id="composed_num")
        composed.register()

        result = await composed.run({"value": 3})
        # 3*2=6, 6*2=12
        assert result["value"] == 12

    def test_compose_flows_custom_id(self):
        """compose_flows uses custom id."""
        flow_a = _make_inner_flow("a")
        flow_b = _make_inner_flow("b")
        composed = compose_flows(flow_a, flow_b, id="my_composed")
        assert composed.id == "my_composed"

    def test_compose_flows_default_id(self):
        """compose_flows generates id from child flow ids."""
        flow_a = _make_inner_flow("alpha")
        flow_b = _make_inner_flow("beta")
        composed = compose_flows(flow_a, flow_b)
        assert "alpha" in composed.id
        assert "beta" in composed.id

    def test_compose_flows_custom_description(self):
        """compose_flows uses custom description."""
        flow_a = _make_inner_flow("a2")
        composed = compose_flows(flow_a, description="My composed flow")
        assert composed.description == "My composed flow"


class TestNestedSubFlow:
    @pytest.mark.asyncio
    async def test_nested_subflow(self):
        """A SubFlow can contain another SubFlow (nested composition)."""
        # Inner-most flow: uppercase
        inner = _make_inner_flow("innermost")

        # Middle flow: wraps inner as a subflow
        middle = Flow(id="middle")
        middle.then(SubFlow(inner).as_task())
        middle.register()

        # Outer flow: wraps middle as a subflow
        outer = Flow(id="outer_nested")
        outer.then(SubFlow(middle).as_task())
        outer.register()

        result = await outer.run({"text": "nested"})
        assert result["text"] == "NESTED"
