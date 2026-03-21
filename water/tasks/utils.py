"""
Utility tasks for Water.

Delay, logging, and no-op tasks for flow composition.
"""

import asyncio
import logging
from typing import Any, Optional

from pydantic import BaseModel

from water.core.task import Task

logger = logging.getLogger(__name__)


class PassthroughInput(BaseModel):
    pass

    class Config:
        extra = "allow"


class PassthroughOutput(BaseModel):
    pass

    class Config:
        extra = "allow"


def delay(
    id: str,
    seconds: float = 1.0,
    description: Optional[str] = None,
) -> Task:
    """
    Create a delay/pause task.

    Args:
        id: Task identifier.
        seconds: Number of seconds to wait.
        description: Task description.

    Returns:
        A Task instance that pauses then passes data through.
    """
    async def execute(params: dict, context: Any) -> dict:
        data = params.get("input_data", params)
        await asyncio.sleep(seconds)
        return dict(data)

    return Task(
        id=id,
        description=description or f"Delay {seconds}s",
        input_schema=PassthroughInput,
        output_schema=PassthroughOutput,
        execute=execute,
    )


def log_task(
    id: str,
    message: str = "",
    level: str = "INFO",
    description: Optional[str] = None,
) -> Task:
    """
    Create a logging task that logs data at any point in the flow.

    Args:
        id: Task identifier.
        message: Log message template (supports {variable} substitution).
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        description: Task description.

    Returns:
        A Task instance that logs and passes data through.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    def execute(params: dict, context: Any) -> dict:
        data = params.get("input_data", params)
        msg = message.format(**data) if message else str(data)
        logger.log(log_level, f"[{id}] {msg}")
        return dict(data)

    return Task(
        id=id,
        description=description or f"Log: {message}",
        input_schema=PassthroughInput,
        output_schema=PassthroughOutput,
        execute=execute,
    )


def noop(
    id: str,
    description: Optional[str] = None,
) -> Task:
    """
    Create a no-op task that passes data through unchanged.

    Useful as a placeholder or for testing.

    Args:
        id: Task identifier.
        description: Task description.

    Returns:
        A Task instance.
    """
    def execute(params: dict, context: Any) -> dict:
        return dict(params.get("input_data", params))

    return Task(
        id=id,
        description=description or "No-op",
        input_schema=PassthroughInput,
        output_schema=PassthroughOutput,
        execute=execute,
    )
