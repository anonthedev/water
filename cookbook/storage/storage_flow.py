"""
Storage Flow Example: Pause, Resume, and Session Inspection

This example demonstrates using InMemoryStorage to enable pause/stop/resume
on a running flow. Shows how to pause a flow mid-execution, inspect the
stored session and task runs, and then resume to completion.

Usage:
    python cookbook/storage_flow.py
"""

from water.core import Flow, create_task
from water.core.engine import FlowPausedError
from water.storage import InMemoryStorage, FlowStatus
from pydantic import BaseModel
from typing import Dict, Any
import asyncio

# Data schemas
class DocumentInput(BaseModel):
    doc_id: str
    content: str

class ParsedDocument(BaseModel):
    doc_id: str
    content: str
    word_count: int
    parsed: bool

class AnalyzedDocument(BaseModel):
    doc_id: str
    word_count: int
    sentiment: str
    analyzed: bool

class FinalReport(BaseModel):
    doc_id: str
    word_count: int
    sentiment: str
    report_generated: bool
    summary: str

# Step 1: Parse document
def parse_document(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Parse raw document content."""
    data = params["input_data"]
    words = len(data["content"].split())
    print(f"  [parse] Parsed doc '{data['doc_id']}': {words} words")
    return {
        "doc_id": data["doc_id"],
        "content": data["content"],
        "word_count": words,
        "parsed": True,
    }

# Step 2: Analyze sentiment
def analyze_sentiment(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Run sentiment analysis on the parsed document."""
    data = params["input_data"]
    sentiment = "positive" if data["word_count"] > 5 else "neutral"
    print(f"  [analyze] Sentiment for '{data['doc_id']}': {sentiment}")
    return {
        "doc_id": data["doc_id"],
        "word_count": data["word_count"],
        "sentiment": sentiment,
        "analyzed": True,
    }

# Step 3: Generate report
def generate_report(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Generate a final summary report."""
    data = params["input_data"]
    summary = f"Document {data['doc_id']}: {data['word_count']} words, {data['sentiment']} tone."
    print(f"  [report] {summary}")
    return {
        "doc_id": data["doc_id"],
        "word_count": data["word_count"],
        "sentiment": data["sentiment"],
        "report_generated": True,
        "summary": summary,
    }

# Create tasks
parse_task = create_task(
    id="parse",
    description="Parse document content",
    input_schema=DocumentInput,
    output_schema=ParsedDocument,
    execute=parse_document,
)

analyze_task = create_task(
    id="analyze",
    description="Analyze document sentiment",
    input_schema=ParsedDocument,
    output_schema=AnalyzedDocument,
    execute=analyze_sentiment,
)

report_task = create_task(
    id="report",
    description="Generate final report",
    input_schema=AnalyzedDocument,
    output_schema=FinalReport,
    execute=generate_report,
)

# Set up storage backend
storage = InMemoryStorage()

# Build flow with storage for pause/resume support
doc_flow = Flow(id="document_pipeline", description="Pausable document processing pipeline", storage=storage)
doc_flow.then(parse_task).then(analyze_task).then(report_task).register()

async def main():
    """Run the storage flow example with pause and resume."""
    print("=== Storage Flow: Pause / Resume / Inspect ===\n")

    doc_input = {
        "doc_id": "DOC-42",
        "content": "Water is a lightweight framework for building robust data pipelines with ease",
    }

    # --- Run 1: Trigger a pause after the first task completes ---
    print("--- Run 1: Start flow and pause after first task ---")

    # Start the flow in a background task so we can pause it
    flow_coro = doc_flow.run(doc_input)
    flow_task = asyncio.create_task(flow_coro)

    # Give the engine time to execute the first task and create a session
    await asyncio.sleep(0.1)

    # Find the active session and pause it
    sessions = await storage.list_sessions(flow_id="document_pipeline")
    if sessions:
        execution_id = sessions[0].execution_id
        print(f"  Found session: {execution_id}")
        try:
            await doc_flow.pause(execution_id)
            print(f"  Requested pause for {execution_id}")
        except ValueError as e:
            print(f"  Could not pause (may have already completed): {e}")

    # Wait for the flow to acknowledge the pause (or complete)
    try:
        result = await flow_task
        print(f"  Flow completed before pause took effect: {result}\n")
    except FlowPausedError:
        print(f"  Flow paused successfully!\n")

        # --- Inspect session state ---
        print("--- Inspecting stored session ---")
        session = await doc_flow.get_session(execution_id)
        print(f"  execution_id:      {session.execution_id}")
        print(f"  status:            {session.status.value}")
        print(f"  current_node_index:{session.current_node_index}")
        print(f"  current_data:      {session.current_data}")

        # Inspect task runs
        task_runs = await doc_flow.get_task_runs(execution_id)
        print(f"  task_runs recorded: {len(task_runs)}")
        for run in task_runs:
            print(f"    - {run.task_id}: {run.status}")

        # --- Run 2: Resume from where we left off ---
        print("\n--- Run 2: Resuming paused flow ---")
        result = await doc_flow.resume(execution_id)
        print(f"  Resume result: {result}")

        # Verify final session state
        session = await doc_flow.get_session(execution_id)
        print(f"  Final status: {session.status.value}")

    # --- Show all sessions recorded ---
    print("\n--- All sessions in storage ---")
    all_sessions = await storage.list_sessions()
    for s in all_sessions:
        print(f"  {s.execution_id}: {s.status.value}")

    print("\n  flow completed successfully!")
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
