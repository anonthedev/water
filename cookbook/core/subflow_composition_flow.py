"""
Cookbook: SubFlow Composition

Demonstrates how to compose flows using SubFlow for reusable,
modular pipeline design in the Water framework.

Features shown:
  - Basic sub-flow embedding via SubFlow.as_task()
  - Input/output mapping between parent and child flows
  - compose_flows() utility for sequential composition
  - Building reusable flow components
"""

import asyncio
from pydantic import BaseModel
from water.core.task import create_task
from water.core.flow import Flow
from water.core.subflow import SubFlow, compose_flows


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────

class TextInput(BaseModel):
    text: str

class TextOutput(BaseModel):
    text: str

class AnalysisInput(BaseModel):
    text: str

class AnalysisOutput(BaseModel):
    text: str
    word_count: int

class ReportInput(BaseModel):
    content: str

class ReportOutput(BaseModel):
    report: str


# ──────────────────────────────────────────────
# Reusable Tasks
# ──────────────────────────────────────────────

normalize_task = create_task(
    id="normalize",
    description="Normalize text: strip and lowercase",
    input_schema=TextInput,
    output_schema=TextOutput,
    execute=lambda params, ctx: {"text": params.get("input_data", params)["text"].strip().lower()},
)

uppercase_task = create_task(
    id="uppercase",
    description="Convert text to uppercase",
    input_schema=TextInput,
    output_schema=TextOutput,
    execute=lambda params, ctx: {"text": params.get("input_data", params)["text"].upper()},
)

analyze_task = create_task(
    id="analyze",
    description="Count words in text",
    input_schema=AnalysisInput,
    output_schema=AnalysisOutput,
    execute=lambda params, ctx: {
        "text": params.get("input_data", params)["text"],
        "word_count": len(params.get("input_data", params)["text"].split()),
    },
)

format_report_task = create_task(
    id="format_report",
    description="Format analysis into a report",
    input_schema=AnalysisOutput,
    output_schema=ReportOutput,
    execute=lambda params, ctx: {
        "report": f"Text: '{params.get('input_data', params)['text']}' | Words: {params.get('input_data', params)['word_count']}"
    },
)


# ──────────────────────────────────────────────
# Example 1: Basic Sub-Flow Embedding
# ──────────────────────────────────────────────

def example_basic_subflow():
    """Embed a preprocessing flow inside a larger pipeline."""
    # Build a reusable preprocessing flow
    preprocess = Flow(id="preprocess")
    preprocess.then(normalize_task).then(uppercase_task)
    preprocess.register()

    # Embed it in a parent flow using SubFlow
    pipeline = Flow(id="pipeline_basic")
    pipeline.then(SubFlow(preprocess).as_task())
    pipeline.then(analyze_task)
    pipeline.register()

    return pipeline


# ──────────────────────────────────────────────
# Example 2: Input/Output Mapping
# ──────────────────────────────────────────────

def example_mapping():
    """Use input/output mapping to adapt between different schemas."""
    # Inner flow expects {"text": ...} and returns {"text": ...}
    text_flow = Flow(id="text_processor")
    text_flow.then(normalize_task).then(uppercase_task)
    text_flow.register()

    # Parent flow uses {"content": ...} field names
    # Map "content" -> "text" on input, "text" -> "content" on output
    sub = SubFlow(
        text_flow,
        input_mapping={"text": "content"},
        output_mapping={"content": "text"},
    )

    pipeline = Flow(id="pipeline_mapped")
    pipeline.then(sub.as_task())
    pipeline.register()

    return pipeline


# ──────────────────────────────────────────────
# Example 3: compose_flows Utility
# ──────────────────────────────────────────────

def example_compose_flows():
    """Use compose_flows() to chain multiple flows together."""
    # Two independent flows
    preprocess = Flow(id="preprocess_step")
    preprocess.then(normalize_task).then(uppercase_task)
    preprocess.register()

    analysis = Flow(id="analysis_step")
    analysis.then(analyze_task).then(format_report_task)
    analysis.register()

    # Compose them into a single flow
    full_pipeline = compose_flows(
        preprocess,
        analysis,
        id="full_pipeline",
        description="Preprocess then analyze text",
    )
    full_pipeline.register()

    return full_pipeline


# ──────────────────────────────────────────────
# Example 4: Reusable Flow Components
# ──────────────────────────────────────────────

def build_text_cleaner() -> Flow:
    """Factory for a reusable text cleaning flow."""
    flow = Flow(id="text_cleaner", description="Clean and normalize text")
    flow.then(normalize_task)
    flow.register()
    return flow


def build_text_transformer() -> Flow:
    """Factory for a reusable text transformation flow."""
    flow = Flow(id="text_transformer", description="Transform text to uppercase")
    flow.then(uppercase_task)
    flow.register()
    return flow


def example_reusable_components():
    """Compose reusable flow components into different pipelines."""
    cleaner = build_text_cleaner()
    transformer = build_text_transformer()

    # Pipeline A: clean then transform
    pipeline_a = Flow(id="pipeline_a")
    pipeline_a.then(SubFlow(cleaner).as_task())
    pipeline_a.then(SubFlow(transformer).as_task())
    pipeline_a.register()

    # Pipeline B: transform then analyze (skip cleaning)
    analysis_flow = Flow(id="quick_analysis")
    analysis_flow.then(analyze_task)
    analysis_flow.register()

    pipeline_b = Flow(id="pipeline_b")
    pipeline_b.then(SubFlow(transformer).as_task())
    pipeline_b.then(SubFlow(analysis_flow).as_task())
    pipeline_b.register()

    return pipeline_a, pipeline_b


# ──────────────────────────────────────────────
# Run Examples
# ──────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("SubFlow Composition Cookbook")
    print("=" * 60)

    # Example 1: Basic sub-flow embedding
    print("\n--- Example 1: Basic Sub-Flow Embedding ---")
    pipeline = example_basic_subflow()
    result = await pipeline.run({"text": "  Hello World  "})
    print(f"Input:  '  Hello World  '")
    print(f"Output: {result}")

    # Example 2: Input/output mapping
    print("\n--- Example 2: Input/Output Mapping ---")
    mapped = example_mapping()
    result = await mapped.run({"content": "  mapped input  "})
    print(f"Input:  {{'content': '  mapped input  '}}")
    print(f"Output: {result}")

    # Example 3: compose_flows utility
    print("\n--- Example 3: compose_flows Utility ---")
    composed = example_compose_flows()
    result = await composed.run({"text": "  compose flows demo  "})
    print(f"Input:  '  compose flows demo  '")
    print(f"Output: {result}")

    # Example 4: Reusable components
    print("\n--- Example 4: Reusable Flow Components ---")
    pipeline_a, pipeline_b = example_reusable_components()

    result_a = await pipeline_a.run({"text": "  Reusable Components  "})
    print(f"Pipeline A output: {result_a}")

    result_b = await pipeline_b.run({"text": "reusable components"})
    print(f"Pipeline B output: {result_b}")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
