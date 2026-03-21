"""Tests for the water eval CLI command and config module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from water.eval.config import EvalConfig, build_evaluators, build_cases
from water.eval.cli import _report_from_dict, cmd_eval_list
from water.eval.evaluators import ExactMatch, ContainsMatch, SemanticSimilarity
from water.eval.suite import EvalCase


# ---------------------------------------------------------------------------
# EvalConfig tests
# ---------------------------------------------------------------------------


class TestEvalConfigFromDict:
    def test_basic_dict(self):
        data = {
            "suite": "my_suite",
            "flow": "mymodule:my_flow",
            "evaluators": [{"type": "exact_match", "key": "answer"}],
            "cases": [{"input": {"q": "hello"}, "expected": {"answer": "hi"}}],
        }
        cfg = EvalConfig.from_dict(data)
        assert cfg.suite_name == "my_suite"
        assert cfg.flow_spec == "mymodule:my_flow"
        assert len(cfg.evaluators) == 1
        assert len(cfg.cases) == 1

    def test_defaults(self):
        cfg = EvalConfig.from_dict({})
        assert cfg.suite_name == "eval"
        assert cfg.flow_spec == ""
        assert cfg.evaluators == []
        assert cfg.cases == []

    def test_name_fallback(self):
        cfg = EvalConfig.from_dict({"name": "fallback_name"})
        assert cfg.suite_name == "fallback_name"

    def test_suite_takes_precedence_over_name(self):
        cfg = EvalConfig.from_dict({"suite": "primary", "name": "secondary"})
        assert cfg.suite_name == "primary"


class TestEvalConfigFromFile:
    def test_json_file(self, tmp_path):
        config_data = {
            "suite": "json_suite",
            "flow": "mod:f",
            "evaluators": [{"type": "exact_match"}],
            "cases": [{"input": {"x": 1}, "expected": {"y": 2}}],
        }
        config_file = tmp_path / "eval_config.json"
        config_file.write_text(json.dumps(config_data))

        cfg = EvalConfig.from_file(str(config_file))
        assert cfg.suite_name == "json_suite"
        assert cfg.flow_spec == "mod:f"
        assert len(cfg.evaluators) == 1
        assert len(cfg.cases) == 1

    def test_unsupported_format(self, tmp_path):
        bad_file = tmp_path / "config.toml"
        bad_file.write_text("key = 'value'")
        with pytest.raises(ValueError, match="Unsupported config format"):
            EvalConfig.from_file(str(bad_file))


# ---------------------------------------------------------------------------
# build_evaluators tests
# ---------------------------------------------------------------------------


class TestBuildEvaluators:
    def test_exact_match(self):
        configs = [{"type": "exact_match", "key": "answer"}]
        evaluators = build_evaluators(configs)
        assert len(evaluators) == 1
        assert isinstance(evaluators[0], ExactMatch)
        assert evaluators[0].key == "answer"

    def test_contains(self):
        configs = [{"type": "contains", "field": "text", "substrings": ["hello"]}]
        evaluators = build_evaluators(configs)
        assert len(evaluators) == 1
        assert isinstance(evaluators[0], ContainsMatch)
        assert evaluators[0].substrings == ["hello"]

    def test_semantic_similarity(self):
        configs = [{"type": "semantic_similarity", "key": "summary", "threshold": 0.8}]
        evaluators = build_evaluators(configs)
        assert len(evaluators) == 1
        assert isinstance(evaluators[0], SemanticSimilarity)
        assert evaluators[0].threshold == 0.8

    def test_unknown_type_skipped(self):
        configs = [{"type": "unknown_evaluator"}]
        evaluators = build_evaluators(configs)
        assert len(evaluators) == 0

    def test_multiple_evaluators(self):
        configs = [
            {"type": "exact_match", "key": "a"},
            {"type": "contains", "key": "b", "substrings": ["x"]},
            {"type": "semantic_similarity", "key": "c"},
        ]
        evaluators = build_evaluators(configs)
        assert len(evaluators) == 3
        assert isinstance(evaluators[0], ExactMatch)
        assert isinstance(evaluators[1], ContainsMatch)
        assert isinstance(evaluators[2], SemanticSimilarity)

    def test_empty_configs(self):
        evaluators = build_evaluators([])
        assert evaluators == []


# ---------------------------------------------------------------------------
# build_cases tests
# ---------------------------------------------------------------------------


class TestBuildCases:
    def test_basic_case(self):
        configs = [
            {"input": {"q": "hello"}, "expected": {"a": "world"}, "name": "greet"}
        ]
        cases = build_cases(configs)
        assert len(cases) == 1
        assert isinstance(cases[0], EvalCase)
        assert cases[0].name == "greet"
        assert cases[0].input == {"q": "hello"}
        assert cases[0].expected == {"a": "world"}

    def test_auto_name(self):
        configs = [{"input": {}, "expected": {}}]
        cases = build_cases(configs)
        assert cases[0].name == "case_0"

    def test_tags(self):
        configs = [{"input": {}, "expected": {}, "tags": ["fast", "unit"]}]
        cases = build_cases(configs)
        assert cases[0].tags == ["fast", "unit"]

    def test_empty_configs(self):
        cases = build_cases([])
        assert cases == []


# ---------------------------------------------------------------------------
# _report_from_dict tests
# ---------------------------------------------------------------------------


class TestReportFromDict:
    def test_basic_reconstruction(self):
        data = {
            "total_cases": 2,
            "passed_cases": 1,
            "failed_cases": 1,
            "avg_score": 0.75,
            "case_results": [
                {
                    "case_index": 0,
                    "input_data": {"q": "a"},
                    "expected": {"a": "b"},
                    "actual": {"a": "b"},
                    "scores": [],
                    "passed": True,
                    "avg_score": 1.0,
                },
                {
                    "case_index": 1,
                    "input_data": {"q": "c"},
                    "expected": {"a": "d"},
                    "actual": {"a": "e"},
                    "scores": [],
                    "passed": False,
                    "avg_score": 0.5,
                },
            ],
        }
        report = _report_from_dict(data)
        assert report.total_cases == 2
        assert report.passed_cases == 1
        assert report.failed_cases == 1
        assert report.avg_score == 0.75
        assert len(report.case_results) == 2
        assert report.case_results[0].passed is True
        assert report.case_results[1].passed is False

    def test_empty_data(self):
        report = _report_from_dict({})
        assert report.total_cases == 0
        assert report.case_results == []


# ---------------------------------------------------------------------------
# cmd_eval_list tests
# ---------------------------------------------------------------------------


class TestCmdEvalList:
    def test_finds_eval_configs(self, tmp_path, capsys):
        (tmp_path / "eval_suite.json").write_text("{}")
        (tmp_path / "my_eval.yaml").write_text("")
        (tmp_path / "other.json").write_text("{}")  # no 'eval' in name

        args = MagicMock()
        args.directory = str(tmp_path)
        cmd_eval_list(args)
        captured = capsys.readouterr()
        assert "2 eval configs" in captured.out
        assert "eval_suite.json" in captured.out
        assert "my_eval.yaml" in captured.out
        assert "other.json" not in captured.out

    def test_no_configs_found(self, tmp_path, capsys):
        args = MagicMock()
        args.directory = str(tmp_path)
        cmd_eval_list(args)
        captured = capsys.readouterr()
        assert "No eval config files found" in captured.out
