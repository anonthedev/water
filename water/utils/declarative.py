"""
Declarative flow definitions for the Water framework.

Allows defining flows via YAML/JSON configuration dicts instead of Python code.
"""

import json
from typing import Any, Callable, Dict, List, Optional, Union

from water.core.flow import Flow


def _resolve_task(task_id: str, task_registry: dict) -> Any:
    """Look up a task by ID in the registry, raising ValueError if not found."""
    if task_id not in task_registry:
        raise ValueError(
            f"Unknown task '{task_id}' in flow definition. "
            f"Available tasks: {list(task_registry.keys())}"
        )
    return task_registry[task_id]


def _resolve_condition(condition_name: str, task_registry: dict) -> Callable:
    """Look up a condition function by name in the registry."""
    if condition_name not in task_registry:
        raise ValueError(
            f"Unknown condition '{condition_name}' in flow definition. "
            f"Available entries: {list(task_registry.keys())}"
        )
    cond = task_registry[condition_name]
    if not callable(cond):
        raise ValueError(
            f"Registry entry '{condition_name}' is not callable — "
            f"conditions must be functions"
        )
    return cond


def load_flow_from_dict(config: dict, task_registry: dict) -> Flow:
    """
    Parse a dict configuration into a registered Flow.

    Args:
        config: Flow definition dict with keys:
            - id (str): Flow identifier
            - description (str): Human-readable description
            - version (str, optional): Flow version
            - steps (list): List of step definitions
        task_registry: Mapping of task_id/condition_name to Task instances
                       or condition callables.

    Returns:
        A registered Flow ready to execute.

    Raises:
        ValueError: If a referenced task or condition is not in the registry,
                    or if a step type is unknown.
    """
    flow_id = config.get("id", None)
    description = config.get("description", None)
    version = config.get("version", None)

    flow = Flow(id=flow_id, description=description, version=version)

    steps = config.get("steps", [])
    if not steps:
        raise ValueError("Flow definition must contain at least one step")

    for step in steps:
        step_type = step.get("type")
        if step_type is None:
            raise ValueError(f"Step is missing 'type' field: {step}")

        if step_type == "sequential":
            task = _resolve_task(step["task"], task_registry)
            when = None
            if "when" in step:
                when = _resolve_condition(step["when"], task_registry)
            fallback = None
            if "fallback" in step:
                fallback = _resolve_task(step["fallback"], task_registry)
            flow.then(task, when=when, fallback=fallback)

        elif step_type == "parallel":
            task_ids = step["tasks"]
            tasks = [_resolve_task(tid, task_registry) for tid in task_ids]
            flow.parallel(tasks)

        elif step_type == "branch":
            branch_defs = step["branches"]
            branches = []
            for branch_def in branch_defs:
                condition_fn = _resolve_condition(
                    branch_def["condition"], task_registry
                )
                task = _resolve_task(branch_def["task"], task_registry)
                branches.append((condition_fn, task))
            flow.branch(branches)

        elif step_type == "loop":
            condition_fn = _resolve_condition(step["condition"], task_registry)
            task = _resolve_task(step["task"], task_registry)
            max_iterations = step.get("max_iterations", 100)
            flow.loop(condition_fn, task, max_iterations=max_iterations)

        elif step_type == "map":
            task = _resolve_task(step["task"], task_registry)
            over = step["over"]
            flow.map(task, over=over)

        elif step_type == "dag":
            task_ids = step["tasks"]
            tasks = [_resolve_task(tid, task_registry) for tid in task_ids]
            dependencies = step.get("dependencies", {})
            flow.dag(tasks, dependencies=dependencies)

        else:
            raise ValueError(f"Unknown step type '{step_type}'")

    flow.register()
    return flow


def load_flow_from_yaml(yaml_str: str, task_registry: dict) -> Flow:
    """
    Parse a YAML string into a registered Flow.

    Args:
        yaml_str: YAML-formatted flow definition string.
        task_registry: Mapping of task_id/condition_name to Task instances
                       or condition callables.

    Returns:
        A registered Flow ready to execute.

    Raises:
        ImportError: If PyYAML is not installed.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML flow definitions. "
            "Install it with: pip install pyyaml"
        )

    config = yaml.safe_load(yaml_str)
    return load_flow_from_dict(config, task_registry)


def load_flow_from_json(json_str: str, task_registry: dict) -> Flow:
    """
    Parse a JSON string into a registered Flow.

    Args:
        json_str: JSON-formatted flow definition string.
        task_registry: Mapping of task_id/condition_name to Task instances
                       or condition callables.

    Returns:
        A registered Flow ready to execute.
    """
    config = json.loads(json_str)
    return load_flow_from_dict(config, task_registry)
