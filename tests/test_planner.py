"""Tests for water.agents.planner -- Dynamic Task Injection."""

import asyncio
import json
import pytest

from pydantic import BaseModel
from water.agents.llm import MockProvider
from water.agents.planner import (
    PlanStep,
    ExecutionPlan,
    TaskRegistry,
    PlannerAgent,
    create_planner_task,
)
from water.core.task import Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _DummyInput(BaseModel):
    value: str = ""


class _DummyOutput(BaseModel):
    result: str = ""


def _make_task(name: str, fn=None, description: str = ""):
    """Build a minimal Task for testing."""
    async def default_fn(params, ctx):
        return {"result": f"{name}_done"}

    return Task(
        id=name,
        description=description or f"Task {name}",
        input_schema=_DummyInput,
        output_schema=_DummyOutput,
        execute=fn or default_fn,
    )


# ---------------------------------------------------------------------------
# TaskRegistry tests
# ---------------------------------------------------------------------------

class TestTaskRegistry:
    def test_register_and_get(self):
        reg = TaskRegistry()
        t = _make_task("alpha")
        reg.register("alpha", t, description="Alpha task")
        assert reg.get("alpha") is t

    def test_get_missing_returns_none(self):
        reg = TaskRegistry()
        assert reg.get("nope") is None

    def test_list_tasks(self):
        reg = TaskRegistry()
        reg.register("a", _make_task("a"), description="A desc")
        reg.register("b", _make_task("b"), description="B desc")
        listing = reg.list_tasks()
        assert len(listing) == 2
        names = {item["name"] for item in listing}
        assert names == {"a", "b"}

    def test_get_task_descriptions(self):
        reg = TaskRegistry()
        reg.register("fetch", _make_task("fetch"), description="Fetch data from API")
        reg.register("transform", _make_task("transform"), description="Transform raw data")
        desc = reg.get_task_descriptions()
        assert "- fetch: Fetch data from API" in desc
        assert "- transform: Transform raw data" in desc


# ---------------------------------------------------------------------------
# Data structure tests
# ---------------------------------------------------------------------------

class TestPlanStep:
    def test_creation_defaults(self):
        step = PlanStep(task_name="foo")
        assert step.task_name == "foo"
        assert step.input_mapping == {}
        assert step.description == ""

    def test_creation_with_values(self):
        step = PlanStep(task_name="bar", input_mapping={"x": "1"}, description="Do bar")
        assert step.input_mapping == {"x": "1"}
        assert step.description == "Do bar"


class TestExecutionPlan:
    def test_creation(self):
        plan = ExecutionPlan(
            steps=[PlanStep(task_name="a"), PlanStep(task_name="b")],
            goal="test goal",
            reasoning="because",
        )
        assert len(plan.steps) == 2
        assert plan.goal == "test goal"
        assert plan.reasoning == "because"


# ---------------------------------------------------------------------------
# PlannerAgent._parse_plan tests
# ---------------------------------------------------------------------------

class TestParsePlan:
    def _agent(self):
        return PlannerAgent(
            provider=MockProvider(),
            task_registry=TaskRegistry(),
        )

    def test_parse_valid_json(self):
        agent = self._agent()
        raw = json.dumps({
            "steps": [
                {"task": "fetch", "input": {"url": "https://example.com"}},
                {"task": "transform", "input": {}},
            ],
            "reasoning": "Fetch then transform",
        })
        plan = agent._parse_plan(raw)
        assert len(plan.steps) == 2
        assert plan.steps[0].task_name == "fetch"
        assert plan.steps[0].input_mapping == {"url": "https://example.com"}
        assert plan.reasoning == "Fetch then transform"

    def test_parse_code_block_json(self):
        agent = self._agent()
        raw = '```json\n{"steps": [{"task": "a", "input": {}}], "reasoning": "ok"}\n```'
        plan = agent._parse_plan(raw)
        assert len(plan.steps) == 1
        assert plan.steps[0].task_name == "a"

    def test_parse_invalid_json(self):
        agent = self._agent()
        plan = agent._parse_plan("not json at all")
        assert plan.steps == []
        assert "Failed to parse" in plan.reasoning


# ---------------------------------------------------------------------------
# Async tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPlannerAgentAsync:
    async def test_plan_calls_provider(self):
        mock_response = json.dumps({
            "steps": [{"task": "greet", "input": {"name": "World"}}],
            "reasoning": "Simple greeting",
        })
        provider = MockProvider(default_response=mock_response)
        reg = TaskRegistry()
        reg.register("greet", _make_task("greet"), description="Greet someone")
        agent = PlannerAgent(provider=provider, task_registry=reg)

        plan = await agent.plan("Say hello")
        assert len(plan.steps) == 1
        assert plan.steps[0].task_name == "greet"
        assert plan.goal == "Say hello"
        # Provider was called once
        assert len(provider.call_history) == 1

    async def test_execute_plan_with_registered_tasks(self):
        async def add_greeting(params, ctx):
            return {"greeting": f"Hello, {params.get('name', 'anon')}"}

        reg = TaskRegistry()
        reg.register("greet", _make_task("greet", fn=add_greeting))

        agent = PlannerAgent(provider=MockProvider(), task_registry=reg)
        plan = ExecutionPlan(
            steps=[PlanStep(task_name="greet", input_mapping={"name": "Alice"})],
        )
        result = await agent.execute_plan(plan)
        assert result["greeting"] == "Hello, Alice"
        assert len(agent.execution_history) == 1
        assert agent.execution_history[0]["status"] == "completed"

    async def test_execute_plan_skips_unknown_tasks(self):
        reg = TaskRegistry()
        agent = PlannerAgent(provider=MockProvider(), task_registry=reg)
        plan = ExecutionPlan(steps=[PlanStep(task_name="missing")])

        result = await agent.execute_plan(plan)
        assert len(agent.execution_history) == 1
        assert agent.execution_history[0]["status"] == "skipped"

    async def test_plan_and_execute(self):
        mock_response = json.dumps({
            "steps": [{"task": "double", "input": {}}],
            "reasoning": "double the number",
        })

        async def double_fn(params, ctx):
            return {"value": params.get("value", 0) * 2}

        provider = MockProvider(default_response=mock_response)
        reg = TaskRegistry()
        reg.register("double", _make_task("double", fn=double_fn))

        agent = PlannerAgent(provider=provider, task_registry=reg)
        result = await agent.plan_and_execute("double it", initial_data={"value": 5})
        assert result["value"] == 10


# ---------------------------------------------------------------------------
# create_planner_task factory test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreatePlannerTask:
    async def test_factory_returns_task(self):
        mock_response = json.dumps({
            "steps": [{"task": "noop", "input": {}}],
            "reasoning": "nothing to do",
        })
        provider = MockProvider(default_response=mock_response)
        reg = TaskRegistry()

        async def noop(params, ctx):
            return {"done": True}

        reg.register("noop", _make_task("noop", fn=noop))

        task = create_planner_task(
            id="my_planner",
            provider=provider,
            task_registry=reg,
        )
        assert isinstance(task, Task)
        assert task.id == "my_planner"

        result = await task.execute({"goal": "do nothing"}, None)
        assert "result" in result
        assert "plan" in result
        assert "history" in result
