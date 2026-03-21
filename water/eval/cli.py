# water/eval/cli.py
"""
CLI command handlers for ``water eval`` subcommands.

Provides:
- ``water eval run <config>``  -- run an eval suite from a config file
- ``water eval compare <baseline> <current>`` -- detect regressions
- ``water eval list [directory]`` -- discover eval config files
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from water.eval.config import EvalConfig, build_evaluators, build_cases


def cmd_eval_run(args):
    """Run an eval suite from a config file."""
    config_path = args.config
    flow_spec = getattr(args, "flow", None)
    output_path = getattr(args, "output", None)
    format_type = getattr(args, "format", "text")

    # Load config
    config = EvalConfig.from_file(config_path)
    if flow_spec:
        config.flow_spec = flow_spec

    # Import flow
    from water.utils.cli import _import_flow

    flow = _import_flow(config.flow_spec)

    # Build evaluators and cases
    evaluators = build_evaluators(config.evaluators)
    cases = build_cases(config.cases)

    if not evaluators:
        print("No evaluators configured.")
        sys.exit(1)
    if not cases:
        print("No test cases configured.")
        sys.exit(1)

    # Run
    from water.eval.suite import EvalSuite

    suite = EvalSuite(
        flow=flow, evaluators=evaluators, cases=cases, name=config.suite_name
    )
    report = asyncio.run(suite.run())

    # Output
    if format_type == "json":
        output = report.to_json(indent=2)
    else:
        output = report.summary()

    if output_path:
        Path(output_path).write_text(output)
        print(f"Report saved to {output_path}")
    else:
        print(output)

    # Exit code
    sys.exit(0 if report.failed_cases == 0 else 1)


def cmd_eval_compare(args):
    """Compare two eval reports for regressions."""
    baseline_path = args.baseline
    current_path = args.current

    with open(baseline_path) as f:
        baseline_data = json.load(f)
    with open(current_path) as f:
        current_data = json.load(f)

    # Reconstruct reports from dicts
    baseline = _report_from_dict(baseline_data)
    current_report = _report_from_dict(current_data)

    regressions = current_report.compare(baseline)

    if regressions:
        print(f"Found {len(regressions)} regressions:")
        for r in regressions:
            print(
                f"  Case {r['case_index']}: "
                f"{r['baseline_score']:.2f} -> {r['current_score']:.2f}"
            )
        sys.exit(2)
    else:
        print("No regressions detected.")
        sys.exit(0)


def _report_from_dict(data):
    """Reconstruct an EvalReport from a serialized dict."""
    from water.eval.report import EvalReport, CaseResult

    results = []
    for cr in data.get("case_results", []):
        results.append(
            CaseResult(
                case_index=cr.get("case_index", 0),
                input_data=cr.get("input_data", {}),
                expected=cr.get("expected", {}),
                actual=cr.get("actual", {}),
                scores=cr.get("scores", []),
                passed=cr.get("passed", False),
                avg_score=cr.get("avg_score", 0.0),
            )
        )
    return EvalReport(
        case_results=results,
        total_cases=data.get("total_cases", len(results)),
        passed_cases=data.get("passed_cases", 0),
        failed_cases=data.get("failed_cases", 0),
        avg_score=data.get("avg_score", 0.0),
    )


def cmd_eval_list(args):
    """List eval config files in a directory."""
    directory = getattr(args, "directory", ".")
    p = Path(directory)
    configs = (
        list(p.glob("**/*.yaml"))
        + list(p.glob("**/*.yml"))
        + list(p.glob("**/*.json"))
    )
    eval_configs = [c for c in configs if "eval" in c.stem.lower()]

    if eval_configs:
        print(f"Found {len(eval_configs)} eval configs:")
        for c in eval_configs:
            print(f"  {c}")
    else:
        print("No eval config files found.")
