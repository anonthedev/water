"""
Streaming Agent Flow Example

Demonstrates how to use the streaming agent task system in Water.
Shows:
  - Creating a streaming agent task with MockStreamProvider
  - Using the on_chunk callback for real-time output
  - Collecting the final result as a normal Dict
  - Chaining a streaming agent with a regular task in a Flow

NOTE: This example uses MockStreamProvider so it runs without API keys.
      Replace with OpenAIStreamProvider or AnthropicStreamProvider for
      production use.
"""

import asyncio
from typing import Dict, Any

from pydantic import BaseModel

from water.core import Flow, create_task
from water.agents.streaming import (
    StreamChunk,
    MockStreamProvider,
    create_streaming_agent_task,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TopicInput(BaseModel):
    topic: str


class TopicOutput(BaseModel):
    response: str
    topic: str


class FormattedOutput(BaseModel):
    formatted: str


# ---------------------------------------------------------------------------
# Example 1: Simple streaming with on_chunk callback
# ---------------------------------------------------------------------------

async def simple_streaming_example():
    """Stream tokens from the LLM and print them as they arrive."""
    print("=== Simple Streaming Agent ===\n")

    mock = MockStreamProvider(
        default_response="Water is a lightweight Python workflow framework that makes building AI agent pipelines easy and fun"
    )

    received_chunks = []

    def on_chunk(chunk: StreamChunk):
        """Print each token as it arrives."""
        print(chunk.delta, end="", flush=True)
        received_chunks.append(chunk)

    task = create_streaming_agent_task(
        id="streamer",
        description="Streams an explanation",
        prompt_template="Explain {topic} in one sentence.",
        provider_instance=mock,
        on_chunk=on_chunk,
        input_schema=TopicInput,
    )

    result = await task.execute({"input_data": {"topic": "the Water framework"}}, None)
    print()  # newline after streaming output

    print(f"\nFull response: {result['response']}")
    print(f"Chunks received: {len(received_chunks)}")
    print(f"Last chunk finish_reason: {received_chunks[-1].finish_reason}\n")


# ---------------------------------------------------------------------------
# Example 2: Streaming agent in a Flow
# ---------------------------------------------------------------------------

async def streaming_in_flow_example():
    """Use a streaming agent task inside a Water Flow."""
    print("=== Streaming Agent in a Flow ===\n")

    mock = MockStreamProvider(
        default_response="Use async generators and yield tokens as they arrive from the API"
    )

    tokens_seen = []

    def track_tokens(chunk: StreamChunk):
        tokens_seen.append(chunk.delta)

    agent = create_streaming_agent_task(
        id="advisor",
        description="Gives streaming advice",
        prompt_template="What is the best practice for {topic}?",
        provider_instance=mock,
        on_chunk=track_tokens,
        input_schema=TopicInput,
        output_schema=TopicOutput,
    )

    def format_advice(params, context):
        data = params["input_data"]
        return {
            "formatted": f"[ADVICE on '{data['topic']}']: {data['response']}"
        }

    formatter = create_task(
        id="formatter",
        description="Formats the advice",
        input_schema=TopicOutput,
        output_schema=FormattedOutput,
        execute=format_advice,
    )

    flow = Flow(id="streaming_flow", description="Streaming agent + formatter")
    flow.then(agent).then(formatter).register()

    result = await flow.run({"topic": "streaming LLM responses"})

    print(f"Tokens streamed: {len(tokens_seen)}")
    print(f"Final result: {result['formatted']}\n")


# ---------------------------------------------------------------------------
# Example 3: Multiple streaming agents in sequence
# ---------------------------------------------------------------------------

async def multi_stream_example():
    """Chain two streaming agents together."""
    print("=== Multi-Stream Agent Pipeline ===\n")

    drafter = MockStreamProvider(
        default_response="Draft: Implement retry logic with exponential backoff"
    )
    refiner = MockStreamProvider(
        default_response="Refined: Implement retry logic with exponential backoff and jitter for robustness"
    )

    draft_tokens = []
    refine_tokens = []

    draft_task = create_streaming_agent_task(
        id="drafter",
        description="Drafts a plan",
        prompt_template="Draft a plan for: {topic}",
        provider_instance=drafter,
        on_chunk=lambda c: draft_tokens.append(c.delta),
        input_schema=TopicInput,
    )

    class DraftOutput(BaseModel):
        response: str
        topic: str

    def bridge(params, context):
        data = params["input_data"]
        return {"plan": data["response"]}

    class PlanInput(BaseModel):
        plan: str

    class RefinedOutput(BaseModel):
        response: str
        plan: str

    bridge_task = create_task(
        id="bridge",
        input_schema=DraftOutput,
        output_schema=PlanInput,
        execute=bridge,
    )

    refine_task = create_streaming_agent_task(
        id="refiner",
        description="Refines the plan",
        prompt_template="Refine this plan: {plan}",
        provider_instance=refiner,
        on_chunk=lambda c: refine_tokens.append(c.delta),
        input_schema=PlanInput,
        output_schema=RefinedOutput,
    )

    flow = Flow(id="multi_stream", description="Draft -> Bridge -> Refine")
    flow.then(draft_task).then(bridge_task).then(refine_task).register()

    result = await flow.run({"topic": "error handling"})

    print(f"Draft tokens:  {len(draft_tokens)}")
    print(f"Refine tokens: {len(refine_tokens)}")
    print(f"Final: {result['response']}\n")


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await simple_streaming_example()
    await streaming_in_flow_example()
    await multi_stream_example()
    print("All streaming examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
