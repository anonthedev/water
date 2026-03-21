"""
Sub-Flow Example: Data Enrichment via Nested Flow

This example demonstrates composing flows by embedding a sub-flow inside a
parent flow. The sub-flow is registered independently and then used as a
task via Flow.as_task(). Auto-coercion is also shown: passing a Flow
directly to .then() converts it automatically.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio


# Data schemas
class RawLead(BaseModel):
    name: str
    email: str


class EnrichedLead(BaseModel):
    name: str
    email: str
    domain: str
    company: Optional[str]


class ScoredLead(BaseModel):
    name: str
    email: str
    domain: str
    company: Optional[str]
    score: int


# --- Sub-flow tasks: enrich a lead ---

def extract_domain(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Extract the email domain."""
    data = params["input_data"]
    domain = data["email"].split("@")[-1]
    return {
        "name": data["name"],
        "email": data["email"],
        "domain": domain,
        "company": None,
    }


def lookup_company(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Look up company name from domain."""
    data = params["input_data"]
    domain_to_company = {
        "water.ai": "Water AI",
        "acme.com": "Acme Corp",
    }
    return {
        "name": data["name"],
        "email": data["email"],
        "domain": data["domain"],
        "company": domain_to_company.get(data["domain"], "Unknown"),
    }


extract_task = create_task(
    id="extract_domain",
    description="Extract email domain",
    input_schema=RawLead,
    output_schema=EnrichedLead,
    execute=extract_domain,
)

lookup_task = create_task(
    id="lookup_company",
    description="Look up company from domain",
    input_schema=EnrichedLead,
    output_schema=EnrichedLead,
    execute=lookup_company,
)

# Build and register the sub-flow
enrichment_subflow = Flow(id="lead_enrichment", description="Enrich a raw lead with company data")
enrichment_subflow.then(extract_task)\
    .then(lookup_task)\
    .register()


# --- Parent flow tasks ---

def score_lead(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Assign a score based on enrichment data."""
    data = params["input_data"]
    score = 50
    if data.get("company") and data["company"] != "Unknown":
        score += 30
    if data.get("domain", "").endswith(".ai"):
        score += 20
    return {
        "name": data["name"],
        "email": data["email"],
        "domain": data["domain"],
        "company": data.get("company"),
        "score": score,
    }


score_task = create_task(
    id="score_lead",
    description="Score the enriched lead",
    input_schema=EnrichedLead,
    output_schema=ScoredLead,
    execute=score_lead,
)

# Build the parent flow using auto-coercion (passing Flow directly to .then())
lead_pipeline = Flow(id="lead_pipeline", description="Full lead pipeline with sub-flow enrichment")
lead_pipeline.then(enrichment_subflow)\
    .then(score_task)\
    .register()


async def main():
    """Run the sub-flow enrichment example."""

    lead = {
        "name": "Manthan Gupta",
        "email": "manthan.gupta@water.ai",
    }

    try:
        result = await lead_pipeline.run(lead)
        print(f"Lead: {result['name']}")
        print(f"  Company: {result['company']}")
        print(f"  Domain:  {result['domain']}")
        print(f"  Score:   {result['score']}")
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
