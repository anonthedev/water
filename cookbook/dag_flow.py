"""
DAG Flow Example: Data Pipeline with Diamond Dependencies

This example demonstrates a DAG (directed acyclic graph) of tasks with
automatic parallelization. Uses a classic diamond pattern where:

    A (ingest) -> B (clean), C (enrich) -> D (publish)

Tasks B and C run in parallel because they only depend on A.
Task D waits for both B and C to finish before executing.

Usage:
    python cookbook/dag_flow.py
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import time

# Data schemas
class RawPayload(BaseModel):
    source: str
    record_count: int

class IngestedData(BaseModel):
    source: str
    record_count: int
    ingested_at: float

class CleanedData(BaseModel):
    source: str
    record_count: int
    nulls_removed: int
    cleaned_at: float

class EnrichedData(BaseModel):
    source: str
    record_count: int
    geo_tagged: bool
    enriched_at: float

class PublishedData(BaseModel):
    source: str
    record_count: int
    nulls_removed: int
    geo_tagged: bool
    published_at: float
    pipeline_complete: bool

# Task A: Ingest raw data
def ingest(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Pull raw records from the data source."""
    data = params["input_data"]
    now = time.time()
    print(f"  [A ingest]  Started  at t={now:.3f}")
    return {
        "source": data["source"],
        "record_count": data["record_count"],
        "ingested_at": now,
    }

# Task B: Clean data (runs in parallel with C)
async def clean(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Remove nulls and duplicates."""
    data = params["input_data"]
    await asyncio.sleep(0.3)  # Simulate work
    now = time.time()
    print(f"  [B clean]   Finished at t={now:.3f}")
    return {
        "source": data["source"],
        "record_count": data["record_count"],
        "nulls_removed": 42,
        "cleaned_at": now,
    }

# Task C: Enrich data (runs in parallel with B)
async def enrich(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Add geo-tagging and metadata."""
    data = params["input_data"]
    await asyncio.sleep(0.3)  # Simulate work
    now = time.time()
    print(f"  [C enrich]  Finished at t={now:.3f}")
    return {
        "source": data["source"],
        "record_count": data["record_count"],
        "geo_tagged": True,
        "enriched_at": now,
    }

# Task D: Publish (depends on both B and C)
def publish(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Write final dataset to the data warehouse."""
    data = params["input_data"]
    # Access outputs from upstream DAG tasks via context
    clean_out = context.get_task_output("clean")
    enrich_out = context.get_task_output("enrich")
    now = time.time()
    print(f"  [D publish] Finished at t={now:.3f}")
    return {
        "source": data.get("source", clean_out.get("source", "")),
        "record_count": data.get("record_count", clean_out.get("record_count", 0)),
        "nulls_removed": clean_out.get("nulls_removed", 0),
        "geo_tagged": enrich_out.get("geo_tagged", False),
        "published_at": now,
        "pipeline_complete": True,
    }

# Create tasks
ingest_task = create_task(
    id="ingest",
    description="Ingest raw data from source",
    input_schema=RawPayload,
    output_schema=IngestedData,
    execute=ingest,
)

clean_task = create_task(
    id="clean",
    description="Clean and deduplicate records",
    input_schema=IngestedData,
    output_schema=CleanedData,
    execute=clean,
)

enrich_task = create_task(
    id="enrich",
    description="Enrich records with geo-tagging",
    input_schema=IngestedData,
    output_schema=EnrichedData,
    execute=enrich,
)

publish_task = create_task(
    id="publish",
    description="Publish final dataset to warehouse",
    input_schema=EnrichedData,
    output_schema=PublishedData,
    execute=publish,
)

# Build the DAG flow with diamond dependencies:
#   ingest -> clean  \
#                     -> publish
#   ingest -> enrich /
pipeline_flow = Flow(id="diamond_pipeline", description="DAG data pipeline with diamond pattern")
pipeline_flow.then(ingest_task).dag(
    tasks=[clean_task, enrich_task, publish_task],
    dependencies={
        "clean": [],            # depends only on prior sequential output
        "enrich": [],           # depends only on prior sequential output
        "publish": ["clean", "enrich"],  # waits for both
    },
).register()

async def main():
    """Run the DAG pipeline example."""
    print("=== DAG Pipeline (Diamond Pattern: A -> B,C -> D) ===\n")

    payload = {
        "source": "clickstream_db",
        "record_count": 10000,
    }

    start = time.time()
    try:
        result = await pipeline_flow.run(payload)
        elapsed = round(time.time() - start, 3)
        print(f"\n  Result: {result}")
        print(f"  Total wall time: {elapsed}s")
        print("  (B and C ran in parallel, so total is ~0.3s, not ~0.6s)")
        print("  flow completed successfully!")
    except Exception as e:
        print(f"  ERROR - {e}")

    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
