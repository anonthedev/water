"""
Versioning Flow Example: Versioned Data Pipeline

This example demonstrates how to attach a version string to a flow. After
execution the version is available in the flow's metadata, making it easy
to track which pipeline definition produced a given result.
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio


# Data schemas
class RawRecord(BaseModel):
    record_id: str
    value: float


class NormalizedRecord(BaseModel):
    record_id: str
    value: float
    normalized_value: float


class ProcessedRecord(BaseModel):
    record_id: str
    value: float
    normalized_value: float
    category: str


# Task: Normalize the value
def normalize(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Normalize the raw value to a 0-1 scale (assuming max 1000)."""
    data = params["input_data"]
    normalized = round(min(data["value"] / 1000.0, 1.0), 4)
    return {
        "record_id": data["record_id"],
        "value": data["value"],
        "normalized_value": normalized,
    }


# Task: Categorize based on normalized value
def categorize(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Assign a category based on the normalized value."""
    data = params["input_data"]
    nv = data["normalized_value"]
    if nv >= 0.75:
        category = "high"
    elif nv >= 0.25:
        category = "medium"
    else:
        category = "low"
    return {
        "record_id": data["record_id"],
        "value": data["value"],
        "normalized_value": data["normalized_value"],
        "category": category,
    }


# Create tasks
normalize_task = create_task(
    id="normalize",
    description="Normalize the raw value",
    input_schema=RawRecord,
    output_schema=NormalizedRecord,
    execute=normalize,
)

categorize_task = create_task(
    id="categorize",
    description="Categorize the normalized value",
    input_schema=NormalizedRecord,
    output_schema=ProcessedRecord,
    execute=categorize,
)

# Build a versioned flow
versioned_flow = Flow(
    id="data_pipeline",
    description="Versioned data normalization and categorization pipeline",
    version="1.0.0",
)
versioned_flow.then(normalize_task)\
    .then(categorize_task)\
    .register()


async def main():
    """Run the versioned flow example and inspect metadata."""

    record = {
        "record_id": "REC-42",
        "value": 680.0,
    }

    try:
        result = await versioned_flow.run(record)
        print(f"Record:     {result['record_id']}")
        print(f"  Value:      {result['value']}")
        print(f"  Normalized: {result['normalized_value']}")
        print(f"  Category:   {result['category']}")
        print(f"\nFlow version from metadata: {versioned_flow.metadata.get('_flow_version')}")
        print(f"Flow metadata: {versioned_flow.metadata}")
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
