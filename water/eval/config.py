# water/eval/config.py
"""
YAML/JSON configuration loader for eval suites.

Allows defining eval suites declaratively via config files,
specifying the flow, evaluators, and test cases.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path


@dataclass
class EvalConfig:
    """Parsed eval configuration."""

    suite_name: str = "eval"
    flow_spec: str = ""  # module:flow_var
    evaluators: List[Dict[str, Any]] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalConfig":
        """Build an EvalConfig from a plain dictionary."""
        return cls(
            suite_name=data.get("suite", data.get("name", "eval")),
            flow_spec=data.get("flow", ""),
            evaluators=data.get("evaluators", []),
            cases=data.get("cases", []),
        )

    @classmethod
    def from_file(cls, path: str) -> "EvalConfig":
        """Load an EvalConfig from a YAML or JSON file."""
        p = Path(path)
        text = p.read_text()
        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml

                data = yaml.safe_load(text)
            except ImportError:
                raise ImportError(
                    "PyYAML required for YAML config files. pip install pyyaml"
                )
        elif p.suffix == ".json":
            data = json.loads(text)
        else:
            raise ValueError(f"Unsupported config format: {p.suffix}")
        return cls.from_dict(data)


def build_evaluators(configs: List[Dict[str, Any]]):
    """Build Evaluator instances from config dicts."""
    from water.eval.evaluators import ExactMatch, ContainsMatch, SemanticSimilarity

    evaluators = []
    for cfg in configs:
        eval_type = cfg.get("type", "")
        if eval_type == "exact_match":
            evaluators.append(
                ExactMatch(key=cfg.get("key", cfg.get("field", "")))
            )
        elif eval_type == "contains":
            keys = cfg.get("keys", [])
            if cfg.get("key"):
                keys = [cfg["key"]]
            evaluators.append(
                ContainsMatch(
                    key=cfg.get("field", ""),
                    substrings=cfg.get("substrings", []),
                    keys=keys,
                )
            )
        elif eval_type == "semantic_similarity":
            evaluators.append(
                SemanticSimilarity(
                    key=cfg.get("key", cfg.get("field", "")),
                    threshold=cfg.get("threshold", 0.7),
                )
            )
        else:
            pass  # Skip unknown evaluators
    return evaluators


def build_cases(configs: List[Dict[str, Any]]):
    """Build EvalCase instances from config dicts."""
    from water.eval.suite import EvalCase

    cases = []
    for i, cfg in enumerate(configs):
        cases.append(
            EvalCase(
                input=cfg.get("input", {}),
                expected=cfg.get("expected", {}),
                name=cfg.get("name", f"case_{i}"),
                tags=cfg.get("tags", []),
            )
        )
    return cases
