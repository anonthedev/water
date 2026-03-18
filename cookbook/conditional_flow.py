"""
Conditional Flow Example: Selective Pipeline Steps

This example demonstrates conditional task execution using the `when`
parameter on .then(). Tasks are skipped when the condition returns False,
and the data passes through unchanged to the next step in the pipeline.
"""

from water import Flow, create_task
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio


# Data schemas
class CustomerOrder(BaseModel):
    customer_id: str
    amount: float
    is_premium: bool
    needs_fraud_check: bool


class FraudResult(BaseModel):
    customer_id: str
    amount: float
    is_premium: bool
    needs_fraud_check: bool
    fraud_cleared: bool


class DiscountResult(BaseModel):
    customer_id: str
    amount: float
    is_premium: bool
    needs_fraud_check: bool
    fraud_cleared: bool
    discount_applied: Optional[float]


class FinalOrder(BaseModel):
    customer_id: str
    final_amount: float
    fraud_checked: bool
    discount_applied: Optional[float]
    status: str


# Task: Fraud check (only when needs_fraud_check is True)
def fraud_check(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Run fraud detection on the order."""
    data = params["input_data"]
    print(f"  [fraud_check] Running fraud check for customer {data['customer_id']}")
    return {
        **data,
        "fraud_cleared": True,
    }


# Task: Apply premium discount (only for premium customers)
def apply_discount(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Apply a 15% discount for premium customers."""
    data = params["input_data"]
    discount = round(data["amount"] * 0.15, 2)
    print(f"  [apply_discount] Applying ${discount} discount for premium customer")
    return {
        **data,
        "discount_applied": discount,
    }


# Task: Finalize the order (always runs)
def finalize_order(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Produce the final order summary."""
    data = params["input_data"]
    discount = data.get("discount_applied") or 0.0
    fraud_checked = data.get("fraud_cleared", False)
    final_amount = round(data["amount"] - discount, 2)
    return {
        "customer_id": data["customer_id"],
        "final_amount": final_amount,
        "fraud_checked": fraud_checked,
        "discount_applied": data.get("discount_applied"),
        "status": "confirmed",
    }


# Create tasks
fraud_task = create_task(
    id="fraud_check",
    description="Run fraud detection",
    input_schema=CustomerOrder,
    output_schema=FraudResult,
    execute=fraud_check,
)

discount_task = create_task(
    id="apply_discount",
    description="Apply premium customer discount",
    input_schema=FraudResult,
    output_schema=DiscountResult,
    execute=apply_discount,
)

finalize_task = create_task(
    id="finalize",
    description="Finalize the order",
    input_schema=DiscountResult,
    output_schema=FinalOrder,
    execute=finalize_order,
)

# Build the flow with conditional steps
order_flow = Flow(id="conditional_order", description="Order pipeline with conditional steps")
order_flow.then(fraud_task, when=lambda data: data.get("needs_fraud_check", False))\
    .then(discount_task, when=lambda data: data.get("is_premium", False))\
    .then(finalize_task)\
    .register()


async def main():
    """Run the conditional flow example with different order types."""

    # Order 1: Premium customer needing fraud check
    premium_order = {
        "customer_id": "CUST-100",
        "amount": 250.00,
        "is_premium": True,
        "needs_fraud_check": True,
    }

    # Order 2: Regular customer, no fraud check needed
    regular_order = {
        "customer_id": "CUST-200",
        "amount": 75.00,
        "is_premium": False,
        "needs_fraud_check": False,
    }

    try:
        print("=== Premium Order (fraud check + discount) ===")
        result1 = await order_flow.run(premium_order)
        print(f"  Final: ${result1['final_amount']}, fraud_checked={result1['fraud_checked']}, "
              f"discount={result1['discount_applied']}\n")

        print("=== Regular Order (both steps skipped) ===")
        result2 = await order_flow.run(regular_order)
        print(f"  Final: ${result2['final_amount']}, fraud_checked={result2['fraud_checked']}, "
              f"discount={result2['discount_applied']}")

        print("flow completed successfully!")
    except Exception as e:
        print(f"ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(main())
