"""
Dead Letter Queue (DLQ) Flow Example: Order Processing with Failure Capture

This example demonstrates how to use a DLQ to capture failed task executions
for later inspection and replay. Orders that fail validation or processing
are pushed to the DLQ instead of being silently lost.
"""

from water import Flow, create_task, InMemoryDLQ
from pydantic import BaseModel
from typing import Dict, Any
import asyncio


# --- Schemas ---

class OrderInput(BaseModel):
    order_id: str
    amount: float
    customer: str


class OrderOutput(BaseModel):
    order_id: str
    status: str
    message: str


# --- Tasks ---

def validate_order(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Validate the order. Rejects orders over $1000."""
    inp = params["input_data"]
    if inp["amount"] > 1000:
        raise ValueError(f"Order {inp['order_id']} exceeds maximum amount: ${inp['amount']}")
    return {
        "order_id": inp["order_id"],
        "status": "validated",
        "message": f"Order {inp['order_id']} validated for ${inp['amount']}",
    }


def process_payment(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Process payment. Fails for customer 'bad_card'."""
    inp = params["input_data"]
    if inp.get("customer") == "bad_card":
        raise RuntimeError(f"Payment declined for customer '{inp['customer']}'")
    return {
        "order_id": inp["order_id"],
        "status": "paid",
        "message": f"Payment of ${inp.get('amount', '?')} processed for {inp.get('customer', '?')}",
    }


validate_task = create_task(
    id="validate_order",
    description="Validate incoming order",
    input_schema=OrderInput,
    output_schema=OrderOutput,
    execute=validate_order,
)

payment_task = create_task(
    id="process_payment",
    description="Process payment for order",
    input_schema=OrderInput,
    output_schema=OrderOutput,
    execute=process_payment,
    retry_count=1,  # retry once before giving up
    retry_delay=0.1,
)


# --- Build the flow with a DLQ ---

dlq = InMemoryDLQ()

flow = Flow(id="order_processing", description="Process customer orders with DLQ")
flow.dlq = dlq
flow.then(validate_task).then(payment_task).register()


async def main():
    print("=== Dead Letter Queue Flow: Order Processing ===\n")

    # --- Process a batch of orders, some will fail ---
    orders = [
        {"order_id": "ORD-001", "amount": 50.0, "customer": "alice"},
        {"order_id": "ORD-002", "amount": 1500.0, "customer": "bob"},      # too expensive
        {"order_id": "ORD-003", "amount": 25.0, "customer": "bad_card"},    # payment fails
        {"order_id": "ORD-004", "amount": 99.0, "customer": "charlie"},
    ]

    for order in orders:
        try:
            result = await flow.run(order)
            print(f"  [OK] {order['order_id']}: {result['message']}")
        except Exception as e:
            print(f"  [FAIL] {order['order_id']}: {e}")

    # --- Inspect the DLQ ---
    print(f"\n--- Dead Letter Queue ({await dlq.size()} items) ---")
    for letter in await dlq.list_letters():
        print(f"  Task: {letter.task_id}")
        print(f"  Error: {letter.error_type}: {letter.error}")
        print(f"  Input: {letter.input_data}")
        print(f"  Attempts: {letter.attempts}")
        print(f"  Timestamp: {letter.timestamp}")
        print()

    # --- Replay: pop a letter and retry ---
    print("--- Replaying first dead letter ---")
    letter = await dlq.pop()
    if letter:
        print(f"  Retrying task '{letter.task_id}' with input: {letter.input_data}")
        # In a real system you'd fix the issue first, then re-run
        print(f"  (In production, fix the root cause before replaying)")

    print(f"\nRemaining DLQ items: {await dlq.size()}")


if __name__ == "__main__":
    asyncio.run(main())
