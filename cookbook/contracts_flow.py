"""
Data Contracts Example
======================

Demonstrates how to use validate_contracts() and strict_contracts
to enforce that sequential tasks have compatible schemas.
"""

import asyncio
from pydantic import BaseModel
from water.core import create_task, Flow


# --- Define schemas ---

class RawTextInput(BaseModel):
    text: str

class AnalysisOutput(BaseModel):
    text: str
    sentiment: float
    word_count: int

class SummaryInput(BaseModel):
    text: str
    sentiment: float

class SummaryOutput(BaseModel):
    summary: str


# --- Define tasks ---

async def analyze(params, context):
    text = params["text"]
    return {
        "text": text,
        "sentiment": 0.85,
        "word_count": len(text.split()),
    }

async def summarize(params, context):
    return {"summary": f"Positive text ({params['sentiment']:.0%}): {params['text'][:50]}..."}


analyze_task = create_task(
    id="analyze",
    description="Analyze text for sentiment and word count",
    input_schema=RawTextInput,
    output_schema=AnalysisOutput,
    execute=analyze,
)

summarize_task = create_task(
    id="summarize",
    description="Produce a short summary from analysis",
    input_schema=SummaryInput,
    output_schema=SummaryOutput,
    execute=summarize,
)


# --- Build and validate a pipeline ---

def main():
    # 1. Valid pipeline: AnalysisOutput covers SummaryInput fields
    flow = Flow(id="valid_pipeline", strict_contracts=True)
    flow.then(analyze_task).then(summarize_task).register()
    print("Valid pipeline registered successfully (no contract violations).")

    # 2. Check violations manually
    violations = flow.validate_contracts()
    print(f"Violations: {violations}")  # []

    # 3. Demonstrate a broken contract
    class IncompleteOutput(BaseModel):
        text: str  # missing 'sentiment' that SummaryInput needs

    broken_task = create_task(
        id="broken_analyze",
        input_schema=RawTextInput,
        output_schema=IncompleteOutput,
        execute=analyze,
    )

    broken_flow = Flow(id="broken_pipeline")
    broken_flow.then(broken_task).then(summarize_task).register()
    violations = broken_flow.validate_contracts()
    print(f"\nBroken pipeline violations: {len(violations)}")
    for v in violations:
        print(f"  {v['message']}")

    # 4. Strict mode raises on broken contracts
    strict_flow = Flow(id="strict_broken", strict_contracts=True)
    strict_flow.then(broken_task).then(summarize_task)
    try:
        strict_flow.register()
    except ValueError as e:
        print(f"\nStrict mode caught violation:\n  {e}")

    # 5. Run the valid pipeline
    result = asyncio.run(flow.run({"text": "Water is a great framework for building pipelines."}))
    print(f"\nPipeline result: {result}")


if __name__ == "__main__":
    main()
