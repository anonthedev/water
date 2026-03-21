"""
Data transformation tasks for Water.

JSONPath-style extraction, field mapping, and filtering.
"""

from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from water.core.task import Task


class TransformInput(BaseModel):
    data: Any = None


class TransformOutput(BaseModel):
    data: Any = None


def json_transform(
    id: str,
    expression: str = "",
    description: Optional[str] = None,
) -> Task:
    """
    Create a data transformation task using dot-notation path extraction.

    Supports simple paths like "user.email" or "data.items" for nested access.
    Use "$." prefix for JSONPath-style syntax (basic support).

    Args:
        id: Task identifier.
        expression: Dot-notation path to extract (e.g., "user.email", "$.data.items").
        description: Task description.

    Returns:
        A Task instance.
    """
    def execute(params: dict, context: Any) -> dict:
        data = params.get("input_data", params)
        path = expression.lstrip("$.")

        result = _extract_path(data, path)
        return {"data": result, **{k: v for k, v in data.items() if k != "data"}}

    return Task(
        id=id,
        description=description or f"JSON transform: {expression}",
        input_schema=TransformInput,
        output_schema=TransformOutput,
        execute=execute,
    )


def map_fields(
    id: str,
    field_map: Dict[str, str],
    description: Optional[str] = None,
) -> Task:
    """
    Create a field mapping task that renames keys.

    Args:
        id: Task identifier.
        field_map: Dict of {old_name: new_name}.
        description: Task description.

    Returns:
        A Task instance.
    """
    def execute(params: dict, context: Any) -> dict:
        data = params.get("input_data", params)
        result = {}
        for key, value in data.items():
            new_key = field_map.get(key, key)
            result[new_key] = value
        return result

    return Task(
        id=id,
        description=description or f"Map fields: {field_map}",
        input_schema=TransformInput,
        output_schema=TransformOutput,
        execute=execute,
    )


def filter_fields(
    id: str,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> Task:
    """
    Create a field filtering task.

    Args:
        id: Task identifier.
        include: Whitelist of fields to keep (mutually exclusive with exclude).
        exclude: Blacklist of fields to remove.
        description: Task description.

    Returns:
        A Task instance.
    """
    def execute(params: dict, context: Any) -> dict:
        data = params.get("input_data", params)
        if include:
            return {k: v for k, v in data.items() if k in include}
        if exclude:
            return {k: v for k, v in data.items() if k not in exclude}
        return dict(data)

    return Task(
        id=id,
        description=description or "Filter fields",
        input_schema=TransformInput,
        output_schema=TransformOutput,
        execute=execute,
    )


def _extract_path(data: Any, path: str) -> Any:
    """Extract a value from nested data using dot-notation."""
    if not path:
        return data

    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current
