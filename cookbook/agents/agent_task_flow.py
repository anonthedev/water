"""
Agent Task Flow Example: Multi-Agent Planner -> Coder -> Reviewer

This example demonstrates how to use LLM-native agent tasks in Water flows.
It shows:
  - Creating an agent task with a prompt template
  - Chaining agent tasks with regular tasks
  - Using output_parser for structured output
  - A multi-agent flow (planner -> coder -> reviewer pattern)

NOTE: This example uses MockProvider so it runs without real API keys.
      Replace MockProvider with OpenAIProvider or AnthropicProvider for
      production use.
"""

import asyncio
import json
from typing import Dict, Any

from pydantic import BaseModel

from water.core import Flow, create_task
from water.agents import create_agent_task, MockProvider


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FeatureRequest(BaseModel):
    feature: str


class PlanOutput(BaseModel):
    response: str
    feature: str


class CodeOutput(BaseModel):
    response: str
    plan: str


class ReviewOutput(BaseModel):
    response: str
    code: str


class FinalReport(BaseModel):
    feature: str
    plan: str
    code: str
    review: str


# ---------------------------------------------------------------------------
# Example 1: Simple agent task with prompt template
# ---------------------------------------------------------------------------

async def simple_agent_example():
    """Create a single agent task and run it in a flow."""
    print("=== Simple Agent Task ===\n")

    mock = MockProvider(
        default_response="Water is a lightweight Python workflow framework."
    )

    class TopicInput(BaseModel):
        topic: str

    agent = create_agent_task(
        id="explainer",
        description="Explains a topic",
        prompt_template="Explain {topic} in one sentence.",
        provider_instance=mock,
        input_schema=TopicInput,
    )

    flow = Flow(id="explain_flow", description="Simple explanation flow")
    flow.then(agent).register()

    result = await flow.run({"topic": "the Water framework"})
    print(f"Topic:    {result.get('topic')}")
    print(f"Response: {result['response']}\n")


# ---------------------------------------------------------------------------
# Example 2: Agent task with output_parser for structured output
# ---------------------------------------------------------------------------

async def structured_output_example():
    """Use an output_parser to convert LLM text into structured data."""
    print("=== Structured Output ===\n")

    mock = MockProvider(
        default_response='{"steps": ["design API", "write tests", "implement"], "estimated_hours": 4}'
    )

    def parse_plan(text: str) -> dict:
        """Parse the LLM JSON response into a plan dict."""
        data = json.loads(text)
        return {
            "plan": text,
            "steps": data["steps"],
            "estimated_hours": data["estimated_hours"],
        }

    class FeatureInput(BaseModel):
        feature: str

    class PlanParserOutput(BaseModel):
        plan: str
        steps: list
        estimated_hours: int

    planner = create_agent_task(
        id="planner",
        description="Creates an implementation plan",
        prompt_template="Create a plan to implement: {feature}",
        provider_instance=mock,
        output_parser=parse_plan,
        input_schema=FeatureInput,
        output_schema=PlanParserOutput,
    )

    flow = Flow(id="plan_flow", description="Structured planning flow")
    flow.then(planner).register()

    result = await flow.run({"feature": "user authentication"})
    print(f"Plan:   {result.get('plan')}")
    print(f"Steps:  {result.get('steps')}")
    print(f"Hours:  {result.get('estimated_hours')}\n")


# ---------------------------------------------------------------------------
# Example 3: Chaining agent tasks with regular tasks
# ---------------------------------------------------------------------------

async def chained_example():
    """Chain an agent task with a regular Python task."""
    print("=== Agent + Regular Task Chain ===\n")

    mock = MockProvider(default_response="Use async/await for concurrency.")

    class TopicInput(BaseModel):
        topic: str

    agent = create_agent_task(
        id="advisor",
        description="Gives coding advice",
        prompt_template="What is the best practice for {topic}?",
        provider_instance=mock,
        input_schema=TopicInput,
    )

    class AdviceInput(BaseModel):
        response: str
        topic: str

    class FormattedOutput(BaseModel):
        formatted: str

    def format_advice(params, context):
        data = params["input_data"]
        return {
            "formatted": f"[ADVICE on '{data['topic']}']: {data['response']}"
        }

    formatter = create_task(
        id="formatter",
        description="Formats the advice",
        input_schema=AdviceInput,
        output_schema=FormattedOutput,
        execute=format_advice,
    )

    flow = Flow(id="chain_flow", description="Agent chained with formatter")
    flow.then(agent).then(formatter).register()

    result = await flow.run({"topic": "Python concurrency"})
    print(f"Result: {result['formatted']}\n")


# ---------------------------------------------------------------------------
# Example 4: Multi-agent flow (planner -> coder -> reviewer)
# ---------------------------------------------------------------------------

async def multi_agent_example():
    """
    Demonstrate a multi-agent flow where three LLM agents collaborate:
      1. Planner  - designs the approach
      2. Coder    - writes the implementation
      3. Reviewer - reviews the code
    A final regular task assembles the report.
    """
    print("=== Multi-Agent Flow (Planner -> Coder -> Reviewer) ===\n")

    planner_mock = MockProvider(
        default_response="Plan: 1) Parse input  2) Validate  3) Transform  4) Return result"
    )
    coder_mock = MockProvider(
        default_response="def process(data):\n    validated = validate(data)\n    return transform(validated)"
    )
    reviewer_mock = MockProvider(
        default_response="LGTM. Consider adding type hints and error handling."
    )

    # Agent 1: Planner
    planner = create_agent_task(
        id="planner",
        description="Plans the implementation",
        prompt_template="Design an implementation plan for: {feature}",
        system_prompt="You are a senior software architect.",
        provider_instance=planner_mock,
        input_schema=FeatureRequest,
        output_schema=PlanOutput,
    )

    # Bridge: extract plan from planner output
    def extract_plan(params, context):
        data = params["input_data"]
        return {"plan": data["response"]}

    class PlanBridge(BaseModel):
        plan: str

    extract = create_task(
        id="extract_plan",
        input_schema=PlanOutput,
        output_schema=PlanBridge,
        execute=extract_plan,
    )

    # Agent 2: Coder
    coder = create_agent_task(
        id="coder",
        description="Writes the code",
        prompt_template="Implement the following plan:\n{plan}",
        system_prompt="You are an expert Python developer.",
        provider_instance=coder_mock,
        input_schema=PlanBridge,
        output_schema=CodeOutput,
    )

    # Bridge: extract code from coder output
    def extract_code(params, context):
        data = params["input_data"]
        return {"code": data["response"], "plan": data.get("plan", "")}

    class CodeBridge(BaseModel):
        code: str
        plan: str

    extract_c = create_task(
        id="extract_code",
        input_schema=CodeOutput,
        output_schema=CodeBridge,
        execute=extract_code,
    )

    # Agent 3: Reviewer
    reviewer = create_agent_task(
        id="reviewer",
        description="Reviews the code",
        prompt_template="Review this code:\n{code}",
        system_prompt="You are a meticulous code reviewer.",
        provider_instance=reviewer_mock,
        input_schema=CodeBridge,
        output_schema=ReviewOutput,
    )

    # Final: assemble the report
    def assemble_report(params, context):
        data = params["input_data"]
        return {
            "feature": "data processing pipeline",
            "plan": data.get("plan", ""),
            "code": data.get("code", ""),
            "review": data.get("response", ""),
        }

    report_task = create_task(
        id="report",
        description="Assembles final report",
        input_schema=ReviewOutput,
        output_schema=FinalReport,
        execute=assemble_report,
    )

    flow = Flow(id="multi_agent", description="Planner -> Coder -> Reviewer")
    flow.then(planner).then(extract).then(coder).then(extract_c).then(reviewer).then(report_task).register()

    result = await flow.run({"feature": "data processing pipeline"})

    print(f"Feature: {result.get('feature')}")
    print(f"Plan:    {result.get('plan')}")
    print(f"Code:    {result.get('code')}")
    print(f"Review:  {result.get('review')}\n")


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await simple_agent_example()
    await structured_output_example()
    await chained_example()
    await multi_agent_example()
    print("All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
