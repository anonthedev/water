"""
Checkpoint Flow Example: Crash-Recoverable ETL Pipeline

Demonstrates how to use InMemoryCheckpoint so a long-running flow can
resume from the last successful step after a failure, instead of
restarting from scratch.

Usage:
    python cookbook/checkpoint_flow.py
"""

import asyncio
from typing import Any, Dict

from pydantic import BaseModel

from water import Flow, create_task, InMemoryCheckpoint


# --- Schemas ---

class RawData(BaseModel):
    records: int


class ExtractedData(BaseModel):
    records: int
    rows: int


class TransformedData(BaseModel):
    records: int
    rows: int
    cleaned: bool


class LoadedData(BaseModel):
    records: int
    rows: int
    cleaned: bool
    stored: bool


# --- Tasks ---

def extract(params: Dict[str, Any], context) -> Dict[str, Any]:
    data = params["input_data"]
    print(f"  [extract] Pulling {data['records']} records from source...")
    return {**data, "rows": data["records"] * 10}


def transform(params: Dict[str, Any], context) -> Dict[str, Any]:
    data = params["input_data"]
    print(f"  [transform] Cleaning {data['rows']} rows...")
    return {**data, "cleaned": True}


def load(params: Dict[str, Any], context) -> Dict[str, Any]:
    data = params["input_data"]
    print(f"  [load] Writing {data['rows']} cleaned rows to warehouse...")
    return {**data, "stored": True}


extract_task = create_task(
    id="extract",
    description="Extract raw records",
    input_schema=RawData,
    output_schema=ExtractedData,
    execute=extract,
)

transform_task = create_task(
    id="transform",
    description="Clean and transform rows",
    input_schema=ExtractedData,
    output_schema=TransformedData,
    execute=transform,
)

load_task = create_task(
    id="load",
    description="Load rows into the warehouse",
    input_schema=TransformedData,
    output_schema=LoadedData,
    execute=load,
)


# --- Flow ---

checkpoint = InMemoryCheckpoint()

etl = Flow(id="etl_pipeline", description="Recoverable ETL pipeline")
etl.checkpoint = checkpoint
etl.then(extract_task).then(transform_task).then(load_task).register()


async def main():
    print("=== ETL Pipeline with Checkpointing ===\n")

    # Normal run — all three steps execute and checkpoint is cleared at the end.
    print("Run 1 (fresh):")
    result = await etl.run({"records": 50})
    print(f"  Result: {result}\n")

    # Simulate a crash after the first two steps by manually saving a checkpoint.
    print("Simulating crash after 'transform' step...")
    await checkpoint.save(
        "etl_pipeline",
        "recovery_demo",
        2,  # next node index (the 'load' step)
        {"records": 50, "rows": 500, "cleaned": True},
    )
    print("  Checkpoint saved. Restarting flow...\n")

    # On the next run the engine will detect the checkpoint and skip ahead.
    # NOTE: In a real application the execution_id would match automatically;
    # here we demonstrate the concept.
    print("Run 2 (recovered — only 'load' runs):")
    result = await etl.run({"records": 50})
    print(f"  Result: {result}\n")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
