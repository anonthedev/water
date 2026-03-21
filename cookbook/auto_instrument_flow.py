"""
Cookbook: Auto-Instrumentation with Water Flows
================================================

This example demonstrates how to use the auto-instrumentation module
to observe and trace Water flow execution -- with or without
OpenTelemetry installed.
"""

import asyncio
from water.observability import auto_instrument, AutoInstrumentor, InstrumentationConfig


# ---------------------------------------------------------------------------
# 1. Basic auto-instrumentation setup (one-liner)
# ---------------------------------------------------------------------------

instrumentor = auto_instrument(
    service_name="my-water-app",
    capture_input=True,
    capture_output=True,
)

print(f"Instrumentation enabled: {instrumentor._enabled}")
print(f"OpenTelemetry available: {instrumentor.is_otel_available}")


# ---------------------------------------------------------------------------
# 2. Simulating task execution with instrumentation hooks
# ---------------------------------------------------------------------------

async def run_pipeline():
    """Simulate a flow with three sequential tasks."""

    tasks = [
        ("extract", {"source": "database", "query": "SELECT * FROM users"}),
        ("transform", {"rows": 150, "format": "normalized"}),
        ("load", {"destination": "warehouse", "batch_size": 50}),
    ]

    results = {}
    for task_id, data in tasks:
        # before_task hook
        await instrumentor.before_task(task_id, data, context=None)

        # ... actual task work would happen here ...
        result = {"status": "success", "task": task_id, "records": 150}

        # after_task hook
        await instrumentor.after_task(task_id, data, result, context=None)
        results[task_id] = result

    return results


results = asyncio.run(run_pipeline())


# ---------------------------------------------------------------------------
# 3. Inspecting collected spans
# ---------------------------------------------------------------------------

collector = instrumentor.get_collector()
spans = collector.get_spans()

print(f"\nCollected {len(spans)} spans:\n")
for span in spans:
    print(f"  [{span.kind}] {span.name}")
    print(f"    duration : {span.duration_ms:.2f} ms")
    print(f"    status   : {span.status}")
    print(f"    attributes: {span.attributes}")
    print()


# ---------------------------------------------------------------------------
# 4. Advanced: custom config with endpoint (OTel export)
# ---------------------------------------------------------------------------

# When OpenTelemetry is installed and an endpoint is provided, spans are
# automatically exported via OTLP. Without OTel, the collector still
# records everything locally for inspection.

advanced = AutoInstrumentor(
    config=InstrumentationConfig(
        service_name="water-prod",
        endpoint="http://localhost:4317",
        sample_rate=0.5,
        capture_input=True,
        capture_output=True,
        custom_attributes={"env": "staging", "version": "1.2.0"},
    )
)
advanced.enable()

print("Advanced instrumentor configured.")
print(f"  service : {advanced.config.service_name}")
print(f"  endpoint: {advanced.config.endpoint}")
print(f"  rate    : {advanced.config.sample_rate}")
