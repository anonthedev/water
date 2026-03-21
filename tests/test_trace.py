"""Tests for trace visualization and debugging."""

import pytest
from pydantic import BaseModel

from water.core.task import create_task
from water.core.flow import Flow
from water.observability.trace import (
    TraceCollector,
    TraceStore,
    Trace,
    TraceSpan,
)


# --- Helpers ---

class TInput(BaseModel):
    value: str = ""

class TOutput(BaseModel):
    result: str = ""


def _make_flow_with_tracing():
    store = TraceStore()
    collector = TraceCollector(store=store)

    async def step1(params, ctx):
        data = params.get("input_data", params)
        return {"result": f"processed {data.get('value', '')}"}

    async def step2(params, ctx):
        data = params.get("input_data", params)
        return {"result": f"finalized {data.get('result', '')}"}

    t1 = create_task(id="step1", input_schema=TInput, output_schema=TOutput, execute=step1)
    t2 = create_task(id="step2", input_schema=TOutput, output_schema=TOutput, execute=step2)

    flow = Flow(id="traced_flow")
    flow.use(collector)
    flow.then(t1).then(t2).register()
    return flow, store, collector


# --- TraceSpan tests ---

def test_trace_span_to_dict():
    span = TraceSpan(
        span_id="s1", task_id="task1", flow_id="f1",
        execution_id="e1", status="completed", duration_ms=42.0,
    )
    d = span.to_dict()
    assert d["span_id"] == "s1"
    assert d["duration_ms"] == 42.0


# --- Trace tests ---

def test_trace_to_dict():
    trace = Trace(trace_id="t1", flow_id="f1", execution_id="e1")
    d = trace.to_dict()
    assert d["trace_id"] == "t1"
    assert d["spans"] == []


# --- TraceStore tests ---

def test_store_save_and_get():
    store = TraceStore()
    trace = Trace(trace_id="t1", flow_id="f1", execution_id="e1")
    store.save(trace)
    assert store.get("t1") is trace


def test_store_find_by_execution():
    store = TraceStore()
    trace = Trace(trace_id="t1", flow_id="f1", execution_id="exec_123")
    store.save(trace)
    found = store.find_by_execution("exec_123")
    assert found is trace


def test_store_find_by_flow():
    store = TraceStore()
    store.save(Trace(trace_id="t1", flow_id="f1", execution_id="e1", started_at="2024-01-01"))
    store.save(Trace(trace_id="t2", flow_id="f1", execution_id="e2", started_at="2024-01-02"))
    store.save(Trace(trace_id="t3", flow_id="f2", execution_id="e3", started_at="2024-01-01"))
    results = store.find_by_flow("f1")
    assert len(results) == 2


def test_store_list_traces():
    store = TraceStore()
    store.save(Trace(trace_id="t1", flow_id="f1", execution_id="e1", status="completed"))
    store.save(Trace(trace_id="t2", flow_id="f1", execution_id="e2", status="failed"))
    all_traces = store.list_traces()
    assert len(all_traces) == 2
    failed = store.list_traces(status="failed")
    assert len(failed) == 1


def test_store_delete():
    store = TraceStore()
    store.save(Trace(trace_id="t1", flow_id="f1", execution_id="e1"))
    assert store.delete("t1")
    assert store.get("t1") is None
    assert not store.delete("nonexistent")


def test_store_clear():
    store = TraceStore()
    store.save(Trace(trace_id="t1", flow_id="f1", execution_id="e1"))
    store.clear()
    assert store.list_traces() == []


def test_store_max_traces():
    store = TraceStore(max_traces=3)
    for i in range(5):
        store.save(Trace(trace_id=f"t{i}", flow_id="f1", execution_id=f"e{i}"))
    assert len(store.list_traces()) == 3


# --- TraceCollector integration tests ---

@pytest.mark.asyncio
async def test_collector_captures_trace():
    flow, store, collector = _make_flow_with_tracing()
    result = await flow.run({"value": "hello"})

    traces = store.list_traces()
    assert len(traces) >= 1
    trace = traces[0]
    assert len(trace.spans) == 2
    assert trace.spans[0].task_id == "step1"
    assert trace.spans[1].task_id == "step2"


@pytest.mark.asyncio
async def test_collector_records_io():
    flow, store, collector = _make_flow_with_tracing()
    await flow.run({"value": "test"})

    traces = store.list_traces()
    trace = traces[0]
    # First span should have input and output
    span = trace.spans[0]
    assert span.status == "completed"
    assert span.input_data is not None
    assert span.output_data is not None


@pytest.mark.asyncio
async def test_collector_records_timing():
    flow, store, collector = _make_flow_with_tracing()
    await flow.run({"value": "timing"})

    traces = store.list_traces()
    span = traces[0].spans[0]
    assert span.started_at is not None
    assert span.completed_at is not None
    assert span.duration_ms is not None
    assert span.duration_ms >= 0


def test_collector_complete_trace():
    store = TraceStore()
    collector = TraceCollector(store=store)
    trace = Trace(trace_id="t1", flow_id="f1", execution_id="e1", started_at="2024-01-01T00:00:00")
    collector._active_traces["e1"] = trace
    store.save(trace)

    collector.complete_trace("e1", output={"result": "done"})
    saved = store.get("t1")
    assert saved.status == "completed"
    assert saved.output_data == {"result": "done"}


def test_collector_complete_trace_error():
    store = TraceStore()
    collector = TraceCollector(store=store)
    trace = Trace(trace_id="t1", flow_id="f1", execution_id="e1", started_at="2024-01-01T00:00:00")
    collector._active_traces["e1"] = trace
    store.save(trace)

    collector.complete_trace("e1", error="something broke")
    saved = store.get("t1")
    assert saved.status == "failed"
    assert saved.error == "something broke"
