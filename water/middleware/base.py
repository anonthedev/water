"""
Middleware support for Water flows.

Middleware intercepts task execution, allowing data transformation or logging
between tasks without explicit task nodes. Each middleware has ``before_task``
and ``after_task`` hooks that can inspect or modify the data flowing through
the pipeline.

Execution order
---------------
Middleware instances are sorted by their ``order`` attribute (ascending) before
being applied.  For each task execution:

1. **before_task** hooks run top-down (lowest ``order`` first).  Each
   ``before_task`` receives the data returned by the previous middleware, so
   earlier middleware can transform input before later ones see it.

2. The task itself executes.

3. **after_task** hooks run bottom-up (highest ``order`` first).  This mirrors
   the "onion" model used by many web frameworks: the middleware that touched
   the request first is the last to touch the response.

Set the ``order`` attribute on your middleware subclass (or pass it to the
constructor) to control where it sits in the chain.  The default order is
``0``.
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

    Attributes:
        order: Integer that controls execution priority. Middleware with lower
            ``order`` values run their ``before_task`` first and their
            ``after_task`` last (onion model). Default is ``0``.
    """

    def __init__(self, order: int = 0) -> None:
        self.order: int = order

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        """Called before each task executes. Return (possibly modified) data."""
        return data

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        """Called after each task executes. Return (possibly modified) result."""
        return result
