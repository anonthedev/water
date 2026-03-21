"""
Map Flow Example: Parallel Item Processing (Fan-Out / Fan-In)

This example demonstrates the .map() operator which executes a task once
per item in a list field. Items are processed in parallel and the results
are collected back into a list, implementing a fan-out/fan-in pattern.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any, List
import asyncio


# Data schemas
class ImageBatch(BaseModel):
    batch_id: str
    images: List[Dict[str, Any]]


class ImageResult(BaseModel):
    batch_id: str
    image_id: str
    thumbnail_url: str
    width: int
    height: int


class BatchSummary(BaseModel):
    batch_id: str
    total_processed: int
    thumbnails: List[str]


# Task: Process a single image (runs once per item via .map())
def generate_thumbnail(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Generate a thumbnail for a single image."""
    data = params["input_data"]
    image = data["images"]  # .map() replaces the list with the individual item
    return {
        "batch_id": data["batch_id"],
        "image_id": image["image_id"],
        "thumbnail_url": f"https://cdn.example.com/thumb/{image['image_id']}.jpg",
        "width": image.get("width", 1920) // 4,
        "height": image.get("height", 1080) // 4,
    }


# Task: Aggregate results after map
def summarize_batch(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Collect all thumbnail results into a batch summary."""
    results = params["input_data"]
    # After .map(), input_data is a list of individual task outputs
    if isinstance(results, list):
        return {
            "batch_id": results[0]["batch_id"] if results else "unknown",
            "total_processed": len(results),
            "thumbnails": [r["thumbnail_url"] for r in results],
        }
    return {
        "batch_id": results.get("batch_id", "unknown"),
        "total_processed": 1,
        "thumbnails": [results.get("thumbnail_url", "")],
    }


# Create tasks
thumbnail_task = create_task(
    id="generate_thumbnail",
    description="Generate thumbnail for a single image",
    input_schema=ImageBatch,
    output_schema=ImageResult,
    execute=generate_thumbnail,
)

summary_task = create_task(
    id="summarize_batch",
    description="Summarize the batch processing results",
    input_schema=ImageResult,
    output_schema=BatchSummary,
    execute=summarize_batch,
)

# Build the flow: fan-out over images, then aggregate
image_flow = Flow(id="image_processing", description="Parallel image thumbnail generation")
image_flow.map(thumbnail_task, over="images")\
    .then(summary_task)\
    .register()


async def main():
    """Run the map flow example."""

    batch = {
        "batch_id": "BATCH-001",
        "images": [
            {"image_id": "img_01", "width": 3840, "height": 2160},
            {"image_id": "img_02", "width": 1920, "height": 1080},
            {"image_id": "img_03", "width": 2560, "height": 1440},
            {"image_id": "img_04", "width": 1280, "height": 720},
        ],
    }

    try:
        result = await image_flow.run(batch)
        print(f"Batch: {result['batch_id']}")
        print(f"Processed: {result['total_processed']} images")
        for url in result["thumbnails"]:
            print(f"  {url}")
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
