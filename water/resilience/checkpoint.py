__all__ = [
    "CheckpointBackend",
    "InMemoryCheckpoint",
]

"""
Checkpoint backend for crash recovery in long-running flows.

Saves intermediate state after each node so flows can resume from
the last successful node instead of starting over.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class CheckpointBackend(ABC):
    """Abstract base class for checkpoint storage backends."""

    @abstractmethod
    async def save(
        self, flow_id: str, execution_id: str, node_index: int, data: dict
    ) -> None:
        """
        Save a checkpoint after a node completes successfully.

        Args:
            flow_id: Unique identifier for the flow definition.
            execution_id: Unique identifier for this particular execution.
            node_index: The index of the *next* node to execute on resume.
            data: The output data produced so far (input to the next node).
        """

    @abstractmethod
    async def load(
        self, flow_id: str, execution_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load the most recent checkpoint for an execution.

        Returns:
            A dict with ``node_index`` and ``data`` keys, or ``None`` if no
            checkpoint exists.
        """

    @abstractmethod
    async def clear(self, flow_id: str, execution_id: str) -> None:
        """
        Remove the checkpoint for an execution (e.g. on successful completion).
        """


class InMemoryCheckpoint(CheckpointBackend):
    """Simple in-memory checkpoint backend backed by a Python dict."""

    def __init__(self) -> None:
        self._store: Dict[tuple, Dict[str, Any]] = {}

    async def save(
        self, flow_id: str, execution_id: str, node_index: int, data: dict
    ) -> None:
        self._store[(flow_id, execution_id)] = {
            "node_index": node_index,
            "data": data,
        }

    async def load(
        self, flow_id: str, execution_id: str
    ) -> Optional[Dict[str, Any]]:
        return self._store.get((flow_id, execution_id))

    async def clear(self, flow_id: str, execution_id: str) -> None:
        self._store.pop((flow_id, execution_id), None)
