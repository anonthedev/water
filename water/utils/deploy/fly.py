"""Fly.io deployment support for Water flows."""

import sys
from pathlib import Path
from typing import Optional


def generate_fly_config(
    app_module: str,
    app_variable: str = "app",
    app_name: Optional[str] = None,
    start_command: Optional[str] = None,
    region: str = "iad",
) -> str:
    """
    Generate a fly.toml configuration file.

    Args:
        app_module: Python module containing the FlowServer app.
        app_variable: Variable name of the ASGI app.
        app_name: Fly.io app name.
        start_command: Custom start command (optional).
        region: Deployment region (default: iad).

    Returns:
        The fly.toml content as a string.
    """
    name = app_name or "water-flow-server"
    cmd = start_command or f"uvicorn {app_module}:{app_variable} --host 0.0.0.0 --port 8080"
    return f"""app = "{name}"
primary_region = "{region}"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

  [http_service.concurrency]
    type = "connections"
    hard_limit = 25
    soft_limit = 20

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/health"

[processes]
  app = "{cmd}"
"""


def cmd_flow_prod_fly(args) -> None:
    """Handle 'water flow prod:fly' command."""
    from water.utils.cli import _find_app_module, _ensure_requirements_txt

    app_module = args.app
    if not app_module:
        app_module = _find_app_module()
        if not app_module:
            print(
                "Error: Could not auto-detect your FlowServer app module.",
                file=sys.stderr,
            )
            print("  Use --app <module_name> to specify it.", file=sys.stderr)
            sys.exit(1)

    app_variable = args.var or "app"
    print(f"Detected app: {app_module}:{app_variable}")

    _ensure_requirements_txt()

    app_name = getattr(args, "name", None) or "water-flow-server"
    region = getattr(args, "region", None) or "iad"
    start_command = getattr(args, "start_command", None)
    config = generate_fly_config(app_module, app_variable, app_name, start_command, region)

    config_path = Path.cwd() / "fly.toml"
    config_path.write_text(config)
    print(f"Generated {config_path}")

    if getattr(args, "config_only", False):
        return

    print()
    print("To deploy to Fly.io:")
    print("  1. Install Fly CLI: curl -L https://fly.io/install.sh | sh")
    print("  2. Login: fly auth login")
    print(f"  3. Launch: fly launch --name {app_name}")
    print("  4. Deploy: fly deploy")
