"""
water.triggers -- Webhook, Cron, and Queue triggers for event-driven flows.

Provides a registry and concrete trigger implementations that watch for
external events and automatically invoke Water flows.
"""

from typing import Dict, List, Optional

from water.triggers.base import Trigger, TriggerEvent
from water.triggers.webhook import WebhookTrigger
from water.triggers.cron import CronTrigger
from water.triggers.queue import QueueTrigger


class TriggerRegistry:
    """Central registry that manages the lifecycle of all triggers.

    Example::

        registry = TriggerRegistry()
        registry.add(WebhookTrigger("my-flow", path="/hooks/github"))
        registry.add(CronTrigger("nightly-job", schedule="0 0 * * *"))
        await registry.start_all()
    """

    def __init__(self) -> None:
        self._triggers: List[Trigger] = []

    def add(self, trigger: Trigger) -> None:
        """Register a trigger.

        Args:
            trigger: The trigger instance to add.
        """
        self._triggers.append(trigger)

    def remove(self, flow_name: str) -> None:
        """Remove all triggers bound to a given flow.

        Args:
            flow_name: The flow ID whose triggers should be removed.
        """
        self._triggers = [t for t in self._triggers if t.flow_name != flow_name]

    def get_triggers(self, flow_name: str) -> List[Trigger]:
        """Return all triggers bound to a specific flow.

        Args:
            flow_name: The flow ID to filter by.

        Returns:
            List of matching trigger instances.
        """
        return [t for t in self._triggers if t.flow_name == flow_name]

    def list_all(self) -> List[Trigger]:
        """Return every registered trigger.

        Returns:
            List of all trigger instances.
        """
        return list(self._triggers)

    async def start_all(self) -> None:
        """Start every registered trigger."""
        for trigger in self._triggers:
            await trigger.start()

    async def stop_all(self) -> None:
        """Stop every registered trigger."""
        for trigger in self._triggers:
            await trigger.stop()

    @property
    def count(self) -> int:
        """Total number of registered triggers."""
        return len(self._triggers)


__all__ = [
    "Trigger",
    "TriggerEvent",
    "WebhookTrigger",
    "CronTrigger",
    "QueueTrigger",
    "TriggerRegistry",
]
