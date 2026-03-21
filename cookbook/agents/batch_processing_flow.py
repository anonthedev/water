"""
Batch Processing Flow Example
==============================

Demonstrates how to use :class:`BatchProcessor` and :func:`create_batch_task`
from ``water.agents.batch`` to process many items through a single Task
concurrently, with retry logic and progress reporting.
"""

import asyncio
from typing import Any, Dict

from pydantic import BaseModel

from water.core.task import Task, create_task
from water.core import Flow
from water.agents.batch import BatchProcessor, create_batch_task


# ---------------------------------------------------------------------------
# 1.  Define schemas and a simple task
# ---------------------------------------------------------------------------

class ArticleInput(BaseModel):
    title: str
    body: str


class SummaryOutput(BaseModel):
    title: str
    summary: str
    word_count: int


async def summarise(params: Dict[str, Any], context) -> Dict[str, Any]:
    """Fake summariser – returns the first 30 chars as a 'summary'."""
    await asyncio.sleep(0.05)  # simulate latency
    body = params.get("body", "")
    return {
        "title": params["title"],
        "summary": body[:30] + ("..." if len(body) > 30 else ""),
        "word_count": len(body.split()),
    }


summarise_task = create_task(
    id="summarise",
    description="Summarise an article",
    input_schema=ArticleInput,
    output_schema=SummaryOutput,
    execute=summarise,
)


# ---------------------------------------------------------------------------
# 2.  Use BatchProcessor directly
# ---------------------------------------------------------------------------

async def demo_batch_processor():
    """Run a batch of articles through the summariser with progress."""

    progress: list = []

    def on_progress(completed: int, total: int) -> None:
        pct = int(completed / total * 100)
        progress.append(pct)
        print(f"  Progress: {completed}/{total} ({pct}%)")

    processor = BatchProcessor(
        max_concurrency=3,
        retry_failed=True,
        max_retries=2,
        on_progress=on_progress,
    )

    articles = [
        {"title": f"Article {i}", "body": f"Body text for article number {i} with enough words to test."}
        for i in range(6)
    ]

    print("=== BatchProcessor demo ===")
    result = await processor.run_batch(summarise_task, articles)

    print(f"\nTotal: {result.total}  Completed: {result.completed}  "
          f"Failed: {result.failed}  Success rate: {result.success_rate:.0%}")

    for item in result.items:
        if item.status == "completed":
            print(f"  [{item.index}] {item.result['title']} -> {item.result['summary']}")
        else:
            print(f"  [{item.index}] FAILED: {item.error}")


# ---------------------------------------------------------------------------
# 3.  Use create_batch_task inside a Flow
# ---------------------------------------------------------------------------

async def demo_batch_task_in_flow():
    """Wrap the summariser as a batch task and run it inside a Flow."""

    batch_task = create_batch_task(
        id="batch_summarise",
        description="Summarise a batch of articles",
        task=summarise_task,
        max_concurrency=4,
        input_key="articles",
        output_key="summaries",
    )

    flow = Flow(id="batch_summary_flow", description="Batch article summarisation")
    flow.then(batch_task).register()

    articles = [
        {"title": f"Post {i}", "body": f"Content for post {i}. It has several sentences."}
        for i in range(5)
    ]

    print("\n=== create_batch_task + Flow demo ===")
    result = await flow.run({"articles": articles})
    summaries = result.get("summaries", [])

    for idx, s in enumerate(summaries):
        if s is not None:
            print(f"  [{idx}] {s['title']} -> {s['summary']}")
        else:
            print(f"  [{idx}] (failed)")


# ---------------------------------------------------------------------------
# 4.  Run both demos
# ---------------------------------------------------------------------------

async def main():
    await demo_batch_processor()
    await demo_batch_task_in_flow()


if __name__ == "__main__":
    asyncio.run(main())
