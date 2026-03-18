"""
Cookbook: Generating Mermaid diagrams from Water flow definitions.

This example builds a complex flow with sequential, parallel, branch,
loop, and map nodes, then calls `flow.visualize()` to produce a
Mermaid flowchart string you can paste into any Mermaid-compatible
renderer (GitHub markdown, Mermaid Live Editor, etc.).
"""

import asyncio
from pydantic import BaseModel
from water import create_task, Flow


# -- Schemas ------------------------------------------------------------------

class NumberInput(BaseModel):
    value: int = 0

class NumberOutput(BaseModel):
    value: int = 0

class ListInput(BaseModel):
    items: list = []

class ListOutput(BaseModel):
    items: list = []


# -- Tasks --------------------------------------------------------------------

validate_task = create_task(
    id="validate",
    description="Validate the input",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=lambda params, ctx: {"value": params["input_data"]["value"]},
)

enrich_task = create_task(
    id="enrich",
    description="Enrich the data",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1},
)

transform_a = create_task(
    id="transform_a",
    description="Transform path A",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=lambda params, ctx: {"value": params["input_data"]["value"] * 2},
)

transform_b = create_task(
    id="transform_b",
    description="Transform path B",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=lambda params, ctx: {"value": params["input_data"]["value"] * 3},
)

increment_task = create_task(
    id="increment",
    description="Increment value by 1",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=lambda params, ctx: {"value": params["input_data"]["value"] + 1},
)

process_item = create_task(
    id="process_item",
    description="Process a single item",
    input_schema=ListInput,
    output_schema=ListOutput,
    execute=lambda params, ctx: {"items": params["input_data"].get("items", [])},
)

finalize_task = create_task(
    id="finalize",
    description="Finalize output",
    input_schema=NumberInput,
    output_schema=NumberOutput,
    execute=lambda params, ctx: {"value": params["input_data"]["value"]},
)


# -- Condition functions ------------------------------------------------------

def is_large(data):
    return data.get("value", 0) > 100

def is_small(data):
    return data.get("value", 0) <= 100

def needs_more(data):
    return data.get("value", 0) < 10


# -- Build the flow -----------------------------------------------------------

flow = Flow(id="demo_pipeline", description="A complex demo pipeline")

flow.then(validate_task)                          # sequential
flow.parallel([transform_a, transform_b])         # parallel fork/join
flow.branch([(is_large, enrich_task),             # conditional branch
              (is_small, increment_task)])
flow.loop(needs_more, increment_task)             # loop with condition
flow.map(process_item, over="items")              # map over list
flow.then(finalize_task)                          # sequential

flow.register()

# -- Generate and print the diagram -------------------------------------------

diagram = flow.visualize()

print("Copy the diagram below into https://mermaid.live or a GitHub markdown block:\n")
print("```mermaid")
print(diagram)
print("```")
