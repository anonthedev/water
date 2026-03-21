"""
Cookbook: Webhook, Cron, and Queue Triggered Flows
==================================================

Demonstrates how to use Water triggers to automatically invoke flows
in response to external events.

Usage:
    python cookbook/trigger_flow.py
"""

import asyncio
from typing import Any, Dict

from pydantic import BaseModel

from water import Flow, Task, create_task
from water.triggers import (
    CronTrigger,
    QueueTrigger,
    TriggerRegistry,
    WebhookTrigger,
)


class EventInput(BaseModel):
    source: str = ""

class EventOutput(BaseModel):
    status: str = ""
    source: str = ""
    enriched: bool = False
    processed_by: str = ""


# ---------------------------------------------------------------------------
# 1. Define a simple processing flow
# ---------------------------------------------------------------------------

process_flow = Flow(id="process-event", description="Processes incoming events")


async def _log_event(params, context):
    input_data = params["input_data"]
    print(f"  [log-event] Received: {input_data}")
    return {"status": "logged", **input_data}


log_event = create_task(
    id="log-event",
    description="Logs the incoming event data",
    input_schema=EventInput,
    output_schema=EventOutput,
    execute=_log_event,
    validate_schema=False,
)


async def _enrich_event(params, context):
    input_data = params["input_data"]
    input_data["enriched"] = True
    input_data["processed_by"] = "water-triggers"
    print(f"  [enrich-event] Enriched: {input_data}")
    return input_data


enrich_event = create_task(
    id="enrich-event",
    description="Enriches event with metadata",
    input_schema=EventOutput,
    output_schema=EventOutput,
    execute=_enrich_event,
    validate_schema=False,
)


process_flow.then(log_event).then(enrich_event).register()


# ---------------------------------------------------------------------------
# 2. Set up triggers
# ---------------------------------------------------------------------------

async def main():
    registry = TriggerRegistry()

    # -- Webhook trigger: fires when an HTTP request hits /hooks/github ------
    webhook = WebhookTrigger(
        flow_name="process-event",
        path="/hooks/github",
        secret="my-webhook-secret",
        transform=lambda p: {"source": "github", **p},
    )
    registry.add(webhook)

    # -- Cron trigger: fires every day at midnight ---------------------------
    cron = CronTrigger(
        flow_name="process-event",
        schedule="0 0 * * *",
        input_data={"source": "cron", "report": "daily"},
    )
    registry.add(cron)

    # -- Queue trigger: fires when a message is pushed -----------------------
    queue = QueueTrigger(
        flow_name="process-event",
        transform=lambda p: {"source": "queue", **p},
    )
    registry.add(queue)

    # Start all triggers
    await registry.start_all()
    print(f"Started {registry.count} triggers\n")

    # --- Simulate a webhook request -----------------------------------------
    print("=== Webhook Trigger ===")
    event = await webhook.handle_request({"action": "push", "repo": "water"})
    print(f"  Event ID : {event.trigger_id}")
    print(f"  Payload  : {event.payload}")

    # Run the flow with the webhook payload
    result = await process_flow.run(event.payload)
    print(f"  Result   : {result}\n")

    # --- Simulate a cron tick -----------------------------------------------
    print("=== Cron Trigger ===")
    cron_event = cron.create_event(cron.input_data)
    print(f"  Event ID : {cron_event.trigger_id}")
    print(f"  Payload  : {cron_event.payload}")

    result = await process_flow.run(cron_event.payload)
    print(f"  Result   : {result}\n")

    # --- Simulate queue messages --------------------------------------------
    print("=== Queue Trigger ===")
    await queue.push({"user_id": "u-001", "action": "signup"})
    await queue.push({"user_id": "u-002", "action": "purchase"})

    while queue.pending > 0:
        q_event = await queue.pop()
        print(f"  Event ID : {q_event.trigger_id}")
        print(f"  Payload  : {q_event.payload}")
        result = await process_flow.run(q_event.payload)
        print(f"  Result   : {result}\n")

    # Stop all triggers
    await registry.stop_all()
    print("All triggers stopped.")


if __name__ == "__main__":
    asyncio.run(main())
