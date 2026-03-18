"""
Rate Limit Flow Example: Throttled API Calls

This example demonstrates tasks with rate_limit=2.0 (2 calls per second)
to avoid hitting external API rate limits. Shows timing between calls to
prove that throttling is working.

Usage:
    python cookbook/rate_limit_flow.py
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import time

# Data schemas
class ApiRequest(BaseModel):
    endpoint: str
    page: int

class ApiResponse(BaseModel):
    endpoint: str
    page: int
    items_fetched: int
    timestamp: float

class AggregatedResult(BaseModel):
    total_items: int
    pages_fetched: int
    elapsed_seconds: float

# Simulated API call (rate-limited to 2 calls/second)
def fetch_page(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate fetching one page from an external API."""
    data = params["input_data"]
    now = time.time()
    print(f"  [fetch] page={data['page']} at t={now:.3f}")
    return {
        "endpoint": data["endpoint"],
        "page": data["page"],
        "items_fetched": 25,
        "timestamp": now,
    }

# Aggregation step
def aggregate(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Combine results from all fetched pages."""
    results = params["input_data"]
    timestamps = [r["timestamp"] for r in results.values()]
    total_items = sum(r["items_fetched"] for r in results.values())
    elapsed = max(timestamps) - min(timestamps)
    return {
        "total_items": total_items,
        "pages_fetched": len(results),
        "elapsed_seconds": round(elapsed, 3),
    }

# Create rate-limited fetch tasks (2 calls per second)
fetch_tasks = []
for page_num in range(1, 6):
    task = create_task(
        id=f"fetch_page_{page_num}",
        description=f"Fetch page {page_num} from API",
        input_schema=ApiRequest,
        output_schema=ApiResponse,
        execute=fetch_page,
        rate_limit=2.0,
    )
    fetch_tasks.append(task)

aggregate_task = create_task(
    id="aggregate",
    description="Aggregate fetched pages",
    input_schema=ApiResponse,
    output_schema=AggregatedResult,
    execute=aggregate,
)

# Build flow: run all fetches in parallel (rate limiter throttles them),
# then aggregate
api_flow = Flow(id="rate_limited_api", description="Throttled API fetch flow")
api_flow.parallel(fetch_tasks).then(aggregate_task).register()

async def main():
    """Run the rate-limited API flow example."""
    print("=== Rate-Limited API Flow (2 calls/sec) ===\n")

    request = {
        "endpoint": "https://api.example.com/items",
        "page": 1,
    }

    start = time.time()
    try:
        result = await api_flow.run(request)
        wall_time = round(time.time() - start, 3)
        print(f"\n  Result: {result}")
        print(f"  Wall clock time: {wall_time}s")
        print(f"  Expected minimum: ~2.0s for 5 calls at 2/sec")
        print("  flow completed successfully!")
    except Exception as e:
        print(f"  ERROR - {e}")

    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
