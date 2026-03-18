"""
Multi-Agent Coordination Cookbook
=================================

Demonstrates three collaboration patterns with Water's multi-agent module:

1. Sequential planner-coder-reviewer pipeline
2. Round-robin debate between two agents
3. Dynamic delegation among specialist agents
4. Embedding an agent team inside a Water Flow
"""

import asyncio
from typing import Dict, Any

from pydantic import BaseModel

from water.core import create_task, Flow
from water.agents.multi import (
    AgentRole,
    AgentOrchestrator,
    SharedContext,
    create_agent_team,
)


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

class TeamInput(BaseModel):
    data: Dict[str, Any] = {}

class TeamOutput(BaseModel):
    data: Dict[str, Any] = {}


# ===================================================================
# Example 1 — Sequential: Planner → Coder → Reviewer
# ===================================================================

def planner_execute(params, context):
    """The planner breaks the request into steps."""
    request = params["input_data"].get("request", "build a hello world app")
    return {
        "request": request,
        "plan": [
            "Step 1: Create main.py",
            "Step 2: Write hello world function",
            "Step 3: Add tests",
        ],
    }

def coder_execute(params, context):
    """The coder implements the plan."""
    plan = params["input_data"].get("plan", [])
    return {
        "plan": plan,
        "code": "def hello():\n    return 'Hello, World!'",
        "tests": "def test_hello():\n    assert hello() == 'Hello, World!'",
    }

def reviewer_execute(params, context):
    """The reviewer checks the code."""
    code = params["input_data"].get("code", "")
    return {
        "code": code,
        "approved": True,
        "feedback": "Looks good — clean and simple.",
    }


async def example_sequential():
    print("=" * 60)
    print("Example 1: Sequential Planner-Coder-Reviewer")
    print("=" * 60)

    planner = AgentRole(
        name="planner",
        description="Breaks a request into an actionable plan",
        task=create_task(
            id="planner", description="Plan",
            input_schema=TeamInput, output_schema=TeamOutput,
            execute=planner_execute,
        ),
    )
    coder = AgentRole(
        name="coder",
        description="Implements the plan in code",
        task=create_task(
            id="coder", description="Code",
            input_schema=TeamInput, output_schema=TeamOutput,
            execute=coder_execute,
        ),
    )
    reviewer = AgentRole(
        name="reviewer",
        description="Reviews the code for correctness",
        task=create_task(
            id="reviewer", description="Review",
            input_schema=TeamInput, output_schema=TeamOutput,
            execute=reviewer_execute,
        ),
    )

    orch = AgentOrchestrator([planner, coder, reviewer], strategy="sequential")
    result = await orch.run({"request": "Build a calculator app"})

    print(f"  Approved : {result.get('approved')}")
    print(f"  Feedback : {result.get('feedback')}")
    print(f"  History  : {len(orch.shared_context.get_history())} steps")
    print()
    return result


# ===================================================================
# Example 2 — Round-Robin: Debate between two agents
# ===================================================================

def debater_a_execute(params, context):
    """Debater A argues in favour."""
    turn = params["input_data"].get("turn", 0) + 1
    if turn >= 4:
        return {"turn": turn, "position": "for", "argument": "Final rebuttal.", "_done": True}
    return {"turn": turn, "position": "for", "argument": f"Argument {turn} in favour."}

def debater_b_execute(params, context):
    """Debater B argues against."""
    turn = params["input_data"].get("turn", 0) + 1
    if turn >= 4:
        return {"turn": turn, "position": "against", "argument": "Final counter.", "_done": True}
    return {"turn": turn, "position": "against", "argument": f"Argument {turn} against."}


async def example_round_robin():
    print("=" * 60)
    print("Example 2: Round-Robin Debate")
    print("=" * 60)

    agents = [
        AgentRole(
            name="debater_a",
            description="Argues in favour",
            task=create_task(
                id="debater_a", description="For",
                input_schema=TeamInput, output_schema=TeamOutput,
                execute=debater_a_execute,
            ),
        ),
        AgentRole(
            name="debater_b",
            description="Argues against",
            task=create_task(
                id="debater_b", description="Against",
                input_schema=TeamInput, output_schema=TeamOutput,
                execute=debater_b_execute,
            ),
        ),
    ]

    orch = AgentOrchestrator(agents, strategy="round_robin")
    orch.max_rounds = 5
    result = await orch.run({"turn": 0})

    print(f"  Final turn   : {result.get('turn')}")
    print(f"  Stopped early: {result.get('_done', False)}")
    print(f"  History      : {len(orch.shared_context.get_history())} exchanges")
    print()
    return result


# ===================================================================
# Example 3 — Dynamic: Specialist delegation
# ===================================================================

def router_execute(params, context):
    """Routes the request to the right specialist."""
    request = params["input_data"].get("request", "")
    if "database" in request.lower():
        return {"request": request, "routed_to": "db_specialist", "_next_agent": "db_specialist"}
    elif "frontend" in request.lower():
        return {"request": request, "routed_to": "ui_specialist", "_next_agent": "ui_specialist"}
    return {"request": request, "routed_to": "none", "answer": "I can handle this myself."}

def db_specialist_execute(params, context):
    """Handles database-related tasks."""
    return {"answer": "Use an index on the query column for faster lookups.", "specialist": "db"}

def ui_specialist_execute(params, context):
    """Handles frontend tasks."""
    return {"answer": "Use a responsive grid layout with CSS flexbox.", "specialist": "ui"}


async def example_dynamic():
    print("=" * 60)
    print("Example 3: Dynamic Delegation")
    print("=" * 60)

    agents = [
        AgentRole(
            name="router",
            description="Routes requests to specialists",
            task=create_task(
                id="router", description="Route",
                input_schema=TeamInput, output_schema=TeamOutput,
                execute=router_execute,
            ),
            can_delegate_to=["db_specialist", "ui_specialist"],
        ),
        AgentRole(
            name="db_specialist",
            description="Database expert",
            task=create_task(
                id="db_specialist", description="DB",
                input_schema=TeamInput, output_schema=TeamOutput,
                execute=db_specialist_execute,
            ),
        ),
        AgentRole(
            name="ui_specialist",
            description="Frontend expert",
            task=create_task(
                id="ui_specialist", description="UI",
                input_schema=TeamInput, output_schema=TeamOutput,
                execute=ui_specialist_execute,
            ),
        ),
    ]

    orch = AgentOrchestrator(agents, strategy="dynamic")

    # Route to DB specialist
    result = await orch.run({"request": "Optimise my database query"})
    print(f"  DB request  -> specialist={result.get('specialist')}, answer={result.get('answer')}")

    # Route to UI specialist (need a fresh orchestrator for clean state)
    orch2 = AgentOrchestrator(agents, strategy="dynamic")
    result2 = await orch2.run({"request": "Build a frontend dashboard"})
    print(f"  UI request  -> specialist={result2.get('specialist')}, answer={result2.get('answer')}")
    print()
    return result, result2


# ===================================================================
# Example 4 — Agent team inside a Water Flow
# ===================================================================

def preprocess_execute(params, context):
    """Pre-processing step before the agent team."""
    raw = params["input_data"].get("raw_text", "")
    return {"text": raw.strip().lower(), "raw_text": raw}

def postprocess_execute(params, context):
    """Post-processing step after the agent team."""
    return {"final_summary": params["input_data"].get("summary", "N/A"), "done": True}

def summariser_execute(params, context):
    """Agent that summarises text."""
    text = params["input_data"].get("text", "")
    return {"summary": f"Summary of: {text[:50]}...", "text": text}


async def example_flow_integration():
    print("=" * 60)
    print("Example 4: Agent Team inside a Water Flow")
    print("=" * 60)

    preprocess = create_task(
        id="preprocess", description="Clean input",
        input_schema=TeamInput, output_schema=TeamOutput,
        execute=preprocess_execute,
    )

    team_task = create_agent_team(
        agents=[
            AgentRole(
                name="summariser",
                description="Summarises text",
                task=create_task(
                    id="summariser", description="Summarise",
                    input_schema=TeamInput, output_schema=TeamOutput,
                    execute=summariser_execute,
                ),
            ),
        ],
        strategy="sequential",
        input_schema=TeamInput,
        output_schema=TeamOutput,
    )

    postprocess = create_task(
        id="postprocess", description="Wrap up",
        input_schema=TeamInput, output_schema=TeamOutput,
        execute=postprocess_execute,
    )

    flow = Flow(id="multi_agent_pipeline", description="Full pipeline with agent team")
    flow.then(preprocess).then(team_task).then(postprocess).register()

    result = await flow.run({"raw_text": "  The Water Framework Makes Orchestration Easy!  "})
    print(f"  Result: {result}")
    print()
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    await example_sequential()
    await example_round_robin()
    await example_dynamic()
    await example_flow_integration()


if __name__ == "__main__":
    asyncio.run(main())
