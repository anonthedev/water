"""
Flow Versioning Advanced Example: Schema Registry & Migration

This example demonstrates Water's advanced versioning features for tracking
schema changes across flow versions and migrating data between versions.
It shows:
  - FlowVersion for semantic versioning of flows
  - SchemaRegistry for registering and tracking schema history
  - CompatibilityChecker for detecting breaking changes
  - Migration functions for transforming data between versions

NOTE: This example uses mock schema snapshots and runs without any
      external dependencies. For basic versioning, see versioning_flow.py.
"""

import asyncio
from typing import Any, Dict

from water.core.versioning import (
    FlowVersion,
    SchemaChange,
    CompatibilityChecker,
    SchemaRegistry,
)


# ---------------------------------------------------------------------------
# Example 1: FlowVersion parsing and comparison
# ---------------------------------------------------------------------------

async def example_flow_version():
    """Parse, compare, and inspect flow versions."""
    print("=== Example 1: FlowVersion Parsing & Comparison ===\n")

    # Parse version strings
    v1 = FlowVersion.parse("1.0.0")
    v2 = FlowVersion.parse("1.1.0")
    v3 = FlowVersion.parse("2.0.0")

    print(f"v1 = {v1}")
    print(f"v2 = {v2}")
    print(f"v3 = {v3}")
    print()

    # Comparisons
    print(f"v1 < v2:  {v1 < v2}")
    print(f"v2 < v3:  {v2 < v3}")
    print(f"v1 == v1: {v1 == FlowVersion.parse('1.0.0')}")
    print(f"v1 <= v2: {v1 <= v2}")
    print()

    # Attach schema snapshot
    v1.schema_snapshot = {
        "normalize": {"input.value": "float", "output.normalized": "float"},
    }
    print(f"v1 with schema: {v1.to_dict()}")
    print()


# ---------------------------------------------------------------------------
# Example 2: CompatibilityChecker for detecting breaking changes
# ---------------------------------------------------------------------------

async def example_compatibility_checker():
    """Detect breaking and non-breaking changes between schemas."""
    print("=== Example 2: CompatibilityChecker ===\n")

    # Schema v1: original
    old_schema = {
        "name": "str",
        "email": "str",
        "age": "int",
    }

    # Schema v2: added field (non-breaking for output), removed field
    new_schema = {
        "name": "str",
        "email": "str",
        "phone": "str",       # added
        # "age" removed
    }

    # Check output schema changes (removing a field is breaking)
    changes = CompatibilityChecker.check(old_schema, new_schema, task_id="user_task", direction="output")
    print("Output schema changes (v1 -> v2):")
    for c in changes:
        print(f"  {c.change_type}: {c.field_name} (breaking={c.breaking}) - {c.details}")
    compatible = CompatibilityChecker.is_compatible(changes)
    print(f"  Compatible: {compatible}")
    print()

    # Check input schema changes (adding a field is breaking for input)
    changes = CompatibilityChecker.check(old_schema, new_schema, task_id="user_task", direction="input")
    print("Input schema changes (v1 -> v2):")
    for c in changes:
        print(f"  {c.change_type}: {c.field_name} (breaking={c.breaking}) - {c.details}")
    compatible = CompatibilityChecker.is_compatible(changes)
    print(f"  Compatible: {compatible}")
    print()

    # Type change (always breaking)
    old_typed = {"score": "int"}
    new_typed = {"score": "float"}
    changes = CompatibilityChecker.check(old_typed, new_typed, task_id="score_task")
    print("Type change:")
    for c in changes:
        print(f"  {c.change_type}: {c.field_name} (breaking={c.breaking}) - {c.details}")
    print()


# ---------------------------------------------------------------------------
# Example 3: SchemaRegistry with versioning and migrations
# ---------------------------------------------------------------------------

async def example_schema_registry():
    """Register versions, check compatibility, and migrate data."""
    print("=== Example 3: SchemaRegistry & Data Migration ===\n")

    registry = SchemaRegistry()

    # Register v1.0.0
    registry.register_version(
        flow_id="user_pipeline",
        version="1.0.0",
        schema_snapshot={
            "fetch_user": {"name": "str", "email": "str"},
            "enrich": {"name": "str", "email": "str", "score": "int"},
        },
    )

    # Register v1.1.0 (added phone field to enrich)
    registry.register_version(
        flow_id="user_pipeline",
        version="1.1.0",
        schema_snapshot={
            "fetch_user": {"name": "str", "email": "str"},
            "enrich": {"name": "str", "email": "str", "score": "int", "phone": "str"},
        },
    )

    # Register v2.0.0 (score changed from int to float, removed email from enrich)
    registry.register_version(
        flow_id="user_pipeline",
        version="2.0.0",
        schema_snapshot={
            "fetch_user": {"name": "str", "email": "str"},
            "enrich": {"name": "str", "score": "float", "phone": "str"},
        },
    )

    # List versions
    versions = registry.list_versions("user_pipeline")
    print(f"Registered versions: {versions}")
    print()

    # Check compatibility between versions
    changes_1_to_1_1 = registry.check_compatibility("user_pipeline", "1.0.0", "1.1.0")
    breaking_1_to_1_1 = [c for c in changes_1_to_1_1 if c.breaking]
    print(f"v1.0.0 -> v1.1.0: {len(changes_1_to_1_1)} changes, {len(breaking_1_to_1_1)} breaking")
    for c in changes_1_to_1_1:
        print(f"  [{c.task_id}] {c.change_type}: {c.field_name} (breaking={c.breaking})")
    print()

    changes_1_1_to_2 = registry.check_compatibility("user_pipeline", "1.1.0", "2.0.0")
    breaking_1_1_to_2 = [c for c in changes_1_1_to_2 if c.breaking]
    print(f"v1.1.0 -> v2.0.0: {len(changes_1_1_to_2)} changes, {len(breaking_1_1_to_2)} breaking")
    for c in changes_1_1_to_2:
        print(f"  [{c.task_id}] {c.change_type}: {c.field_name} (breaking={c.breaking})")
    print()

    # Register migrations
    def migrate_1_to_1_1(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add default phone field."""
        result = dict(data)
        result.setdefault("phone", "")
        return result

    def migrate_1_1_to_2(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert score to float, remove email."""
        result = dict(data)
        if "score" in result:
            result["score"] = float(result["score"])
        result.pop("email", None)
        return result

    registry.add_migration("user_pipeline", "1.0.0", "1.1.0", migrate_1_to_1_1,
                           description="Add phone field with default")
    registry.add_migration("user_pipeline", "1.1.0", "2.0.0", migrate_1_1_to_2,
                           description="Convert score type, remove email")

    # Migrate data from v1.0.0 to v2.0.0 (two-step chain)
    old_data = {"name": "Alice", "email": "alice@example.com", "score": 85}
    migrated = registry.migrate_data("user_pipeline", old_data, "1.0.0", "2.0.0")
    print(f"Original (v1.0.0): {old_data}")
    print(f"Migrated (v2.0.0): {migrated}")
    print()

    # Verify no migration needed for same version
    same = registry.migrate_data("user_pipeline", old_data, "1.0.0", "1.0.0")
    print(f"Same version migration: {same == old_data}")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_flow_version()
    await example_compatibility_checker()
    await example_schema_registry()
    print("All versioning examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
