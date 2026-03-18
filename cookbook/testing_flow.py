"""
Testing Flow Example: Unit Testing with MockTask and FlowTestRunner

This example demonstrates how to use Water's built-in testing utilities
to write fast, deterministic unit tests for flows without real side effects.
"""

import asyncio
from pydantic import BaseModel
from water.core import Flow, create_task
from water.utils.testing import MockTask, FlowTestRunner


# --- Schemas ---

class OrderInput(BaseModel):
    item: str
    quantity: int

class PricedOrder(BaseModel):
    item: str
    quantity: int
    total: float

class ShippedOrder(BaseModel):
    item: str
    quantity: int
    total: float
    tracking_id: str


async def main():
    print("=== Testing Flow with MockTask & FlowTestRunner ===\n")

    # ----------------------------------------------------------------
    # 1. Replace real tasks with MockTask for isolated testing
    # ----------------------------------------------------------------

    # Instead of calling a pricing API, return a fixed price
    pricing_mock = MockTask(
        id="pricing",
        return_value={"item": "widget", "quantity": 3, "total": 29.97},
        input_schema=OrderInput,
        output_schema=PricedOrder,
    )

    # Instead of calling a shipping service, return a fixed tracking ID
    shipping_mock = MockTask(
        id="shipping",
        return_value={
            "item": "widget",
            "quantity": 3,
            "total": 29.97,
            "tracking_id": "TRACK-001",
        },
        input_schema=PricedOrder,
        output_schema=ShippedOrder,
    )

    # Build and register the flow
    order_flow = Flow(id="order_pipeline", description="Price then ship an order")
    order_flow.then(pricing_mock).then(shipping_mock).register()

    # ----------------------------------------------------------------
    # 2. Use FlowTestRunner for convenient assertions
    # ----------------------------------------------------------------

    runner = FlowTestRunner(order_flow)
    await runner.run({"item": "widget", "quantity": 3})

    runner.assert_completed()
    runner.assert_result_contains("tracking_id", "TRACK-001")
    runner.assert_result_equals({
        "item": "widget",
        "quantity": 3,
        "total": 29.97,
        "tracking_id": "TRACK-001",
    })

    print("[PASS] Flow completed with expected result")

    # ----------------------------------------------------------------
    # 3. Verify that tasks were called with the right data
    # ----------------------------------------------------------------

    pricing_mock.assert_called()
    pricing_mock.assert_call_count(1)
    pricing_mock.assert_called_with({"item": "widget", "quantity": 3})
    print("[PASS] Pricing task received correct input")

    shipping_mock.assert_called()
    shipping_mock.assert_call_count(1)
    print("[PASS] Shipping task was called once")

    # ----------------------------------------------------------------
    # 4. Test error paths with side_effect
    # ----------------------------------------------------------------

    failing_mock = MockTask(
        id="failing_pricing",
        side_effect=ValueError("Price lookup failed"),
    )

    error_flow = Flow(id="error_pipeline", description="Flow that should fail")
    error_flow.then(failing_mock).register()

    error_runner = FlowTestRunner(error_flow)
    err = await error_runner.run_expecting_error(
        {"item": "widget", "quantity": 1},
        error_type=ValueError,
    )

    error_runner.assert_failed()
    print(f"[PASS] Flow raised expected error: {err}")

    # ----------------------------------------------------------------
    # 5. Dynamic side_effect for data-driven responses
    # ----------------------------------------------------------------

    dynamic_mock = MockTask(
        id="dynamic_pricing",
        side_effect=lambda data: {
            "item": data["item"],
            "quantity": data["quantity"],
            "total": data["quantity"] * 9.99,
        },
    )

    dynamic_flow = Flow(id="dynamic_pipeline", description="Flow with dynamic mock")
    dynamic_flow.then(dynamic_mock).register()

    dynamic_runner = FlowTestRunner(dynamic_flow)
    await dynamic_runner.run({"item": "gadget", "quantity": 5})

    dynamic_runner.assert_completed()
    dynamic_runner.assert_result_contains("total", 49.95)
    print("[PASS] Dynamic side_effect computed correct total")

    # ----------------------------------------------------------------
    # 6. Reset tracking between test scenarios
    # ----------------------------------------------------------------

    pricing_mock.reset()
    pricing_mock.assert_call_count(0)
    print("[PASS] Reset cleared call tracking")

    print("\nAll assertions passed!")


if __name__ == "__main__":
    asyncio.run(main())
