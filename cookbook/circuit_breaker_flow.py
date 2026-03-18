"""
Circuit Breaker Flow Example: Protecting External API Calls

This example demonstrates the circuit breaker pattern to protect against
cascading failures from an unreliable external API. After consecutive
failures the circuit opens, rejecting further calls immediately. Once
the recovery timeout elapses the circuit enters half-open state and
allows a single test call to check if the service has recovered.
"""

from water import Flow, create_task, CircuitBreaker, CircuitBreakerOpen
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import random

# Data schemas
class APIRequest(BaseModel):
    endpoint: str

class APIResponse(BaseModel):
    endpoint: str
    status: str
    data: str

# Create a circuit breaker: opens after 3 failures, recovers after 5 seconds
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)

# Simulated unreliable API
request_count = 0

def call_external_api(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate an external API that fails intermittently."""
    global request_count
    request_count += 1
    endpoint = params["input_data"]["endpoint"]

    # Simulate: first 4 calls fail, then recover
    if request_count <= 4:
        print(f"  [Request #{request_count}] {endpoint} -> FAILURE (service unavailable)")
        raise ConnectionError(f"Service unavailable for {endpoint}")

    print(f"  [Request #{request_count}] {endpoint} -> SUCCESS")
    return {
        "endpoint": endpoint,
        "status": "ok",
        "data": f"Response from {endpoint}",
    }

# Create task with circuit breaker protection
api_task = create_task(
    id="external_api",
    description="Call external API with circuit breaker",
    input_schema=APIRequest,
    output_schema=APIResponse,
    execute=call_external_api,
    circuit_breaker=breaker,
)

# Build flow
api_flow = Flow(id="api_call", description="Protected API call")
api_flow.then(api_task).register()

async def main():
    print("=== Circuit Breaker Example ===\n")

    endpoints = ["/users", "/orders", "/products", "/health", "/users", "/orders"]

    for endpoint in endpoints:
        print(f"Calling {endpoint} (circuit: {breaker.state})...")
        try:
            result = await api_flow.run({"endpoint": endpoint})
            print(f"  Result: {result['status']} — {result['data']}")
        except CircuitBreakerOpen:
            print(f"  BLOCKED: Circuit breaker is open — call rejected immediately")
        except ConnectionError as e:
            print(f"  ERROR: {e}")
        print()

    # Wait for recovery timeout
    print("Waiting for recovery timeout (5 seconds)...\n")
    await asyncio.sleep(5.0)

    # Try again — circuit is now half-open
    print(f"Retrying (circuit: {breaker.state})...")
    try:
        result = await api_flow.run({"endpoint": "/health"})
        print(f"  Result: {result['status']} — {result['data']}")
        print(f"  Circuit recovered: {breaker.state}")
    except Exception as e:
        print(f"  Still failing: {e}")

if __name__ == "__main__":
    asyncio.run(main())
