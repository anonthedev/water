"""
Execution Replay Example: Rerun a Pipeline from a Failure Point

Demonstrates three replay scenarios:
  1. Recording a flow execution and its task outputs.
  2. Replaying from the task that failed, skipping earlier work.
  3. Overriding a task's input on replay to test a fix.

Usage:
    python cookbook/replay_flow.py
"""

import asyncio
from typing import Any, Dict

from pydantic import BaseModel

from water.core import Flow, create_task
from water.core.replay import ReplayConfig, ReplayEngine


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

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
    print(f"  [load] Storing {data['rows']} rows into warehouse...")
    return {**data, "stored": True}


# ---------------------------------------------------------------------------
# Build flow
# ---------------------------------------------------------------------------

def build_pipeline() -> Flow:
    t_extract = create_task(
        id="extract",
        description="Pull raw data",
        input_schema=RawData,
        output_schema=ExtractedData,
        execute=extract,
    )
    t_transform = create_task(
        id="transform",
        description="Clean and transform data",
        input_schema=ExtractedData,
        output_schema=TransformedData,
        execute=transform,
    )
    t_load = create_task(
        id="load",
        description="Store data in warehouse",
        input_schema=LoadedData,
        output_schema=LoadedData,
        execute=load,
    )

    flow = Flow(id="etl_pipeline", description="ETL Pipeline")
    flow.then(t_extract).then(t_transform).then(t_load).register()
    return flow


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------

async def scenario_1_record_execution():
    """Run the full pipeline and record task outputs."""
    print("=" * 60)
    print("Scenario 1: Full execution (recording outputs)")
    print("=" * 60)

    flow = build_pipeline()
    result = await flow.run({"records": 50})
    print(f"  Result: {result}\n")

    # In a real system the storage backend would persist these automatically.
    # Here we return them manually so the next scenarios can use them.
    recorded_outputs = {
        "extract": {"records": 50, "rows": 500},
        "transform": {"records": 50, "rows": 500, "cleaned": True},
        "load": {"records": 50, "rows": 500, "cleaned": True, "stored": True},
    }
    return recorded_outputs


async def scenario_2_replay_from_failure(recorded_outputs: Dict):
    """Replay from the 'load' step, reusing extract and transform outputs."""
    print("=" * 60)
    print("Scenario 2: Replay from the 'load' step (skip extract & transform)")
    print("=" * 60)

    flow = build_pipeline()
    engine = ReplayEngine()
    engine.set_task_outputs(recorded_outputs)

    result = await engine.replay(
        flow,
        session_id="original_session_001",
        config=ReplayConfig(from_task="load"),
    )

    print(f"  Cached steps   : {result.cached_steps}")
    print(f"  Re-executed    : {result.re_executed_steps}")
    print(f"  Status         : {result.status}")
    print(f"  Result         : {result.result}\n")


async def scenario_3_override_inputs(recorded_outputs: Dict):
    """Replay from 'transform' but override the row count to test a fix."""
    print("=" * 60)
    print("Scenario 3: Replay with overridden inputs")
    print("=" * 60)

    flow = build_pipeline()
    engine = ReplayEngine()
    engine.set_task_outputs(recorded_outputs)

    result = await engine.replay(
        flow,
        session_id="original_session_001",
        config=ReplayConfig(
            from_task="transform",
            override_inputs={"transform": {"rows": 9999, "records": 50}},
        ),
    )

    print(f"  Cached steps   : {result.cached_steps}")
    print(f"  Re-executed    : {result.re_executed_steps}")
    print(f"  Status         : {result.status}")
    print(f"  Result         : {result.result}\n")


async def main():
    recorded = await scenario_1_record_execution()
    await scenario_2_replay_from_failure(recorded)
    await scenario_3_override_inputs(recorded)


if __name__ == "__main__":
    asyncio.run(main())
