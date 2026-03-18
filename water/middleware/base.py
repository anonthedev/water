"""
Middleware support for Water flows.

Middleware intercepts task execution, allowing data transformation or logging
between tasks without explicit task nodes. Each middleware has ``before_task``
and ``after_task`` hooks that can inspect or modify the data flowing through
the pipeline.
"""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class Middleware:
    """
    Base middleware class.

    Subclass and override ``before_task`` and/or ``after_task`` to intercept
    task execution.  Both methods receive the current data and must return
    the (possibly modified) data dict.
    """

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        """Called before each task executes. Return (possibly modified) data."""
        return data

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        """Called after each task executes. Return (possibly modified) result."""
        return result
