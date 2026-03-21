"""
A2A Protocol Flow Example: Agent-to-Agent Communication

This example demonstrates Water's Agent-to-Agent (A2A) protocol support,
based on Google's A2A specification. It shows:
  - Creating an A2AServer to expose a flow as an A2A-compliant agent
  - Building AgentCards with skills for agent discovery
  - Using A2AClient to send tasks to a remote agent (simulated locally)
  - The full task lifecycle: submit, poll, cancel

NOTE: This example runs entirely in-process by wiring the client directly
      to the server's handle_request method, so no real HTTP server is needed.
"""

import asyncio
import json
from typing import Any, Dict

from pydantic import BaseModel

from water.core import Flow, create_task
from water.integrations.a2a import (
    A2AServer,
    A2AClient,
    A2ATask,
    A2AMessage,
    AgentCard,
    AgentSkill,
    MessagePart,
    TaskState,
)


# ---------------------------------------------------------------------------
# Helper: a simple flow to back our A2A agent
# ---------------------------------------------------------------------------

class QueryInput(BaseModel):
    prompt: str = ""

class QueryOutput(BaseModel):
    answer: str = ""
    confidence: float = 0.0


def answer_query(params: Dict[str, Any], context) -> Dict[str, Any]:
    data = params["input_data"]
    prompt = data.get("prompt", "")
    return {
        "answer": f"The answer to '{prompt}' is 42.",
        "confidence": 0.95,
    }


qa_task = create_task(
    id="qa_responder",
    description="Answer a user query",
    input_schema=QueryInput,
    output_schema=QueryOutput,
    execute=answer_query,
)


def build_qa_flow() -> Flow:
    """Build and register a simple Q&A flow."""
    flow = Flow(id="qa_flow", description="Question-answering flow")
    flow.then(qa_task).register()
    return flow


# ---------------------------------------------------------------------------
# Example 1: A2AServer setup and AgentCard creation
# ---------------------------------------------------------------------------

async def example_server_and_agent_card():
    """Create an A2A server, inspect its agent card, and handle a task."""
    print("=== Example 1: A2AServer & AgentCard ===\n")

    flow = build_qa_flow()

    # Create the server with skills
    server = A2AServer(
        flow=flow,
        name="QA Agent",
        description="Answers general knowledge questions",
        url="http://localhost:8000",
        skills=[
            AgentSkill(
                id="general_qa",
                name="General Q&A",
                description="Answer general knowledge questions",
                tags=["qa", "knowledge"],
                examples=["What is the capital of France?"],
            ),
            AgentSkill(
                id="math",
                name="Math Helper",
                description="Solve basic math problems",
                tags=["math", "calculation"],
                examples=["What is 2 + 2?"],
            ),
        ],
        version="1.0.0",
    )

    # Inspect the agent card (served at /.well-known/agent.json)
    card = server.get_agent_card()
    print(f"Agent:       {card['name']}")
    print(f"Description: {card['description']}")
    print(f"URL:         {card['url']}")
    print(f"Skills:      {[s['name'] for s in card['skills']]}")
    print(f"Protocols:   {card['protocols']}")
    print()

    # Send a task via JSON-RPC
    request = {
        "jsonrpc": "2.0",
        "id": "req-001",
        "method": "tasks/send",
        "params": {
            "id": "task-001",
            "messages": [
                {
                    "role": "user",
                    "parts": [{"kind": "text", "content": "What is Water?"}],
                }
            ],
        },
    }

    response = await server.handle_request(request)
    result = response["result"]
    print(f"Task ID:    {result['id']}")
    print(f"Task State: {result['state']}")
    print(f"Result:     {result.get('result', {})}")
    print()


# ---------------------------------------------------------------------------
# Example 2: Simulated A2AClient usage (in-process)
# ---------------------------------------------------------------------------

async def example_client_usage():
    """Simulate A2AClient sending tasks to a server (in-process wiring)."""
    print("=== Example 2: A2AClient Task Submission ===\n")

    flow = build_qa_flow()
    server = A2AServer(
        flow=flow,
        name="QA Agent",
        description="Answers questions",
        url="http://localhost:8000",
    )

    # Simulate the client by directly calling server.handle_request
    # (In production, A2AClient would make real HTTP calls.)

    # Send a text message
    text_msg = A2AMessage(
        role="user",
        parts=[MessagePart.text("Explain quantum computing")],
    )
    request = {
        "jsonrpc": "2.0",
        "id": "req-002",
        "method": "tasks/send",
        "params": {
            "id": "task-002",
            "messages": [text_msg.to_dict()],
        },
    }
    response = await server.handle_request(request)
    task_result = response["result"]
    print(f"Text message task state:  {task_result['state']}")
    print(f"Answer:                   {task_result.get('result', {}).get('answer', '')}")
    print()

    # Send structured data
    data_msg = A2AMessage(
        role="user",
        parts=[MessagePart.data({"prompt": "What is 6 times 7?"})],
    )
    request = {
        "jsonrpc": "2.0",
        "id": "req-003",
        "method": "tasks/send",
        "params": {
            "id": "task-003",
            "messages": [data_msg.to_dict()],
        },
    }
    response = await server.handle_request(request)
    task_result = response["result"]
    print(f"Data message task state:  {task_result['state']}")
    print(f"Answer:                   {task_result.get('result', {}).get('answer', '')}")
    print(f"Confidence:               {task_result.get('result', {}).get('confidence', 0)}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Task lifecycle (get, cancel)
# ---------------------------------------------------------------------------

async def example_task_lifecycle():
    """Demonstrate the full A2A task lifecycle: submit, get, cancel."""
    print("=== Example 3: Task Lifecycle (Submit, Get, Cancel) ===\n")

    flow = build_qa_flow()
    server = A2AServer(
        flow=flow,
        name="Lifecycle Agent",
        description="Demonstrates task lifecycle",
        url="http://localhost:8000",
    )

    # Submit a task
    submit_request = {
        "jsonrpc": "2.0",
        "id": "req-010",
        "method": "tasks/send",
        "params": {
            "id": "lifecycle-task-001",
            "messages": [
                {"role": "user", "parts": [{"kind": "text", "content": "Hello"}]},
            ],
        },
    }
    resp = await server.handle_request(submit_request)
    print(f"After submit -> state: {resp['result']['state']}")

    # Get the task status
    get_request = {
        "jsonrpc": "2.0",
        "id": "req-011",
        "method": "tasks/get",
        "params": {"id": "lifecycle-task-001"},
    }
    resp = await server.handle_request(get_request)
    print(f"After get    -> state: {resp['result']['state']}")
    print(f"               messages: {len(resp['result']['messages'])}")

    # Cancel the task
    cancel_request = {
        "jsonrpc": "2.0",
        "id": "req-012",
        "method": "tasks/cancel",
        "params": {"id": "lifecycle-task-001"},
    }
    resp = await server.handle_request(cancel_request)
    print(f"After cancel -> state: {resp['result']['state']}")

    # Verify cancellation
    resp = await server.handle_request(get_request)
    print(f"Verify       -> state: {resp['result']['state']}")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_server_and_agent_card()
    await example_client_usage()
    await example_task_lifecycle()
    print("All A2A examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
