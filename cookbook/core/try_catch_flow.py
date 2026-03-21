"""
Cookbook: Try-Catch-Finally Error Handling in Water Flows

Demonstrates Feature #27 — Conditional Sub-flow Composition using
try_catch() and on_error() for structured error handling.
"""

import asyncio
from pydantic import BaseModel
from typing import Dict, Any

from water.core.flow import Flow
from water.core.task import Task


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenericInput(BaseModel):
    data: Dict[str, Any] = {}

class GenericOutput(BaseModel):
    data: Dict[str, Any] = {}


def make_task(task_id, fn, description=None):
    return Task(
        id=task_id,
        description=description or task_id,
        input_schema=GenericInput,
        output_schema=GenericOutput,
        execute=fn,
    )


# ---------------------------------------------------------------------------
# Example 1: Basic try-catch
# ---------------------------------------------------------------------------

async def fetch_data(params, context):
    """Simulate an API call that might fail."""
    data = params["input_data"]
    if data.get("simulate_error"):
        raise ConnectionError("API unreachable")
    return {**data, "fetched": True, "payload": [1, 2, 3]}


async def use_cached_data(params, context):
    """Fallback: return cached data when the API is down."""
    return {
        "fetched": False,
        "payload": [0, 0, 0],
        "error": params["input_data"].get("_error", "unknown"),
    }


async def example_basic_try_catch():
    print("=== Example 1: Basic try-catch ===")

    flow = Flow(id="basic_try_catch")
    flow.try_catch(
        make_task("fetch", fetch_data),
        catch_handler=make_task("cached", use_cached_data),
    ).register()

    # Success path
    result = await flow.run({"simulate_error": False})
    print(f"  Success: {result}")

    # Failure path
    result = await flow.run({"simulate_error": True})
    print(f"  Failure (caught): {result}")
    print()


# ---------------------------------------------------------------------------
# Example 2: Try-catch-finally with cleanup
# ---------------------------------------------------------------------------

cleanup_log = []

async def open_connection(params, context):
    return {**params["input_data"], "connection": "open"}


async def query_database(params, context):
    if params["input_data"].get("bad_query"):
        raise RuntimeError("SQL syntax error")
    return {**params["input_data"], "rows": [{"id": 1}, {"id": 2}]}


async def handle_db_error(params, context):
    return {"rows": [], "db_error": params["input_data"].get("_error")}


async def close_connection(params, context):
    cleanup_log.append("connection closed")
    return params["input_data"]


async def example_try_catch_finally():
    print("=== Example 2: Try-catch-finally ===")
    cleanup_log.clear()

    flow = Flow(id="db_flow")
    flow.then(make_task("open", open_connection))
    flow.try_catch(
        make_task("query", query_database),
        catch_handler=make_task("db_err", handle_db_error),
        finally_handler=make_task("close", close_connection),
    )
    flow.register()

    result = await flow.run({"bad_query": False})
    print(f"  Success: rows={result.get('rows')}, cleanup={cleanup_log}")

    cleanup_log.clear()
    result = await flow.run({"bad_query": True})
    print(f"  Failure: error={result.get('db_error')}, cleanup={cleanup_log}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Global on_error handler
# ---------------------------------------------------------------------------

async def process_order(params, context):
    data = params["input_data"]
    if data.get("amount", 0) <= 0:
        raise ValueError("Invalid order amount")
    return {**data, "status": "processed"}


async def charge_payment(params, context):
    return {**params["input_data"], "charged": True}


async def handle_any_error(params, context):
    return {
        "status": "failed",
        "error": params["input_data"].get("_error"),
        "error_type": params["input_data"].get("_error_type"),
    }


async def example_on_error():
    print("=== Example 3: Global on_error ===")

    flow = Flow(id="order_flow")
    flow.then(make_task("process", process_order))
    flow.then(make_task("charge", charge_payment))
    flow.on_error(make_task("err_handler", handle_any_error))
    flow.register()

    result = await flow.run({"order_id": "A1", "amount": 50})
    print(f"  Valid order: {result}")

    result = await flow.run({"order_id": "A2", "amount": -1})
    print(f"  Invalid order: {result}")
    print()


# ---------------------------------------------------------------------------
# Example 4: Callable catch handler (no Task needed)
# ---------------------------------------------------------------------------

async def example_callable_handler():
    print("=== Example 4: Callable catch handler ===")

    def simple_handler(error, context):
        return {"recovered": True, "message": f"Handled: {error}"}

    async def risky_task(params, context):
        raise RuntimeError("something broke")

    flow = Flow(id="callable_catch")
    flow.try_catch(
        make_task("risky", risky_task),
        catch_handler=simple_handler,
    ).register()

    result = await flow.run({})
    print(f"  Result: {result}")
    print()


# ---------------------------------------------------------------------------
# Example 5: Multi-step try block
# ---------------------------------------------------------------------------

async def validate_input(params, context):
    data = params["input_data"]
    if "name" not in data:
        raise ValueError("Missing 'name' field")
    return {**data, "validated": True}


async def enrich_data(params, context):
    return {**params["input_data"], "enriched": True}


async def save_record(params, context):
    return {**params["input_data"], "saved": True}


async def rollback(params, context):
    return {"rolled_back": True, "reason": params["input_data"].get("_error")}


async def example_multi_step_try():
    print("=== Example 5: Multi-step try block ===")

    flow = Flow(id="pipeline")
    flow.try_catch(
        [
            make_task("validate", validate_input),
            make_task("enrich", enrich_data),
            make_task("save", save_record),
        ],
        catch_handler=make_task("rollback", rollback),
    ).register()

    result = await flow.run({"name": "Alice"})
    print(f"  Success: {result}")

    result = await flow.run({})  # Missing 'name' triggers validation error
    print(f"  Rolled back: {result}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    await example_basic_try_catch()
    await example_try_catch_finally()
    await example_on_error()
    await example_callable_handler()
    await example_multi_step_try()


if __name__ == "__main__":
    asyncio.run(main())
