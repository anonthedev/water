"""
Dry Run Flow Example: Validating Before Execution

This example demonstrates how to use dry_run() to validate a complex flow's
structure and data shape without actually executing any tasks. Useful for
catching schema mismatches, invalid branch conditions, and DAG cycle errors
before committing to a full run.
"""

from water.core import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio


# Data schemas
class OrderInput(BaseModel):
    order_id: str
    amount: float
    currency: str

class ValidationResult(BaseModel):
    order_id: str
    amount: float
    is_valid: bool

class PaymentResult(BaseModel):
    order_id: str
    charged: bool
    transaction_id: str

class NotificationResult(BaseModel):
    order_id: str
    notified: bool


# Tasks
validate_order = create_task(
    id="validate_order",
    description="Validate order data",
    input_schema=OrderInput,
    output_schema=ValidationResult,
    execute=lambda params, ctx: {
        "order_id": params["input_data"]["order_id"],
        "amount": params["input_data"]["amount"],
        "is_valid": params["input_data"]["amount"] > 0,
    },
)

process_payment = create_task(
    id="process_payment",
    description="Charge the customer",
    input_schema=ValidationResult,
    output_schema=PaymentResult,
    execute=lambda params, ctx: {
        "order_id": params["input_data"]["order_id"],
        "charged": True,
        "transaction_id": "txn_abc123",
    },
)

send_confirmation = create_task(
    id="send_confirmation",
    description="Send order confirmation email",
    input_schema=PaymentResult,
    output_schema=NotificationResult,
    execute=lambda params, ctx: {
        "order_id": params["input_data"]["order_id"],
        "notified": True,
    },
)

send_failure_notice = create_task(
    id="send_failure_notice",
    description="Send failure notification",
    input_schema=ValidationResult,
    output_schema=NotificationResult,
    execute=lambda params, ctx: {
        "order_id": params["input_data"]["order_id"],
        "notified": True,
    },
)

# Build a complex flow: validate -> branch on validity -> notify
order_flow = Flow(id="order_pipeline", description="Order processing with dry run validation")
order_flow.then(validate_order) \
    .branch([
        (lambda data: data.get("is_valid", False), process_payment),
        (lambda data: not data.get("is_valid", True), send_failure_notice),
    ]) \
    .then(send_confirmation) \
    .register()


async def main():
    """Validate the flow with dry_run before executing."""

    # Good input: matches OrderInput schema
    good_input = {"order_id": "ORD-001", "amount": 99.99, "currency": "USD"}

    print("=== Dry Run with valid input ===")
    report = await order_flow.dry_run(good_input)
    print(f"Flow: {report['flow_id']}")
    print(f"Valid: {report['valid']}")
    for node in report["nodes"]:
        print(f"  Node {node['index']}: type={node['type']}, valid={node.get('input_valid')}")
        if node.get("branches"):
            for b in node["branches"]:
                print(f"    Branch -> {b['task_id']}: matches={b['condition_matches']}")

    # Bad input: missing required fields
    bad_input = {"order_id": "ORD-002"}

    print("\n=== Dry Run with invalid input ===")
    report = await order_flow.dry_run(bad_input)
    print(f"Flow: {report['flow_id']}")
    print(f"Valid: {report['valid']}")
    for node in report["nodes"]:
        print(f"  Node {node['index']}: type={node['type']}, valid={node.get('input_valid')}")
        for err in node.get("errors", []):
            print(f"    ERROR: {err}")

    # Only run if dry_run passes
    if report["valid"]:
        result = await order_flow.run(good_input)
        print(f"\nExecution result: {result}")
    else:
        print("\nSkipping execution due to dry run errors.")


if __name__ == "__main__":
    asyncio.run(main())
