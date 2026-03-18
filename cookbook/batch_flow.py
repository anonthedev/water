"""
Batch Flow Example: Processing User Records with Concurrency Control

This example demonstrates how to use run_batch to process multiple inputs
through a flow concurrently, with a configurable concurrency limit.
Useful for bulk operations like importing users, processing orders, or
making rate-limited API calls.
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import uuid


# Data schemas
class UserRecord(BaseModel):
    email: str
    name: str


class EnrichedUser(BaseModel):
    email: str
    name: str
    user_id: str
    email_domain: str
    processed: bool


# Step 1: Enrich user record (simulates an API call)
async def enrich_user(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate enriching a user record via an external API."""
    data = params["input_data"]

    # Simulate network latency
    await asyncio.sleep(0.1)

    return {
        "email": data["email"],
        "name": data["name"],
        "user_id": f"user_{uuid.uuid4().hex[:8]}",
        "email_domain": data["email"].split("@")[1],
        "processed": True,
    }


# Create task and flow
enrich_task = create_task(
    id="enrich",
    description="Enrich user record with generated ID and domain",
    input_schema=UserRecord,
    output_schema=EnrichedUser,
    execute=enrich_user,
)

user_flow = Flow(id="user_enrichment", description="Enrich user records")
user_flow.then(enrich_task).register()


async def main():
    """Run a batch of user records through the enrichment flow."""

    # Prepare a batch of user records
    user_records = [
        {"email": "alice@example.com", "name": "Alice"},
        {"email": "bob@widgets.io", "name": "Bob"},
        {"email": "carol@startup.dev", "name": "Carol"},
        {"email": "dave@bigcorp.com", "name": "Dave"},
        {"email": "eve@research.org", "name": "Eve"},
        {"email": "frank@agency.net", "name": "Frank"},
    ]

    print(f"Processing {len(user_records)} user records (max_concurrency=3)...\n")

    results = await user_flow.run_batch(
        user_records,
        max_concurrency=3,
        return_exceptions=False,
    )

    for result in results:
        print(f"  {result['name']:>8} -> {result['user_id']}  ({result['email_domain']})")

    print(f"\nAll {len(results)} records processed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
