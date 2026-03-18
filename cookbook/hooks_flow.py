"""
Hooks Flow Example: Lifecycle Event Logging

This example demonstrates how to use flow lifecycle hooks to log task and
flow events. Hooks are registered via flow.hooks.on("event_name", callback)
and fire automatically during execution, enabling observability without
modifying task logic.
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio


# Data schemas
class OrderRequest(BaseModel):
    order_id: str
    item: str
    quantity: int


class ValidatedOrder(BaseModel):
    order_id: str
    item: str
    quantity: int
    is_valid: bool


class FulfilledOrder(BaseModel):
    order_id: str
    item: str
    quantity: int
    fulfilled: bool
    tracking_id: str


# Hook callbacks
def on_flow_start(flow_id, input_data):
    print(f"[HOOK] Flow '{flow_id}' started with input: {input_data}")


def on_flow_complete(flow_id, output_data):
    print(f"[HOOK] Flow '{flow_id}' completed with output: {output_data}")


def on_flow_error(flow_id, error):
    print(f"[HOOK] Flow '{flow_id}' encountered error: {error}")


def on_task_start(task_id, input_data, context):
    print(f"  [HOOK] Task '{task_id}' starting")


def on_task_complete(task_id, input_data, output_data, context):
    print(f"  [HOOK] Task '{task_id}' completed successfully")


def on_task_error(task_id, input_data, error, context):
    print(f"  [HOOK] Task '{task_id}' failed with error: {error}")


# Task: Validate order
def validate_order(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Check that the order has a valid quantity."""
    data = params["input_data"]
    is_valid = data["quantity"] > 0
    return {
        "order_id": data["order_id"],
        "item": data["item"],
        "quantity": data["quantity"],
        "is_valid": is_valid,
    }


# Task: Fulfill order
def fulfill_order(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Process and fulfill the validated order."""
    data = params["input_data"]
    return {
        "order_id": data["order_id"],
        "item": data["item"],
        "quantity": data["quantity"],
        "fulfilled": data["is_valid"],
        "tracking_id": f"TRK-{data['order_id']}" if data["is_valid"] else "",
    }


# Create tasks
validate_task = create_task(
    id="validate_order",
    description="Validate the incoming order",
    input_schema=OrderRequest,
    output_schema=ValidatedOrder,
    execute=validate_order,
)

fulfill_task = create_task(
    id="fulfill_order",
    description="Fulfill the validated order",
    input_schema=ValidatedOrder,
    output_schema=FulfilledOrder,
    execute=fulfill_order,
)

# Build the flow and register hooks
order_flow = Flow(id="order_processing", description="Order pipeline with lifecycle hooks")

order_flow.hooks.on("on_flow_start", on_flow_start)
order_flow.hooks.on("on_flow_complete", on_flow_complete)
order_flow.hooks.on("on_flow_error", on_flow_error)
order_flow.hooks.on("on_task_start", on_task_start)
order_flow.hooks.on("on_task_complete", on_task_complete)
order_flow.hooks.on("on_task_error", on_task_error)

order_flow.then(validate_task)\
    .then(fulfill_task)\
    .register()


async def main():
    """Run the hooks example."""

    order = {
        "order_id": "ORD-42",
        "item": "Mechanical Keyboard",
        "quantity": 2,
    }

    try:
        result = await order_flow.run(order)
        print(f"\nFinal result: tracking_id={result['tracking_id']}, fulfilled={result['fulfilled']}")
        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
