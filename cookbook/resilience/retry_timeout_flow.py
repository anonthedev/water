"""
Retry and Timeout Flow Example: Resilient API Call

This example demonstrates a flow with retry logic and timeout protection.
A task simulates an intermittently failing API call that succeeds on the
third attempt using exponential backoff. A timeout ensures the task does
not hang indefinitely.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio

# Mutable counter to simulate intermittent failures
_attempt_counter = {"count": 0}


# Data schemas
class ApiRequest(BaseModel):
    endpoint: str
    payload: str


class ApiResponse(BaseModel):
    endpoint: str
    status_code: int
    body: str
    attempts: int


# Task: Call an unreliable API
def call_unreliable_api(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate an API that fails twice before succeeding on the third attempt."""
    data = params["input_data"]
    _attempt_counter["count"] += 1
    attempt = _attempt_counter["count"]

    if attempt < 3:
        raise ConnectionError(f"API unavailable (attempt {attempt})")

    return {
        "endpoint": data["endpoint"],
        "status_code": 200,
        "body": f"Success from {data['endpoint']}",
        "attempts": attempt,
    }


# Task: Process the API response
def process_response(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Format the successful API response."""
    data = params["input_data"]
    return {
        "endpoint": data["endpoint"],
        "status_code": data["status_code"],
        "body": f"[processed] {data['body']}",
        "attempts": data["attempts"],
    }


# Create tasks
api_task = create_task(
    id="api_call",
    description="Call unreliable API with retry and timeout",
    input_schema=ApiRequest,
    output_schema=ApiResponse,
    execute=call_unreliable_api,
    retry_count=3,
    retry_delay=0.5,
    retry_backoff=2.0,
    timeout=5.0,
)

process_task = create_task(
    id="process",
    description="Process the API response",
    input_schema=ApiResponse,
    output_schema=ApiResponse,
    execute=process_response,
)

# Build the flow
api_flow = Flow(id="retry_timeout_api", description="Resilient API call with retry and timeout")
api_flow.then(api_task)\
    .then(process_task)\
    .register()


async def main():
    """Run the retry and timeout example."""

    request = {
        "endpoint": "https://api.example.com/data",
        "payload": "fetch_user_records",
    }

    try:
        result = await api_flow.run(request)
        print(f"API call succeeded after {result['attempts']} attempts")
        print(f"  Endpoint:    {result['endpoint']}")
        print(f"  Status:      {result['status_code']}")
        print(f"  Body:        {result['body']}")
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
