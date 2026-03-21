"""
Flow Versioning & Migration System.

Tracks schema changes across flow versions and provides migration
utilities for backward compatibility.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class FlowVersion:
    """Semantic version attached to a flow with schema snapshot."""
    major: int
    minor: int
    patch: int
    schema_snapshot: Optional[Dict[str, Any]] = None

    @classmethod
    def parse(cls, version_str: str) -> "FlowVersion":
        """Parse a semver string like '1.2.3'."""
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str.strip())
        if not match:
            raise ValueError(f"Invalid version format: {version_str!r}. Expected 'major.minor.patch'")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, FlowVersion):
            return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
        return NotImplemented

    def __lt__(self, other: "FlowVersion") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: "FlowVersion") -> bool:
        return self == other or self < other

    def to_dict(self) -> dict:
        return {
            "version": str(self),
            "schema_snapshot": self.schema_snapshot,
        }


@dataclass
class SchemaChange:
    """Describes a single change between two versions."""
    change_type: str  # "field_added", "field_removed", "type_changed", "required_added"
    field_name: str
    task_id: str
    direction: str  # "input" or "output"
    details: str = ""
    breaking: bool = False

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type,
            "field_name": self.field_name,
            "task_id": self.task_id,
            "direction": self.direction,
            "details": self.details,
            "breaking": self.breaking,
        }


class CompatibilityChecker:
    """
    Detects breaking changes between flow versions.

    A breaking change is defined as:
    - Removing a field from output schema
    - Changing a field's type
    - Adding a required field to input schema
    """

    @staticmethod
    def check(
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        task_id: str = "",
        direction: str = "output",
    ) -> List[SchemaChange]:
        """
        Compare two schema snapshots and return list of changes.

        Args:
            old_schema: Previous version schema (field_name -> type_name).
            new_schema: Current version schema.
            task_id: Task ID for context.
            direction: "input" or "output".

        Returns:
            List of SchemaChange describing differences.
        """
        changes = []
        old_fields = set(old_schema.keys())
        new_fields = set(new_schema.keys())

        # Removed fields (breaking for output)
        for f in old_fields - new_fields:
            changes.append(SchemaChange(
                change_type="field_removed",
                field_name=f,
                task_id=task_id,
                direction=direction,
                details=f"Field '{f}' removed",
                breaking=(direction == "output"),
            ))

        # Added fields (breaking if required input)
        for f in new_fields - old_fields:
            is_breaking = (direction == "input")
            changes.append(SchemaChange(
                change_type="field_added",
                field_name=f,
                task_id=task_id,
                direction=direction,
                details=f"Field '{f}' added",
                breaking=is_breaking,
            ))

        # Type changes (always breaking)
        for f in old_fields & new_fields:
            if old_schema[f] != new_schema[f]:
                changes.append(SchemaChange(
                    change_type="type_changed",
                    field_name=f,
                    task_id=task_id,
                    direction=direction,
                    details=f"Field '{f}' type changed from {old_schema[f]} to {new_schema[f]}",
                    breaking=True,
                ))

        return changes

    @staticmethod
    def is_compatible(changes: List[SchemaChange]) -> bool:
        """Return True if there are no breaking changes."""
        return not any(c.breaking for c in changes)


@dataclass
class MigrationStep:
    """A single migration from one version to another."""
    from_version: str
    to_version: str
    migrate_fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    description: str = ""


class SchemaRegistry:
    """
    Tracks schema history per flow ID.

    Stores schema snapshots for each version, migration functions,
    and provides compatibility checking.
    """

    def __init__(self):
        self._schemas: Dict[str, Dict[str, FlowVersion]] = {}  # flow_id -> {version_str -> FlowVersion}
        self._migrations: Dict[str, List[MigrationStep]] = {}  # flow_id -> [MigrationStep]

    def register_version(
        self,
        flow_id: str,
        version: str,
        schema_snapshot: Dict[str, Any],
    ) -> FlowVersion:
        """
        Register a flow version with its schema snapshot.

        Args:
            flow_id: Flow identifier.
            version: Semantic version string.
            schema_snapshot: Dict of {task_id: {field: type}} describing schemas.

        Returns:
            The registered FlowVersion.
        """
        fv = FlowVersion.parse(version)
        fv.schema_snapshot = schema_snapshot

        if flow_id not in self._schemas:
            self._schemas[flow_id] = {}
        self._schemas[flow_id][version] = fv

        return fv

    def get_version(self, flow_id: str, version: str) -> Optional[FlowVersion]:
        """Get a registered flow version."""
        return self._schemas.get(flow_id, {}).get(version)

    def list_versions(self, flow_id: str) -> List[str]:
        """List all registered versions for a flow."""
        versions = list(self._schemas.get(flow_id, {}).keys())
        versions.sort(key=lambda v: FlowVersion.parse(v))
        return versions

    def add_migration(
        self,
        flow_id: str,
        from_version: str,
        to_version: str,
        migrate_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        description: str = "",
    ) -> None:
        """
        Register a migration function between two versions.

        Args:
            flow_id: Flow identifier.
            from_version: Source version.
            to_version: Target version.
            migrate_fn: Function that transforms data from old to new format.
            description: Human-readable migration description.
        """
        if flow_id not in self._migrations:
            self._migrations[flow_id] = []
        self._migrations[flow_id].append(MigrationStep(
            from_version=from_version,
            to_version=to_version,
            migrate_fn=migrate_fn,
            description=description,
        ))

    def check_compatibility(
        self,
        flow_id: str,
        from_version: str,
        to_version: str,
    ) -> List[SchemaChange]:
        """
        Check compatibility between two versions.

        Returns list of changes (empty = fully compatible).
        """
        old_fv = self.get_version(flow_id, from_version)
        new_fv = self.get_version(flow_id, to_version)

        if not old_fv or not new_fv:
            return []

        old_snap = old_fv.schema_snapshot or {}
        new_snap = new_fv.schema_snapshot or {}

        all_changes = []
        all_tasks = set(list(old_snap.keys()) + list(new_snap.keys()))

        for task_id in all_tasks:
            old_task = old_snap.get(task_id, {})
            new_task = new_snap.get(task_id, {})
            changes = CompatibilityChecker.check(old_task, new_task, task_id=task_id)
            all_changes.extend(changes)

        return all_changes

    def migrate_data(
        self,
        flow_id: str,
        data: Dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> Dict[str, Any]:
        """
        Apply migration chain to transform data between versions.

        Finds a migration path from from_version to to_version and
        applies each step in sequence.

        Args:
            flow_id: Flow identifier.
            data: Data to migrate.
            from_version: Current data version.
            to_version: Target version.

        Returns:
            Migrated data.

        Raises:
            ValueError: If no migration path exists.
        """
        if from_version == to_version:
            return data

        migrations = self._migrations.get(flow_id, [])
        path = self._find_migration_path(migrations, from_version, to_version)

        if not path:
            raise ValueError(
                f"No migration path found from {from_version} to {to_version} "
                f"for flow {flow_id}"
            )

        result = dict(data)
        for step in path:
            result = step.migrate_fn(result)

        return result

    @staticmethod
    def _find_migration_path(
        migrations: List[MigrationStep],
        from_version: str,
        to_version: str,
    ) -> List[MigrationStep]:
        """Find a chain of migrations from source to target version."""
        # BFS to find shortest path
        from collections import deque

        graph: Dict[str, List[MigrationStep]] = {}
        for m in migrations:
            graph.setdefault(m.from_version, []).append(m)

        queue = deque([(from_version, [])])
        visited = {from_version}

        while queue:
            current, path = queue.popleft()
            if current == to_version:
                return path

            for step in graph.get(current, []):
                if step.to_version not in visited:
                    visited.add(step.to_version)
                    queue.append((step.to_version, path + [step]))

        return []


def snapshot_flow_schemas(flow: Any) -> Dict[str, Dict[str, str]]:
    """
    Extract schema snapshots from a flow's tasks.

    Returns a dict of {task_id: {field_name: type_name}} for all
    sequential tasks in the flow.
    """
    from water.core.engine import NodeType

    snapshot = {}
    for node in getattr(flow, "_tasks", []):
        node_type = node.get("type", "")
        task = node.get("task")
        if task and hasattr(task, "input_schema"):
            task_schema = {}
            input_fields = _get_fields(task.input_schema)
            output_fields = _get_fields(getattr(task, "output_schema", None))
            if input_fields:
                task_schema.update({f"input.{k}": v for k, v in input_fields.items()})
            if output_fields:
                task_schema.update({f"output.{k}": v for k, v in output_fields.items()})
            if task_schema:
                snapshot[task.id] = task_schema
    return snapshot


def _get_fields(schema: Any) -> Optional[Dict[str, str]]:
    """Extract field names and types from a Pydantic model."""
    if schema is None:
        return None
    if hasattr(schema, "model_fields"):
        return {k: str(v.annotation) for k, v in schema.model_fields.items()}
    if hasattr(schema, "__fields__"):
        return {k: str(v.outer_type_) for k, v in schema.__fields__.items()}
    return None
