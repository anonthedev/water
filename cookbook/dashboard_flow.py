"""
Dashboard Flow Example: Inspecting Flow Execution State

This example shows how to use FlowDashboard to observe flow executions.
It runs a simple flow, then uses the dashboard to inspect the stored
sessions and task runs.
"""

import asyncio
from pydantic import BaseModel
from water import Flow, create_task, InMemoryStorage, FlowDashboard, FlowSession, FlowStatus


# --- Define a simple flow ---

class AddInput(BaseModel):
    value: int

class AddOutput(BaseModel):
    value: int


def add_one(payload, context):
    return {"value": payload["input_data"]["value"] + 1}


async def main():
    # Set up storage and dashboard
    storage = InMemoryStorage()
    dashboard = FlowDashboard(storage)

    # Create and run a flow
    task = create_task(
        id="add_one",
        description="Adds one to the input value",
        input_schema=AddInput,
        output_schema=AddOutput,
        execute=add_one,
    )
    flow = Flow(id="addition_flow", description="Simple addition flow")
    flow.then(task).register()

    # Simulate saving a completed session to storage
    session = FlowSession(
        flow_id="addition_flow",
        input_data={"value": 5},
        execution_id="exec_demo_001",
        status=FlowStatus.COMPLETED,
        result={"value": 6},
    )
    await storage.save_session(session)

    # Also save a failed session for contrast
    failed_session = FlowSession(
        flow_id="addition_flow",
        input_data={"value": -1},
        execution_id="exec_demo_002",
        status=FlowStatus.FAILED,
        error="Negative values not allowed",
    )
    await storage.save_session(failed_session)

    # --- Use the dashboard to inspect state ---

    # 1. Get aggregate stats
    stats = await dashboard.get_stats()
    print("=== Flow Stats ===")
    print(f"Total sessions: {stats['total_sessions']}")
    print(f"By status: {stats['by_status']}")
    print()

    # 2. Render the main dashboard HTML
    dashboard_html = await dashboard.get_dashboard_html()
    print("=== Dashboard HTML (first 500 chars) ===")
    print(dashboard_html[:500])
    print("...")
    print()

    # 3. Render a session detail page
    detail_html = await dashboard.get_session_detail_html("exec_demo_001")
    print("=== Session Detail HTML (first 500 chars) ===")
    print(detail_html[:500])
    print("...")


if __name__ == "__main__":
    asyncio.run(main())
