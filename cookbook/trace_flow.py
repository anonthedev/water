"""
Trace Visualization Flow Example: Debugging Flow Execution

This example demonstrates Water's tracing system for capturing per-node
timing, I/O, and metadata during flow execution. It shows:
  - TraceCollector for capturing execution traces
  - TraceStore for persisting and querying traces
  - Trace and TraceSpan inspection
  - Querying traces by flow ID, execution ID, and status

NOTE: This example creates mock trace data directly to demonstrate the
      tracing API without running a full flow.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from water.observability.trace import TraceCollector, TraceStore, Trace, TraceSpan


# ---------------------------------------------------------------------------
# Example 1: TraceStore basics (create, query, delete)
# ---------------------------------------------------------------------------

async def example_trace_store():
    """Store and query traces manually."""
    print("=== Example 1: TraceStore Basics ===\n")

    store = TraceStore(max_traces=100)

    # Create a completed trace with spans
    now = datetime.utcnow()
    trace1 = Trace(
        trace_id="trace_001",
        flow_id="data_pipeline",
        execution_id="exec_001",
        status="completed",
        started_at=(now - timedelta(seconds=5)).isoformat(),
        completed_at=now.isoformat(),
        duration_ms=5000,
        input_data={"record_id": "R001", "value": 42},
        output_data={"record_id": "R001", "normalized": 0.042, "category": "low"},
        spans=[
            TraceSpan(
                span_id="span_001a",
                task_id="normalize",
                flow_id="data_pipeline",
                execution_id="exec_001",
                status="completed",
                input_data={"record_id": "R001", "value": 42},
                output_data={"normalized": 0.042},
                started_at=(now - timedelta(seconds=5)).isoformat(),
                completed_at=(now - timedelta(seconds=3)).isoformat(),
                duration_ms=2000,
            ),
            TraceSpan(
                span_id="span_001b",
                task_id="categorize",
                flow_id="data_pipeline",
                execution_id="exec_001",
                status="completed",
                input_data={"normalized": 0.042},
                output_data={"category": "low"},
                started_at=(now - timedelta(seconds=3)).isoformat(),
                completed_at=now.isoformat(),
                duration_ms=3000,
            ),
        ],
    )

    # Create a failed trace
    trace2 = Trace(
        trace_id="trace_002",
        flow_id="data_pipeline",
        execution_id="exec_002",
        status="failed",
        started_at=(now - timedelta(seconds=2)).isoformat(),
        completed_at=(now - timedelta(seconds=1)).isoformat(),
        duration_ms=1000,
        error="ValidationError: missing required field 'value'",
    )

    # Save traces
    store.save(trace1)
    store.save(trace2)

    # Query all traces
    all_traces = store.list_traces()
    print(f"Total traces: {len(all_traces)}")
    for t in all_traces:
        print(f"  {t.trace_id}: {t.status} ({t.duration_ms}ms, {len(t.spans)} spans)")
    print()

    # Query by status
    failed = store.list_traces(status="failed")
    print(f"Failed traces: {len(failed)}")
    if failed:
        print(f"  Error: {failed[0].error}")
    print()

    # Query by flow ID
    pipeline_traces = store.find_by_flow("data_pipeline")
    print(f"Traces for 'data_pipeline': {len(pipeline_traces)}")

    # Query by execution ID
    found = store.find_by_execution("exec_001")
    print(f"Trace for exec_001: {found.trace_id if found else 'not found'}")

    # Get a specific trace
    t = store.get("trace_001")
    print(f"Trace trace_001 status: {t.status}")
    print()


# ---------------------------------------------------------------------------
# Example 2: TraceCollector middleware simulation
# ---------------------------------------------------------------------------

async def example_trace_collector():
    """Simulate using TraceCollector as middleware during flow execution."""
    print("=== Example 2: TraceCollector Middleware ===\n")

    store = TraceStore()
    collector = TraceCollector(store=store)

    # Simulate a mock execution context
    class MockContext:
        execution_id = "exec_100"
        flow_id = "etl_flow"
        initial_input = {"source": "database", "table": "users"}
        attempt_number = 1

    ctx = MockContext()

    # Before task 1: extract
    await collector.before_task("extract", {"source": "database", "table": "users"}, ctx)
    # Simulate some work
    await asyncio.sleep(0.01)
    # After task 1
    await collector.after_task(
        "extract",
        {"source": "database", "table": "users"},
        {"rows": 150, "columns": ["id", "name", "email"]},
        ctx,
    )

    # Before task 2: transform
    await collector.before_task("transform", {"rows": 150}, ctx)
    await asyncio.sleep(0.01)
    await collector.after_task(
        "transform",
        {"rows": 150},
        {"rows": 148, "dropped": 2, "reason": "null values"},
        ctx,
    )

    # Before task 3: load
    await collector.before_task("load", {"rows": 148}, ctx)
    await asyncio.sleep(0.01)
    await collector.after_task(
        "load",
        {"rows": 148},
        {"inserted": 148, "target": "warehouse.users"},
        ctx,
    )

    # Mark trace as completed
    collector.complete_trace(
        "exec_100",
        output={"inserted": 148, "target": "warehouse.users"},
    )

    # Inspect the trace
    trace = store.find_by_execution("exec_100")
    print(f"Trace ID:     {trace.trace_id}")
    print(f"Flow ID:      {trace.flow_id}")
    print(f"Status:       {trace.status}")
    print(f"Duration:     {trace.duration_ms:.1f}ms")
    print(f"Spans:        {len(trace.spans)}")
    print()

    for span in trace.spans:
        print(f"  Span: {span.task_id}")
        print(f"    Status:   {span.status}")
        print(f"    Duration: {span.duration_ms:.1f}ms")
        print(f"    Input:    {span.input_data}")
        print(f"    Output:   {span.output_data}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Trace serialization and inspection
# ---------------------------------------------------------------------------

async def example_trace_inspection():
    """Inspect trace data via to_dict() for export or visualization."""
    print("=== Example 3: Trace Serialization & Inspection ===\n")

    store = TraceStore()
    collector = TraceCollector(store=store)

    class Ctx:
        execution_id = "exec_200"
        flow_id = "ml_pipeline"
        initial_input = {"model": "classifier_v2", "dataset": "test_set"}
        attempt_number = 1

    ctx = Ctx()

    # Simulate a two-step ML pipeline
    await collector.before_task("predict", {"model": "classifier_v2", "samples": 500}, ctx)
    await asyncio.sleep(0.01)
    await collector.after_task("predict", {}, {"predictions": 500, "avg_confidence": 0.87}, ctx)

    await collector.before_task("evaluate", {"predictions": 500}, ctx)
    await asyncio.sleep(0.01)
    await collector.after_task("evaluate", {}, {"accuracy": 0.92, "f1": 0.89}, ctx)

    collector.complete_trace("exec_200", output={"accuracy": 0.92, "f1": 0.89})

    # Serialize for export
    trace = store.find_by_execution("exec_200")
    trace_dict = trace.to_dict()

    print(f"Trace keys:  {list(trace_dict.keys())}")
    print(f"Status:      {trace_dict['status']}")
    print(f"Span count:  {len(trace_dict['spans'])}")
    print()

    for span_dict in trace_dict["spans"]:
        print(f"  {span_dict['task_id']}: status={span_dict['status']}, "
              f"duration={span_dict['duration_ms']:.1f}ms")
    print()

    # Verify the store contents
    all_traces = store.list_traces()
    print(f"Store contains {len(all_traces)} trace(s)")
    store.clear()
    print(f"After clear: {len(store.list_traces())} trace(s)")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_trace_store()
    await example_trace_collector()
    await example_trace_inspection()
    print("All trace examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
