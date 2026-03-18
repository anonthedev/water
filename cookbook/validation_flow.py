"""
Validation Flow Example: Schema-Validated Order Processing

This example demonstrates tasks with validate_schema=True that validate
input and output data against Pydantic models at runtime. Shows both
successful validation and what happens when validation fails.

Usage:
    python cookbook/validation_flow.py
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any
import asyncio

# Data schemas
class OrderInput(BaseModel):
    product_id: str
    quantity: int
    customer_email: str

class PricedOrder(BaseModel):
    product_id: str
    quantity: int
    customer_email: str
    unit_price: float
    total: float

class OrderConfirmation(BaseModel):
    order_id: str
    product_id: str
    quantity: int
    customer_email: str
    total: float
    confirmed: bool

# Step 1: Look up pricing
def price_lookup(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Look up unit price and compute total."""
    data = params["input_data"]
    prices = {"SKU-001": 29.99, "SKU-002": 49.99, "SKU-003": 9.99}
    unit_price = prices.get(data["product_id"], 0.0)
    return {
        "product_id": data["product_id"],
        "quantity": data["quantity"],
        "customer_email": data["customer_email"],
        "unit_price": unit_price,
        "total": round(unit_price * data["quantity"], 2),
    }

# Step 2: Confirm order
def confirm_order(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Generate an order confirmation."""
    data = params["input_data"]
    return {
        "order_id": f"ORD-{data['product_id']}-{data['quantity']}",
        "product_id": data["product_id"],
        "quantity": data["quantity"],
        "customer_email": data["customer_email"],
        "total": data["total"],
        "confirmed": True,
    }

# Create tasks with schema validation enabled
price_task = create_task(
    id="price_lookup",
    description="Look up product price and compute total",
    input_schema=OrderInput,
    output_schema=PricedOrder,
    execute=price_lookup,
    validate_schema=True,
)

confirm_task = create_task(
    id="confirm_order",
    description="Confirm the order",
    input_schema=PricedOrder,
    output_schema=OrderConfirmation,
    execute=confirm_order,
    validate_schema=True,
)

# Build and register the flow
order_flow = Flow(id="validated_order", description="Schema-validated order processing")
order_flow.then(price_task).then(confirm_task).register()

async def main():
    """Run the validation flow example."""

    # --- Case 1: Valid input passes validation ---
    print("=== Case 1: Valid Input ===")
    valid_order = {
        "product_id": "SKU-001",
        "quantity": 3,
        "customer_email": "buyer@example.com",
    }
    try:
        result = await order_flow.run(valid_order)
        print(f"  Order confirmed: {result}")
        print("  flow completed successfully!\n")
    except Exception as e:
        print(f"  ERROR - {e}\n")

    # --- Case 2: Invalid input fails validation ---
    print("=== Case 2: Invalid Input (missing required field) ===")
    invalid_order = {
        "product_id": "SKU-002",
        # missing 'quantity' and 'customer_email'
    }
    try:
        result = await order_flow.run(invalid_order)
        print(f"  Order confirmed: {result}")
    except Exception as e:
        print(f"  Caught validation error: {type(e).__name__}: {e}\n")

    # --- Case 3: Wrong type fails validation ---
    print("=== Case 3: Invalid Input (wrong type) ===")
    wrong_type_order = {
        "product_id": "SKU-003",
        "quantity": "not-a-number",
        "customer_email": "buyer@example.com",
    }
    try:
        result = await order_flow.run(wrong_type_order)
        print(f"  Order confirmed: {result}")
    except Exception as e:
        print(f"  Caught validation error: {type(e).__name__}: {e}\n")

    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
