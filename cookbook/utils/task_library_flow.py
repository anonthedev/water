"""
Task Library Flow Example: Using Built-in Reusable Tasks

This example demonstrates Water's standard task library - pre-built tasks
for common operations like JSON transforms, file I/O, delays, and logging.
"""

import asyncio
import json
import tempfile
import os

from water.core import Flow
from water.tasks import (
    json_transform,
    map_fields,
    filter_fields,
    file_read,
    file_write,
    delay,
    log_task,
    noop,
)


async def example_json_transform():
    """Chain JSON transforms to reshape data."""
    print("=== Example 1: JSON Transform Pipeline ===\n")

    flow = (
        Flow("transform-pipeline")
        .then(json_transform(
            id="extract",
            expression="profile",
        ))
        .then(map_fields(
            id="rename",
            field_map={"user_name": "name", "user_email": "email"},
        ))
        .register()
    )

    result = await flow.run({
        "profile": {"name": "Alice", "email": "alice@example.com", "age": 30},
    })
    print(f"  Transformed: {result}\n")


async def example_filter_fields():
    """Filter to include only specific fields."""
    print("=== Example 2: Filter Fields ===\n")

    flow = (
        Flow("filter-pipeline")
        .then(filter_fields(id="keep-essentials", include=["name", "email"]))
        .register()
    )

    result = await flow.run({
        "name": "Bob", "email": "bob@example.com",
        "password": "secret123", "ssn": "123-45-6789",
    })
    print(f"  Filtered (sensitive removed): {result}\n")


async def example_file_io():
    """Write and read files using task library."""
    print("=== Example 3: File I/O ===\n")

    tmp = tempfile.mktemp(suffix=".json")

    write_flow = Flow("write-file").then(file_write(id="writer", path=tmp)).register()
    await write_flow.run({"content": json.dumps({"greeting": "Hello, Water!"})})
    print(f"  Wrote to {tmp}")

    read_flow = Flow("read-file").then(file_read(id="reader", path=tmp)).register()
    result = await read_flow.run({})
    print(f"  Read back: {result}\n")
    os.unlink(tmp)


async def example_utilities():
    """Use utility tasks for timing, logging, and pass-through."""
    print("=== Example 4: Utility Tasks ===\n")

    flow = (
        Flow("utility-chain")
        .then(log_task(id="start-log", message="Pipeline starting"))
        .then(delay(id="pause", seconds=0.1))
        .then(noop(id="pass-through"))
        .then(log_task(id="end-log", message="Pipeline complete"))
        .register()
    )

    result = await flow.run({"data": "test"})
    print(f"  Result after utility chain: {result}\n")


async def main():
    await example_json_transform()
    await example_filter_fields()
    await example_file_io()
    await example_utilities()


if __name__ == "__main__":
    asyncio.run(main())
