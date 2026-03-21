import asyncio
import time
import pytest

from water.observability.auto_instrument import (
    InstrumentationConfig,
    SpanRecord,
    InstrumentationCollector,
    AutoInstrumentor,
    auto_instrument,
)


def test_instrumentation_config_defaults():
    config = InstrumentationConfig()
    assert config.service_name == "water-service"
    assert config.endpoint is None
    assert config.sample_rate == 1.0
    assert config.capture_input is False
    assert config.capture_output is False
    assert config.custom_attributes == {}


def test_span_record_creation_and_duration():
    span = SpanRecord(name="test-span", kind="task", start_time=1.0, end_time=1.5)
    assert span.name == "test-span"
    assert span.kind == "task"
    assert span.duration_ms == pytest.approx(500.0)
    assert span.status == "ok"
    assert span.error is None
    assert span.children == []


def test_span_record_duration_zero():
    span = SpanRecord(name="zero", start_time=0.0, end_time=0.0)
    assert span.duration_ms == 0.0


def test_collector_start_end_span():
    collector = InstrumentationCollector()
    collector.start_span("my-span", kind="flow", attributes={"key": "value"})
    assert len(collector.spans) == 0
    assert "my-span" in collector._active_spans

    span = collector.end_span("my-span")
    assert span is not None
    assert span.name == "my-span"
    assert span.kind == "flow"
    assert span.attributes["key"] == "value"
    assert span.status == "ok"
    assert span.end_time > 0
    assert len(collector.spans) == 1


def test_collector_end_nonexistent_span():
    collector = InstrumentationCollector()
    result = collector.end_span("does-not-exist")
    assert result is None


def test_collector_clear():
    collector = InstrumentationCollector()
    collector.start_span("span-1")
    collector.end_span("span-1")
    collector.start_span("span-2")  # still active
    assert len(collector.spans) == 1
    assert len(collector._active_spans) == 1

    collector.clear()
    assert len(collector.spans) == 0
    assert len(collector._active_spans) == 0


def test_collector_get_spans_returns_copy():
    collector = InstrumentationCollector()
    collector.start_span("s1")
    collector.end_span("s1")
    spans = collector.get_spans()
    assert len(spans) == 1
    spans.clear()
    assert len(collector.spans) == 1  # original unaffected


def test_auto_instrumentor_enable_disable():
    inst = AutoInstrumentor()
    assert inst._enabled is False
    inst.enable()
    assert inst._enabled is True
    inst.disable()
    assert inst._enabled is False


def test_auto_instrumentor_before_after_task():
    inst = AutoInstrumentor()
    inst.enable()

    data = {"input": "hello"}
    result_data = asyncio.get_event_loop().run_until_complete(
        inst.before_task("task-1", data, context=None)
    )
    assert result_data == data

    collector = inst.get_collector()
    assert "task:task-1" in collector._active_spans

    result = {"output": "world"}
    result_out = asyncio.get_event_loop().run_until_complete(
        inst.after_task("task-1", data, result, context=None)
    )
    assert result_out == result
    assert len(collector.spans) == 1
    assert collector.spans[0].name == "task:task-1"
    assert collector.spans[0].kind == "task"


def test_auto_instrumentor_disabled_skips_spans():
    inst = AutoInstrumentor()
    # Not enabled
    data = {"input": "hello"}
    asyncio.get_event_loop().run_until_complete(
        inst.before_task("task-1", data, context=None)
    )
    collector = inst.get_collector()
    assert len(collector._active_spans) == 0
    assert len(collector.spans) == 0


def test_auto_instrument_convenience():
    inst = auto_instrument(service_name="my-svc", sample_rate=0.5, capture_input=True)
    assert isinstance(inst, AutoInstrumentor)
    assert inst._enabled is True
    assert inst.config.service_name == "my-svc"
    assert inst.config.sample_rate == 0.5
    assert inst.config.capture_input is True


def test_capture_input_records_input():
    config = InstrumentationConfig(capture_input=True)
    inst = AutoInstrumentor(config=config)
    inst.enable()

    data = {"message": "test input data"}
    asyncio.get_event_loop().run_until_complete(
        inst.before_task("cap-task", data, context=None)
    )
    span = inst.get_collector()._active_spans.get("task:cap-task")
    assert span is not None
    assert "task.input" in span.attributes
    assert "test input data" in span.attributes["task.input"]


def test_capture_output_records_output():
    config = InstrumentationConfig(capture_output=True)
    inst = AutoInstrumentor(config=config)
    inst.enable()

    data = {"message": "input"}
    result = {"response": "output data"}
    asyncio.get_event_loop().run_until_complete(
        inst.before_task("out-task", data, context=None)
    )
    asyncio.get_event_loop().run_until_complete(
        inst.after_task("out-task", data, result, context=None)
    )
    collector = inst.get_collector()
    assert len(collector.spans) == 1
    assert "task.output" in collector.spans[0].attributes
    assert "output data" in collector.spans[0].attributes["task.output"]


def test_otel_availability_detection():
    inst = AutoInstrumentor()
    # OTel is likely not installed in test env; either way the property should work
    assert isinstance(inst.is_otel_available, bool)


def test_multiple_spans_tracking():
    inst = AutoInstrumentor()
    inst.enable()

    loop = asyncio.get_event_loop()
    for i in range(5):
        loop.run_until_complete(
            inst.before_task(f"task-{i}", {"i": i}, context=None)
        )
    for i in range(5):
        loop.run_until_complete(
            inst.after_task(f"task-{i}", {"i": i}, {"result": i}, context=None)
        )

    collector = inst.get_collector()
    assert len(collector.spans) == 5
    names = {s.name for s in collector.spans}
    for i in range(5):
        assert f"task:task-{i}" in names
