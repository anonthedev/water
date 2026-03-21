"""
Structured Logging Flow Example: JSON Logging & Log Correlation

This example demonstrates Water's structured logging system for producing
machine-readable logs with automatic correlation across tasks. It shows:
  - StructuredLogger with JSON and text output formats
  - LogContext for injecting flow/execution/task IDs into every log line
  - Field redaction for masking sensitive data
  - LogExporter for exporting log records
  - Log sampling for high-throughput scenarios

NOTE: This example writes to stdout and an in-memory buffer. No external
      logging services are required.
"""

import asyncio
import logging
from typing import Any, Dict

from water.observability.logging import StructuredLogger, LogContext, LogExporter


# Suppress default logging to keep output clean
logging.getLogger("water.structured").handlers = []


# ---------------------------------------------------------------------------
# Example 1: Basic structured logging (JSON and text formats)
# ---------------------------------------------------------------------------

async def example_basic_logging():
    """Log messages in JSON and text formats with context injection."""
    print("=== Example 1: Basic Structured Logging ===\n")

    # JSON format logger
    json_logger = StructuredLogger(level="DEBUG", format="json")
    json_logger.set_context(
        flow_id="data_pipeline",
        execution_id="exec_001",
        task_id="extract",
    )

    json_logger.info("Starting data extraction", source="database", table="users")
    json_logger.debug("Query prepared", query="SELECT * FROM users LIMIT 100")
    json_logger.info("Extraction complete", rows=150)

    print("JSON log entries:")
    for entry in json_logger.get_logs():
        print(f"  {entry}")
    print()

    # Text format logger
    text_logger = StructuredLogger(level="INFO", format="text")
    text_logger.set_context(
        flow_id="ml_pipeline",
        execution_id="exec_002",
    )

    text_logger.info("Model training started", model="classifier_v3")
    text_logger.info("Epoch complete", epoch=1, loss=0.45, accuracy=0.82)
    text_logger.warn("Learning rate too high", lr=0.01)

    print("Text log entries:")
    for entry in text_logger.get_logs():
        level = entry["level"]
        msg = entry["msg"]
        print(f"  [{level}] {msg}")
    print()


# ---------------------------------------------------------------------------
# Example 2: Log context and task correlation
# ---------------------------------------------------------------------------

async def example_log_context():
    """Track logs across multiple tasks in a flow execution."""
    print("=== Example 2: LogContext & Task Correlation ===\n")

    logger = StructuredLogger(level="INFO", format="json")

    # Set flow-level context
    base_ctx = LogContext(
        flow_id="order_processing",
        execution_id="exec_100",
    )

    # Task 1: validate_order
    ctx1 = base_ctx.with_task("validate_order")
    logger._context = ctx1
    logger.info("Validating order", order_id="ORD-001")
    logger.info("Order valid", items=3, total=149.99)

    # Task 2: charge_payment
    ctx2 = base_ctx.with_task("charge_payment")
    logger._context = ctx2
    logger.info("Processing payment", method="credit_card")
    logger.info("Payment successful", transaction_id="TXN-456")

    # Task 3: ship_order
    ctx3 = base_ctx.with_task("ship_order")
    logger._context = ctx3
    logger.info("Shipping order", carrier="fedex")

    # All logs share the same execution_id for correlation
    logs = logger.get_logs()
    print(f"Total log entries: {len(logs)}")
    print(f"All share execution_id: {all(l.get('execution_id') == 'exec_100' for l in logs)}")
    print()
    for entry in logs:
        print(f"  task={entry.get('task_id', 'N/A'):20s} msg={entry['msg']}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Redaction, sampling, and export
# ---------------------------------------------------------------------------

async def example_redaction_and_export():
    """Demonstrate field redaction and log export."""
    print("=== Example 3: Redaction & Export ===\n")

    # Logger with field redaction
    logger = StructuredLogger(
        level="INFO",
        format="json",
        redact_fields=["password", "ssn", "api_key"],
        sample_rate=1.0,  # log everything
    )
    logger.set_context(flow_id="auth_flow", execution_id="exec_300")

    logger.info("User login attempt", username="alice", password="s3cret123")
    logger.info("API call", endpoint="/users", api_key="sk-1234567890")
    logger.info("User profile", name="Alice", ssn="123-45-6789", email="alice@example.com")

    print("Logs with redacted fields:")
    for entry in logger.get_logs():
        # Show relevant fields
        redacted_fields = {k: v for k, v in entry.items()
                          if k in ("username", "password", "api_key", "ssn", "name", "email")}
        if redacted_fields:
            print(f"  msg='{entry['msg']}' -> {redacted_fields}")
    print()

    # LogExporter (stdout export)
    exporter = LogExporter(destination="stdout")
    print("Exported records:")
    exporter.export(logger.get_logs()[:2])  # export first 2 records
    print()

    # Clear buffer
    logger.clear()
    print(f"After clear: {len(logger.get_logs())} entries")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_basic_logging()
    await example_log_context()
    await example_redaction_and_export()
    print("All structured logging examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
