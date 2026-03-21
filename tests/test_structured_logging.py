"""Tests for structured logging and log correlation."""

import pytest

from water.observability.logging import (
    StructuredLogger,
    LogContext,
    LogExporter,
    LogFormat,
    LogExport,
)


# --- LogContext tests ---

def test_log_context_to_dict():
    ctx = LogContext(flow_id="f1", execution_id="e1", task_id="t1")
    d = ctx.to_dict()
    assert d["flow_id"] == "f1"
    assert d["execution_id"] == "e1"
    assert d["task_id"] == "t1"


def test_log_context_with_task():
    ctx = LogContext(flow_id="f1", execution_id="e1", task_id="t1")
    new_ctx = ctx.with_task("t2")
    assert new_ctx.task_id == "t2"
    assert new_ctx.flow_id == "f1"
    assert ctx.task_id == "t1"  # original unchanged


def test_log_context_extra():
    ctx = LogContext(flow_id="f1", extra={"key": "value"})
    d = ctx.to_dict()
    assert d["key"] == "value"


# --- StructuredLogger tests ---

def test_logger_json_format():
    logger = StructuredLogger(level="DEBUG", format="json")
    logger.set_context(flow_id="f1", execution_id="e1")
    logger.info("test message", user_id="abc")
    logs = logger.get_logs()
    assert len(logs) == 1
    assert logs[0]["msg"] == "test message"
    assert logs[0]["flow_id"] == "f1"
    assert logs[0]["user_id"] == "abc"
    assert logs[0]["level"] == "INFO"


def test_logger_text_format():
    logger = StructuredLogger(level="DEBUG", format="text")
    logger.set_context(flow_id="f1")
    logger.info("hello")
    logs = logger.get_logs()
    assert len(logs) == 1


def test_logger_levels():
    logger = StructuredLogger(level="INFO", format="json")
    logger.debug("debug msg")  # Should be filtered
    logger.info("info msg")
    logger.warn("warn msg")
    logger.error("error msg")
    logs = logger.get_logs()
    assert len(logs) == 3  # debug filtered out
    levels = [l["level"] for l in logs]
    assert "INFO" in levels
    assert "WARN" in levels
    assert "ERROR" in levels


def test_logger_context_correlation():
    logger = StructuredLogger(level="DEBUG", format="json")
    logger.set_context(flow_id="registration", execution_id="exec_123", task_id="validate")
    logger.info("Processing user")
    log = logger.get_logs()[0]
    assert log["flow_id"] == "registration"
    assert log["execution_id"] == "exec_123"
    assert log["task_id"] == "validate"


def test_logger_redact_fields():
    logger = StructuredLogger(level="DEBUG", format="json", redact_fields=["password", "token"])
    logger.info("login", password="secret123", token="abc")
    log = logger.get_logs()[0]
    assert log["password"] == "***REDACTED***"
    assert log["token"] == "***REDACTED***"


def test_logger_clear():
    logger = StructuredLogger(level="DEBUG", format="json")
    logger.info("msg1")
    logger.info("msg2")
    assert len(logger.get_logs()) == 2
    logger.clear()
    assert len(logger.get_logs()) == 0


def test_logger_timestamp():
    logger = StructuredLogger(level="DEBUG", format="json")
    logger.info("msg")
    log = logger.get_logs()[0]
    assert "timestamp" in log


def test_logger_set_context_incremental():
    logger = StructuredLogger(level="DEBUG", format="json")
    logger.set_context(flow_id="f1")
    logger.set_context(task_id="t1")
    logger.info("msg")
    log = logger.get_logs()[0]
    assert log["flow_id"] == "f1"
    assert log["task_id"] == "t1"


# --- LogExporter tests ---

def test_log_exporter_stdout(capsys):
    exporter = LogExporter(destination="stdout")
    exporter.export([{"msg": "test", "level": "INFO"}])
    captured = capsys.readouterr()
    assert "test" in captured.out


def test_log_exporter_file(tmp_path):
    log_file = tmp_path / "test.log"
    exporter = LogExporter(destination="file", file_path=str(log_file))
    exporter.export([{"msg": "hello"}, {"msg": "world"}])
    content = log_file.read_text()
    assert "hello" in content
    assert "world" in content
