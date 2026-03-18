"""
Dependency Injection Flow
=========================

Demonstrates injecting shared services (database client, API client) into
tasks via the Water execution context.  Tasks retrieve services with
``context.get_service(name)`` rather than importing or instantiating
clients themselves, which keeps task logic decoupled from infrastructure.
"""

import asyncio
from pydantic import BaseModel
from water.core import create_task, Flow


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserInput(BaseModel):
    user_id: str

class UserProfile(BaseModel):
    user_id: str
    name: str
    email: str

class EnrichedProfile(BaseModel):
    user_id: str
    name: str
    email: str
    reputation_score: float


# ---------------------------------------------------------------------------
# Stub services (replace with real clients in production)
# ---------------------------------------------------------------------------

class DatabaseClient:
    """Simulates a database connection."""

    async def fetch_user(self, user_id: str) -> dict:
        return {
            "user_id": user_id,
            "name": "Alice",
            "email": "alice@example.com",
        }


class ReputationAPIClient:
    """Simulates an external reputation-scoring API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def get_score(self, user_id: str) -> float:
        return 92.5


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@create_task(
    id="fetch_user",
    description="Load user profile from the database",
    input_schema=UserInput,
    output_schema=UserProfile,
)
async def fetch_user(input_data, context):
    db = context.get_service("db")
    profile = await db.fetch_user(input_data["user_id"])
    return profile


@create_task(
    id="enrich_profile",
    description="Augment profile with a reputation score from an external API",
    input_schema=UserProfile,
    output_schema=EnrichedProfile,
)
async def enrich_profile(input_data, context):
    api = context.get_service("reputation_api")
    score = await api.get_score(input_data["user_id"])
    return {**input_data, "reputation_score": score}


# ---------------------------------------------------------------------------
# Flow definition
# ---------------------------------------------------------------------------

flow = (
    Flow(id="user_enrichment", description="Fetch user and enrich with reputation score")
    .inject("db", DatabaseClient())
    .inject("reputation_api", ReputationAPIClient(api_key="sk-test-123"))
    .then(fetch_user)
    .then(enrich_profile)
    .register()
)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

async def main():
    result = await flow.run({"user_id": "u_42"})
    print("Enriched profile:", result)


if __name__ == "__main__":
    asyncio.run(main())
