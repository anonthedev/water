"""
Cookbook: Declarative Flow Definitions

This example shows how to define a data pipeline using a dict/JSON
configuration instead of Python chaining, and then execute it.
"""

import asyncio
import json
from pydantic import BaseModel
from water import create_task, load_flow_from_dict, load_flow_from_json


# ---- 1. Define schemas ----

class PipelineInput(BaseModel):
    text: str
    value: int = 0


class PipelineOutput(BaseModel):
    text: str
    value: int = 0


# ---- 2. Create tasks ----

normalize_task = create_task(
    id="normalize",
    description="Normalize text to lowercase",
    input_schema=PipelineInput,
    output_schema=PipelineOutput,
    execute=lambda params, ctx: {
        "text": params["input_data"]["text"].strip().lower(),
        "value": params["input_data"].get("value", 0),
    },
)

enrich_task = create_task(
    id="enrich",
    description="Add word count to value",
    input_schema=PipelineInput,
    output_schema=PipelineOutput,
    execute=lambda params, ctx: {
        "text": params["input_data"]["text"],
        "value": len(params["input_data"]["text"].split()),
    },
)

validate_task = create_task(
    id="validate",
    description="Mark text as validated",
    input_schema=PipelineInput,
    output_schema=PipelineOutput,
    execute=lambda params, ctx: {
        "text": f"[valid] {params['input_data']['text']}",
        "value": params["input_data"].get("value", 0),
    },
)


# ---- 3. Define the flow as a plain dict (could be loaded from a file) ----

pipeline_config = {
    "id": "data_pipeline",
    "description": "A declarative data processing pipeline",
    "version": "1.0",
    "steps": [
        {"type": "sequential", "task": "normalize"},
        {"type": "sequential", "task": "enrich"},
        {"type": "sequential", "task": "validate"},
    ],
}

# ---- 4. Build the task registry ----

task_registry = {
    "normalize": normalize_task,
    "enrich": enrich_task,
    "validate": validate_task,
}


# ---- 5. Load and run ----

async def main():
    # Option A: Load from a dict
    flow = load_flow_from_dict(pipeline_config, task_registry)
    result = await flow.run({"text": "  Hello World  ", "value": 0})
    print("Dict result:", result)
    # Expected: {"text": "[valid] hello world", "value": 2}

    # Option B: Load from a JSON string (e.g., read from a file)
    json_str = json.dumps(pipeline_config)
    flow_json = load_flow_from_json(json_str, task_registry)
    result_json = await flow_json.run({"text": " Water Framework ", "value": 0})
    print("JSON result:", result_json)
    # Expected: {"text": "[valid] water framework", "value": 2}


if __name__ == "__main__":
    asyncio.run(main())
