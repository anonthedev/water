"""Base trigger classes for event-driven flow execution."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List
from abc import ABC, abstractmethod
from datetime import datetime
import uuid


@dataclass
class TriggerEvent:
    """Represents an event that triggers a flow execution.

    Attributes:
        source: The source type of the trigger (e.g., "webhook", "cron", "queue").
        timestamp: ISO-format timestamp of when the event occurred.
        payload: The event data to be passed to the flow.
        trigger_id: Unique identifier for this event instance.
        metadata: Additional metadata about the trigger event.
    """

    source: str
    timestamp: str
    payload: Dict[str, Any]
    trigger_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trigger_id:
            self.trigger_id = uuid.uuid4().hex[:12]
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class Trigger(ABC):
    """Abstract base class for all trigger types.

    A Trigger watches for external events and fires flow executions
    when conditions are met.

    Args:
        flow_name: The ID of the flow this trigger is bound to.
        transform: Optional callable to transform the incoming payload
                   before passing it to the flow.
    """

    def __init__(self, flow_name: str, transform: Optional[Callable] = None) -> None:
        self.flow_name = flow_name
        self.transform = transform
        self._active = False

    @abstractmethod
    async def start(self) -> None:
        """Activate the trigger so it begins listening for events."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Deactivate the trigger and clean up resources."""
        ...

    def transform_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the optional transform function to the payload.

        Args:
            payload: Raw event payload.

        Returns:
            Transformed payload if a transform is set, otherwise the
            original payload unchanged.
        """
        if self.transform:
            return self.transform(payload)
        return payload

    @property
    def active(self) -> bool:
        """Whether this trigger is currently active."""
        return self._active

    def create_event(self, payload: Dict[str, Any], **metadata: Any) -> TriggerEvent:
        """Helper to create a TriggerEvent from this trigger.

        Args:
            payload: The event payload data.
            **metadata: Additional metadata key-value pairs.

        Returns:
            A new TriggerEvent instance.
        """
        return TriggerEvent(
            source=self.__class__.__name__,
            timestamp=datetime.utcnow().isoformat(),
            payload=self.transform_payload(payload),
            metadata=metadata,
        )
