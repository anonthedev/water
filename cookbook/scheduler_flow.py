"""
Cookbook: Scheduling a health-check flow to run every 30 seconds.

This example demonstrates the FlowScheduler, which lets you run
Water flows on a recurring schedule using either a fixed interval
or a cron expression.
"""

import asyncio
from pydantic import BaseModel
from water.core import create_task, Flow
from water.utils.scheduler import FlowScheduler


# ── Models ────────────────────────────────────────────────────────

class HealthInput(BaseModel):
    url: str


class HealthOutput(BaseModel):
    status: str
    message: str


# ── Task ──────────────────────────────────────────────────────────

health_check = create_task(
    id="health_check",
    description="Simulate a health check against a URL",
    input_schema=HealthInput,
    output_schema=HealthOutput,
    execute=lambda params, context: {
        "status": "healthy",
        "message": f"{params['input_data']['url']} is up",
    },
)


# ── Flow ──────────────────────────────────────────────────────────

health_flow = Flow(id="health_check_flow", description="Periodic health check")
health_flow.then(health_check).register()


# ── Run ───────────────────────────────────────────────────────────

async def main():
    scheduler = FlowScheduler()

    # Schedule with a fixed interval (every 30 seconds)
    job_id = scheduler.schedule(
        flow=health_flow,
        input_data={"url": "https://example.com/health"},
        interval_seconds=30,
    )
    print(f"Scheduled job: {job_id}")

    # You can also schedule with a cron expression:
    # scheduler.schedule(
    #     flow=health_flow,
    #     input_data={"url": "https://example.com/health"},
    #     cron_expr="*/5 * * * *",  # every 5 minutes
    # )

    # List all registered jobs
    for job in scheduler.list_jobs():
        print(f"  Job {job['job_id']} — next run: {job['next_run']}")

    # Start the background scheduler
    await scheduler.start()

    # Let it run for a while (in a real app this would run indefinitely)
    print("Scheduler running — press Ctrl+C to stop")
    try:
        await asyncio.sleep(120)  # run for 2 minutes as a demo
    except KeyboardInterrupt:
        pass

    await scheduler.stop()
    print("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
