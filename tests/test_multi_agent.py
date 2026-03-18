"""Tests for the multi-agent coordination module."""

import pytest
from pydantic import BaseModel
from typing import Dict, Any

from water.task import Task, create_task
from water.flow import Flow
from water.multi_agent import (
    AgentRole,
    SharedContext,
    AgentOrchestrator,
    create_agent_team,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class GenericInput(BaseModel):
    data: Dict[str, Any] = {}

class GenericOutput(BaseModel):
    data: Dict[str, Any] = {}


def _make_task(task_id: str, fn):
    """Create a simple Water task from a sync function."""
    return create_task(
        id=task_id,
        description=task_id,
        input_schema=GenericInput,
        output_schema=GenericOutput,
        execute=fn,
    )


# ---------------------------------------------------------------------------
# Sequential strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sequential_strategy():
    """Agents run in order, each receiving the previous agent's output."""
    planner = AgentRole(
        name="planner",
        description="Plans the work",
        task=_make_task("planner_task", lambda p, c: {
            "plan": "do X then Y",
            "value": p["input_data"].get("value", 0),
        }),
    )
    coder = AgentRole(
        name="coder",
        description="Writes the code",
        task=_make_task("coder_task", lambda p, c: {
            "code": "print('hello')",
            "plan": p["input_data"].get("plan", ""),
            "value": p["input_data"].get("value", 0) + 1,
        }),
    )
    reviewer = AgentRole(
        name="reviewer",
        description="Reviews the code",
        task=_make_task("reviewer_task", lambda p, c: {
            "approved": True,
            "value": p["input_data"].get("value", 0) + 1,
        }),
    )

    orch = AgentOrchestrator([planner, coder, reviewer], strategy="sequential")
    result = await orch.run({"value": 0})

    assert result["approved"] is True
    assert result["value"] == 2  # incremented by coder and reviewer
    assert len(orch.shared_context.get_history()) == 3


# ---------------------------------------------------------------------------
# Round-robin strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_round_robin_strategy():
    """Agents cycle through for max_rounds."""
    call_log = []

    def agent_fn(name):
        def fn(p, c):
            call_log.append(name)
            val = p["input_data"].get("counter", 0)
            return {"counter": val + 1}
        return fn

    agents = [
        AgentRole(name="a", description="A", task=_make_task("a_task", agent_fn("a"))),
        AgentRole(name="b", description="B", task=_make_task("b_task", agent_fn("b"))),
    ]

    orch = AgentOrchestrator(agents, strategy="round_robin")
    orch.max_rounds = 3
    result = await orch.run({"counter": 0}, max_rounds=3)

    # 3 rounds * 2 agents = 6 calls
    assert len(call_log) == 6
    assert result["counter"] == 6
    assert call_log == ["a", "b", "a", "b", "a", "b"]


@pytest.mark.asyncio
async def test_round_robin_early_stop():
    """Round-robin stops early when _done flag is set."""
    call_count = 0

    def stopping_agent(p, c):
        nonlocal call_count
        call_count += 1
        val = p["input_data"].get("counter", 0) + 1
        if val >= 3:
            return {"counter": val, "_done": True}
        return {"counter": val}

    agents = [
        AgentRole(name="worker", description="W", task=_make_task("w_task", stopping_agent)),
    ]

    orch = AgentOrchestrator(agents, strategy="round_robin")
    result = await orch.run({"counter": 0}, max_rounds=10)

    assert result["_done"] is True
    assert result["counter"] == 3
    assert call_count == 3


# ---------------------------------------------------------------------------
# Dynamic strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dynamic_strategy():
    """Agents hand off via _next_agent."""
    trail = []

    def make_fn(name, next_agent=None):
        def fn(p, c):
            trail.append(name)
            out = {"trail": trail[:], "value": p["input_data"].get("value", 0) + 1}
            if next_agent:
                out["_next_agent"] = next_agent
            return out
        return fn

    agents = [
        AgentRole(name="alpha", description="A", task=_make_task("alpha_task", make_fn("alpha", "beta"))),
        AgentRole(name="beta", description="B", task=_make_task("beta_task", make_fn("beta", "gamma"))),
        AgentRole(name="gamma", description="G", task=_make_task("gamma_task", make_fn("gamma"))),
    ]

    orch = AgentOrchestrator(agents, strategy="dynamic")
    result = await orch.run({"value": 0})

    assert trail == ["alpha", "beta", "gamma"]
    assert result["value"] == 3


@pytest.mark.asyncio
async def test_dynamic_strategy_stops():
    """Dynamic strategy stops when no _next_agent is returned."""
    trail = []

    def fn_no_next(p, c):
        trail.append("only")
        return {"result": "done"}

    agents = [
        AgentRole(name="only", description="O", task=_make_task("only_task", fn_no_next)),
        AgentRole(name="other", description="X", task=_make_task("other_task", lambda p, c: {})),
    ]

    orch = AgentOrchestrator(agents, strategy="dynamic")
    result = await orch.run({})

    assert trail == ["only"]
    assert result["result"] == "done"


# ---------------------------------------------------------------------------
# Shared context — state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shared_context_state():
    """Agents can read and write shared state."""
    ctx = SharedContext()

    def writer(p, c):
        # The agent reads _shared_context injected into its input
        ctx.set("written_by", "writer_agent")
        return {"status": "wrote"}

    def reader(p, c):
        val = ctx.get("written_by")
        return {"read_value": val}

    agents = [
        AgentRole(name="writer", description="Writes state",
                  task=_make_task("writer_task", writer)),
        AgentRole(name="reader", description="Reads state",
                  task=_make_task("reader_task", reader)),
    ]

    orch = AgentOrchestrator(agents, strategy="sequential")
    # Replace shared_context so our closures use the same one
    orch.shared_context = ctx
    result = await orch.run({})

    assert result["read_value"] == "writer_agent"
    assert ctx.get("written_by") == "writer_agent"


# ---------------------------------------------------------------------------
# Shared context — messages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shared_context_messages():
    """Agent-to-agent messaging works correctly."""
    ctx = SharedContext()

    def sender(p, c):
        ctx.add_message("sender", "receiver", "hello from sender")
        return {"sent": True}

    def receiver(p, c):
        msgs = p["input_data"].get("_agent_messages", [])
        return {"received": len(msgs), "content": msgs[0]["content"] if msgs else None}

    agents = [
        AgentRole(name="sender", description="Sends a message",
                  task=_make_task("sender_task", sender)),
        AgentRole(name="receiver", description="Receives messages",
                  task=_make_task("receiver_task", receiver)),
    ]

    orch = AgentOrchestrator(agents, strategy="sequential")
    orch.shared_context = ctx
    result = await orch.run({})

    assert result["received"] == 1
    assert result["content"] == "hello from sender"
    assert len(ctx.get_messages("receiver")) == 1
    assert len(ctx.get_messages("sender")) == 0
    assert len(ctx.get_messages()) == 1


# ---------------------------------------------------------------------------
# create_agent_team inside a Flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_team_in_flow():
    """create_agent_team produces a Task usable inside a Water Flow."""
    agents = [
        AgentRole(
            name="incrementer",
            description="Increments value",
            task=_make_task("inc_task", lambda p, c: {"value": p["input_data"].get("value", 0) + 10}),
        ),
    ]

    team_task = create_agent_team(
        agents=agents,
        strategy="sequential",
        input_schema=GenericInput,
        output_schema=GenericOutput,
    )

    flow = Flow(id="team_flow", description="Flow with agent team")
    flow.then(team_task).register()

    result = await flow.run({"value": 5})
    assert result["value"] == 15


# ---------------------------------------------------------------------------
# as_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_orchestrator_as_task():
    """as_task returns a usable Task."""
    agents = [
        AgentRole(
            name="doubler",
            description="Doubles value",
            task=_make_task("dbl_task", lambda p, c: {"value": p["input_data"].get("value", 0) * 2}),
        ),
    ]

    orch = AgentOrchestrator(agents, strategy="sequential")
    task = orch.as_task(input_schema=GenericInput, output_schema=GenericOutput)

    assert isinstance(task, Task)
    assert task.id == "agent_orchestrator"

    # Execute it directly via the flow engine
    flow = Flow(id="as_task_flow", description="Test as_task")
    flow.then(task).register()
    result = await flow.run({"value": 7})
    assert result["value"] == 14


# ---------------------------------------------------------------------------
# Delegation enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delegation():
    """can_delegate_to is respected; unauthorized delegation stops the chain."""
    trail = []

    def make_fn(name, next_name=None):
        def fn(p, c):
            trail.append(name)
            out = {"value": name}
            if next_name:
                out["_next_agent"] = next_name
            return out
        return fn

    agents = [
        AgentRole(
            name="alpha",
            description="A",
            task=_make_task("alpha_t", make_fn("alpha", "gamma")),
            can_delegate_to=["beta"],  # NOT gamma
        ),
        AgentRole(name="beta", description="B", task=_make_task("beta_t", make_fn("beta"))),
        AgentRole(name="gamma", description="G", task=_make_task("gamma_t", make_fn("gamma"))),
    ]

    orch = AgentOrchestrator(agents, strategy="dynamic")
    result = await orch.run({})

    # alpha tries to delegate to gamma, but can only delegate to beta => stops
    assert trail == ["alpha"]
    assert result["value"] == "alpha"
