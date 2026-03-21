"""
CLI Usage Example: Using Water flows from the command line.

This module defines a simple data-processing flow and demonstrates
how to interact with it using the `water` CLI commands.

# -------------------------------------------------------------------------
# CLI Commands
# -------------------------------------------------------------------------
#
# 1. Run the flow with input data:
#
#    water run cookbook.cli_usage_flow:process_flow \
#        --input '{"text": "hello world", "uppercase": true}'
#
#    Output (JSON):
#    {
#      "original": "hello world",
#      "processed": "HELLO WORLD",
#      "length": 11
#    }
#
# 2. Visualize the flow as a Mermaid diagram:
#
#    water visualize cookbook.cli_usage_flow:process_flow
#
#    Save to file:
#    water visualize cookbook.cli_usage_flow:process_flow --output diagram.md
#
# 3. Dry-run the flow (validate without executing):
#
#    water dry-run cookbook.cli_usage_flow:process_flow \
#        --input '{"text": "hello world", "uppercase": true}'
#
# 4. List all flows defined in this module:
#
#    water list cookbook.cli_usage_flow
#
# -------------------------------------------------------------------------
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio


# --- Schemas ---

class TextInput(BaseModel):
    text: str = ""
    uppercase: bool = False


class TransformOutput(BaseModel):
    original: str
    processed: str
    length: int


class MetadataOutput(BaseModel):
    original: str
    processed: str
    length: int
    version: str
    source: str


# --- Tasks ---

def transform_text(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Transform text based on the uppercase flag."""
    data = params["input_data"]
    text = data.get("text", "")
    if data.get("uppercase", False):
        processed = text.upper()
    else:
        processed = text.lower()
    return {
        "original": text,
        "processed": processed,
        "length": len(text),
    }


def add_metadata(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Append metadata to the result."""
    data = params["input_data"]
    return {
        **data,
        "version": "1.0",
        "source": "cli_usage_flow",
    }


transform_task = create_task(
    id="transform",
    description="Transform text based on flags",
    input_schema=TextInput,
    output_schema=TransformOutput,
    execute=transform_text,
)

metadata_task = create_task(
    id="metadata",
    description="Attach metadata to output",
    input_schema=TransformOutput,
    output_schema=MetadataOutput,
    execute=add_metadata,
)


# --- Flow ---

process_flow = Flow(
    id="text_processor",
    description="Transform text and attach metadata",
    version="1.0.0",
)
process_flow.then(transform_task).then(metadata_task).register()


# --- Direct execution ---

async def main():
    result = await process_flow.run({"text": "hello world", "uppercase": True})
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
