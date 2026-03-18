"""
Telemetry Flow Example: Observability with TelemetryManager

This example demonstrates how to attach a TelemetryManager to a flow
for OpenTelemetry-based tracing. Since OTel may not be installed, the
example gracefully falls back to noop mode and shows how to check
whether tracing is actually active.

Usage:
    python cookbook/telemetry_flow.py
"""

from water.core import Flow, create_task
from water.observability import TelemetryManager, is_otel_available
from pydantic import BaseModel
from typing import Dict, Any
import asyncio

# Data schemas
class MetricsInput(BaseModel):
    service_name: str
    region: str

class CollectedMetrics(BaseModel):
    service_name: str
    region: str
    cpu_percent: float
    memory_mb: int

class HealthReport(BaseModel):
    service_name: str
    region: str
    cpu_percent: float
    memory_mb: int
    healthy: bool
    recommendation: str

# Step 1: Collect metrics
def collect_metrics(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Simulate collecting service metrics."""
    data = params["input_data"]
    print(f"  [collect] Gathering metrics for {data['service_name']} in {data['region']}")
    return {
        "service_name": data["service_name"],
        "region": data["region"],
        "cpu_percent": 72.5,
        "memory_mb": 3840,
    }

# Step 2: Analyze health
def analyze_health(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Evaluate whether the service is healthy based on metrics."""
    data = params["input_data"]
    healthy = data["cpu_percent"] < 90 and data["memory_mb"] < 7000
    recommendation = "No action needed." if healthy else "Scale up immediately."
    print(f"  [analyze] healthy={healthy}, recommendation={recommendation}")
    return {
        **data,
        "healthy": healthy,
        "recommendation": recommendation,
    }

# Create tasks
collect_task = create_task(
    id="collect_metrics",
    description="Collect CPU and memory metrics",
    input_schema=MetricsInput,
    output_schema=CollectedMetrics,
    execute=collect_metrics,
)

analyze_task = create_task(
    id="analyze_health",
    description="Analyze service health from metrics",
    input_schema=CollectedMetrics,
    output_schema=HealthReport,
    execute=analyze_health,
)

# Configure telemetry
telemetry = TelemetryManager(enabled=True, tracer_name="water-cookbook")

# Build flow with telemetry attached
health_flow = Flow(id="service_health_check", description="Telemetry-instrumented health check")
health_flow.telemetry = telemetry
health_flow.then(collect_task).then(analyze_task).register()

async def main():
    """Run the telemetry flow example."""
    print("=== Telemetry Flow Example ===\n")

    # Report telemetry status
    otel_installed = is_otel_available()
    print(f"  OpenTelemetry installed: {otel_installed}")
    print(f"  TelemetryManager active: {telemetry.is_active}")
    if not otel_installed:
        print("  (Running in noop mode - install opentelemetry-api to enable tracing)\n")
    else:
        print("  (Tracing is active - spans will be emitted)\n")

    # Demonstrate that the flow works identically with or without OTel
    payload = {
        "service_name": "payment-api",
        "region": "us-east-1",
    }

    try:
        result = await health_flow.run(payload)
        print(f"\n  Result: {result}")
        print("  flow completed successfully!")
    except Exception as e:
        print(f"  ERROR - {e}")

    # Show that telemetry context managers work as noop
    print("\n  --- Manual span demo (noop if OTel not installed) ---")
    with telemetry.flow_span("demo_flow") as span:
        print(f"  flow_span returned: {span}")
        with telemetry.task_span("demo_task", "demo_flow") as task_span:
            print(f"  task_span returned: {task_span}")
            telemetry.set_success(task_span)
    print("  Spans completed without error.")

    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
