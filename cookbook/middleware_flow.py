"""
Middleware Flow Example: Authentication Headers & Logging

This example demonstrates how to use middleware to inject authentication
headers and log every task execution — without adding explicit task nodes
for cross-cutting concerns.
"""

from water import Flow, create_task, Middleware, LoggingMiddleware, TransformMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# --- Schemas ---

class ApiRequest(BaseModel):
    url: str
    method: str

class ApiResponse(BaseModel):
    url: str
    status: int
    body: str


# --- Custom middleware: inject auth headers into every task's input ---

class AuthMiddleware(Middleware):
    """Adds an 'auth_token' key to every task's input data."""

    def __init__(self, token: str) -> None:
        self.token = token

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        print(f"  [AuthMiddleware] Injecting auth token for task '{task_id}'")
        return {**data, "auth_token": self.token}

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        # Strip the token from the result so it doesn't leak downstream
        cleaned = {k: v for k, v in result.items() if k != "auth_token"}
        return cleaned


# --- Tasks ---

def fetch_data(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate an authenticated API call."""
    inp = params["input_data"]
    token = inp.get("auth_token", "MISSING")
    print(f"  [fetch_data] Calling {inp['method']} {inp['url']} with token={token[:8]}...")
    return {
        "url": inp["url"],
        "status": 200,
        "body": '{"users": ["alice", "bob"]}',
    }

def process_response(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Process the API response."""
    inp = params["input_data"]
    token = inp.get("auth_token", "MISSING")
    print(f"  [process_response] Processing response from {inp['url']} with token={token[:8]}...")
    return {
        "url": inp["url"],
        "status": inp["status"],
        "body": f"Processed: {inp['body']}",
    }


fetch_task = create_task(
    id="fetch_data",
    description="Fetch data from API",
    input_schema=ApiRequest,
    output_schema=ApiResponse,
    execute=fetch_data,
)

process_task = create_task(
    id="process_response",
    description="Process API response",
    input_schema=ApiResponse,
    output_schema=ApiResponse,
    execute=process_response,
)


# --- Build the flow with middleware ---

flow = Flow(id="auth_logging_flow", description="API flow with auth and logging")

# Chain middleware — auth is applied first, then logging observes the result
flow.use(AuthMiddleware(token="sk-secret-token-12345678")) \
    .use(LoggingMiddleware()) \
    .then(fetch_task) \
    .then(process_task) \
    .register()


async def main():
    print("=== Middleware Flow: Auth + Logging ===\n")

    result = await flow.run({"url": "https://api.example.com/users", "method": "GET"})

    print(f"\nFinal result: {result}")
    # Notice: auth_token is stripped from the final output by AuthMiddleware.after_task


if __name__ == "__main__":
    asyncio.run(main())
