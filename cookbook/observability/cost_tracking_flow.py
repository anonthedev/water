"""
Cost Tracking Flow Example

Demonstrates how to use the CostTracker middleware to monitor token usage
and accumulated cost across a multi-step flow.  The example simulates two
LLM calls — a summarisation step and a review step — with mock token usage
embedded in each task's result.
"""

import asyncio

from water.core import Flow, create_task
from water.observability.cost import CostTracker, TokenUsage
from pydantic import BaseModel


# --- Schemas ----------------------------------------------------------------

class TextInput(BaseModel):
    text: str


class LLMOutput(BaseModel):
    text: str
    model: str
    usage: dict  # {"input_tokens": ..., "output_tokens": ...}


# --- Tasks ------------------------------------------------------------------

summarise_task = create_task(
    id="summarise",
    description="Summarise the input text (simulated LLM call)",
    input_schema=TextInput,
    output_schema=LLMOutput,
    execute=lambda payload, ctx: {
        "text": "This is a short summary.",
        "model": "gpt-4o",
        "usage": {"input_tokens": 800, "output_tokens": 120},
    },
)

review_task = create_task(
    id="review",
    description="Review the summary for accuracy (simulated LLM call)",
    input_schema=TextInput,
    output_schema=LLMOutput,
    execute=lambda payload, ctx: {
        "text": "Summary looks accurate.",
        "model": "gpt-4o-mini",
        "usage": {"input_tokens": 200, "output_tokens": 50},
    },
)


# --- Flow -------------------------------------------------------------------

async def main():
    # Create a cost tracker with a generous budget
    tracker = CostTracker(budget_limit=1.00, on_budget_exceeded="warn")

    flow = Flow(id="cost_demo", description="Cost tracking demo flow")
    flow.use(tracker).then(summarise_task).then(review_task).register()

    print("Running flow...\n")
    result = await flow.run({"text": "Water is an agent harness framework."})

    # Print the cost summary
    summary = tracker.get_summary()
    print(summary.summary())
    print()

    # Serialised form (useful for logging / dashboards)
    print("Serialised summary:")
    for key, value in summary.to_dict().items():
        print(f"  {key}: {value}")

    # --- Manual recording example ---
    print("\n--- Manual recording ---")
    tracker.reset()
    tracker.record("custom_call", "claude-sonnet-4-20250514", TokenUsage(5000, 2000))
    tracker.record("custom_call_2", "claude-opus-4-20250514", TokenUsage(3000, 1000))
    print(tracker.get_summary().summary())


if __name__ == "__main__":
    asyncio.run(main())
