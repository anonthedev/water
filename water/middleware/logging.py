"""LoggingMiddleware — logs task_id, input keys, and output keys."""

import logging
from typing import Any, Optional

from water.middleware.base import Middleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(Middleware):
    """
    Middleware that logs task_id, input keys, and output keys for every task.

    Does **not** modify the data — purely observational.
    """

    def __init__(self, logger_instance: Optional[logging.Logger] = None) -> None:
        self._logger = logger_instance or logger

    async def before_task(self, task_id: str, data: dict, context: Any) -> dict:
        self._logger.info(
            "Middleware [before] task=%s input_keys=%s",
            task_id,
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        return data

    async def after_task(self, task_id: str, data: dict, result: dict, context: Any) -> dict:
        self._logger.info(
            "Middleware [after]  task=%s output_keys=%s",
            task_id,
            list(result.keys()) if isinstance(result, dict) else type(result).__name__,
        )
        return result
