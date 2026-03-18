"""
Fallback Flow Example: API Enrichment with Cache Fallback

This example demonstrates using the fallback parameter on .then() to gracefully
handle task failures. When the primary API enrichment task fails (e.g., the
external API is down), the flow automatically falls back to a cache lookup
instead of failing the entire pipeline.
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio


# Data schemas
class UserProfile(BaseModel):
    user_id: str
    email: str


class EnrichedProfile(BaseModel):
    user_id: str
    email: str
    company: Optional[str]
    location: Optional[str]
    enrichment_source: str


# Simulated cache of previously enriched profiles
ENRICHMENT_CACHE: Dict[str, Dict[str, Any]] = {
    "user_001": {
        "company": "Acme Corp (cached)",
        "location": "San Francisco, CA (cached)",
    },
    "user_002": {
        "company": "Globex Inc (cached)",
        "location": "New York, NY (cached)",
    },
}


# Primary task: Call external API for enrichment
def enrich_via_api(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Enrich a user profile by calling an external API.

    In a real application this would call a service like Clearbit or
    FullContact. Here we simulate an API outage by raising an exception.
    """
    data = params["input_data"]

    # Simulate API failure
    raise ConnectionError(
        f"External enrichment API is unreachable for user {data['user_id']}"
    )


# Fallback task: Look up cached enrichment data
def enrich_via_cache(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Fall back to cached enrichment data when the API is unavailable."""
    data = params["input_data"]
    user_id = data["user_id"]

    cached = ENRICHMENT_CACHE.get(user_id, {})

    return {
        "user_id": user_id,
        "email": data["email"],
        "company": cached.get("company", "Unknown"),
        "location": cached.get("location", "Unknown"),
        "enrichment_source": "cache",
    }


# Final step: Format the enriched profile for downstream consumers
def format_profile(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Produce a final summary of the enriched profile."""
    data = params["input_data"]
    return {
        "user_id": data["user_id"],
        "email": data["email"],
        "company": data.get("company", "Unknown"),
        "location": data.get("location", "Unknown"),
        "enrichment_source": data.get("enrichment_source", "none"),
    }


# Create tasks
api_enrichment_task = create_task(
    id="api_enrichment",
    description="Enrich user profile via external API",
    input_schema=UserProfile,
    output_schema=EnrichedProfile,
    execute=enrich_via_api,
)

cache_enrichment_task = create_task(
    id="cache_enrichment",
    description="Enrich user profile from local cache",
    input_schema=UserProfile,
    output_schema=EnrichedProfile,
    execute=enrich_via_cache,
)

format_task = create_task(
    id="format_profile",
    description="Format enriched profile for output",
    input_schema=EnrichedProfile,
    output_schema=EnrichedProfile,
    execute=format_profile,
)

# Build the flow: API enrichment falls back to cache, then format the result
enrichment_flow = Flow(
    id="profile_enrichment",
    description="Enrich user profiles with API fallback to cache",
)
enrichment_flow.then(api_enrichment_task, fallback=cache_enrichment_task)\
    .then(format_task)\
    .register()


async def main():
    """Run the fallback enrichment example."""

    user = {
        "user_id": "user_001",
        "email": "alice@example.com",
    }

    try:
        result = await enrichment_flow.run(user)
        print(f"Enrichment succeeded via: {result['enrichment_source']}")
        print(f"  User:     {result['user_id']}")
        print(f"  Email:    {result['email']}")
        print(f"  Company:  {result['company']}")
        print(f"  Location: {result['location']}")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
