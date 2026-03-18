"""
Tests for the Water CLI commands: run, visualize, dry-run, list.
"""

import json
import subprocess
import sys
import os
import pytest

# Ensure the project root is on sys.path so 'tests.sample_flow_for_cli' is importable.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Helper: _import_flow
# ---------------------------------------------------------------------------

class TestImportFlowHelper:
    def test_import_flow_valid(self):
        from water.cli import _import_flow
        flow = _import_flow("tests.sample_flow_for_cli:hello_flow")
        from water.flow import Flow
        assert isinstance(flow, Flow)
        assert flow.id == "hello"

    def test_import_flow_missing_colon(self):
        from water.cli import _import_flow
        with pytest.raises(ValueError, match="Invalid spec"):
            _import_flow("tests.sample_flow_for_cli")

    def test_import_flow_bad_module(self):
        from water.cli import _import_flow
        with pytest.raises(ImportError):
            _import_flow("nonexistent_module_xyz:foo")

    def test_import_flow_bad_variable(self):
        from water.cli import _import_flow
        with pytest.raises(AttributeError):
            _import_flow("tests.sample_flow_for_cli:no_such_var")

    def test_import_flow_not_a_flow(self):
        from water.cli import _import_flow
        with pytest.raises(TypeError, match="not a Flow instance"):
            _import_flow("tests.sample_flow_for_cli:greet_task")


# ---------------------------------------------------------------------------
# Helpers for subprocess-based CLI tests
# ---------------------------------------------------------------------------

def run_cli(*args, input_data=None):
    """Run the water CLI as a subprocess and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "-m", "water.cli"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_run_with_input(self):
        rc, stdout, stderr = run_cli(
            "run",
            "tests.sample_flow_for_cli:hello_flow",
            "--input", '{"name": "Water"}',
        )
        assert rc == 0, f"stderr: {stderr}"
        output = json.loads(stdout)
        assert output["greeting"] == "Hello, Water!"

    def test_run_without_input(self):
        rc, stdout, stderr = run_cli(
            "run",
            "tests.sample_flow_for_cli:hello_flow",
        )
        assert rc == 0, f"stderr: {stderr}"
        output = json.loads(stdout)
        assert "Hello" in output["greeting"]

    def test_run_bad_spec(self):
        rc, stdout, stderr = run_cli("run", "bad_spec_no_colon")
        assert rc != 0
        assert "Invalid spec" in stderr

    def test_run_bad_json(self):
        rc, stdout, stderr = run_cli(
            "run",
            "tests.sample_flow_for_cli:hello_flow",
            "--input", "not-json",
        )
        assert rc != 0
        assert "Invalid JSON" in stderr


class TestVisualizeCommand:
    def test_visualize_stdout(self):
        rc, stdout, stderr = run_cli(
            "visualize",
            "tests.sample_flow_for_cli:hello_flow",
        )
        assert rc == 0, f"stderr: {stderr}"
        assert "graph TD" in stdout

    def test_visualize_output_file(self, tmp_path):
        output_file = str(tmp_path / "diagram.md")
        rc, stdout, stderr = run_cli(
            "visualize",
            "tests.sample_flow_for_cli:hello_flow",
            "--output", output_file,
        )
        assert rc == 0, f"stderr: {stderr}"
        assert "Diagram saved" in stdout
        with open(output_file) as f:
            content = f.read()
        assert "graph TD" in content


class TestDryRunCommand:
    def test_dry_run_with_input(self):
        rc, stdout, stderr = run_cli(
            "dry-run",
            "tests.sample_flow_for_cli:hello_flow",
            "--input", '{"name": "Test"}',
        )
        assert rc == 0, f"stderr: {stderr}"
        report = json.loads(stdout)
        assert "flow_id" in report
        assert report["flow_id"] == "hello"

    def test_dry_run_without_input(self):
        rc, stdout, stderr = run_cli(
            "dry-run",
            "tests.sample_flow_for_cli:hello_flow",
        )
        assert rc == 0, f"stderr: {stderr}"
        report = json.loads(stdout)
        assert "valid" in report


class TestListCommand:
    def test_list_finds_flows(self):
        rc, stdout, stderr = run_cli("list", "tests.sample_flow_for_cli")
        assert rc == 0, f"stderr: {stderr}"
        assert "hello" in stdout
        assert "bye" in stdout

    def test_list_shows_header(self):
        rc, stdout, stderr = run_cli("list", "tests.sample_flow_for_cli")
        assert rc == 0, f"stderr: {stderr}"
        assert "Flow ID" in stdout
        assert "Variable" in stdout

    def test_list_bad_module(self):
        rc, stdout, stderr = run_cli("list", "nonexistent_module_xyz")
        assert rc != 0
        assert "Could not import" in stderr
