"""
Dashboard Flow Example: Server-Integrated Dashboard

This example shows how to use FlowDashboard integrated with FlowServer.
The dashboard is served at /dashboard and provides a React SPA for
inspecting flow executions, sessions, and task runs.

Run with:
    uvicorn cookbook.dashboard_flow:app --host 0.0.0.0 --port 8000

Then visit http://localhost:8000/dashboard
"""

from pydantic import BaseModel
from water import Flow, create_task, FlowServer, InMemoryStorage, FlowDashboard


# --- Define a simple flow ---

class AddInput(BaseModel):
    value: int

class AddOutput(BaseModel):
    value: int


def add_one(payload, context):
    return {"value": payload["input_data"]["value"] + 1}


# Set up shared storage
storage = InMemoryStorage()

# Create task and flow
task = create_task(
    id="add_one",
    description="Adds one to the input value",
    input_schema=AddInput,
    output_schema=AddOutput,
    execute=add_one,
)
flow = Flow(id="addition_flow", description="Simple addition flow", storage=storage)
flow.then(task).register()

# Create the server with storage to enable the dashboard
server = FlowServer(flows=[flow], storage=storage)
app = server.get_app()

# Visit http://localhost:8000/dashboard to see the React dashboard
# API endpoints available:
#   GET /api/dashboard/stats      - Aggregate session statistics
#   GET /api/dashboard/sessions   - List sessions (supports ?flow_id=, ?limit=, ?offset=)
#   GET /api/dashboard/sessions/{execution_id} - Session detail with task runs
#   GET /api/dashboard/flows      - Flow summaries
