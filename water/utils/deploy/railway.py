"""Railway deployment support for Water flows."""

import json
import sys
from pathlib import Path
from typing import Optional


def generate_railway_config(
    app_module: str,
    app_variable: str = "app",
    start_command: Optional[str] = None,
) -> str:
    """
    Generate a railway.toml configuration file.

    Args:
        app_module: Python module containing the FlowServer app.
        app_variable: Variable name of the ASGI app.
        start_command: Custom start command (optional).

    Returns:
        The railway.toml content as a string.
    """
    cmd = start_command or f"uvicorn {app_module}:{app_variable} --host 0.0.0.0 --port ${{PORT:-8000}}"
    return f"""[build]
builder = "nixpacks"

[deploy]
startCommand = "{cmd}"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
"""


def cmd_flow_prod_railway(args) -> None:
    """Handle 'water flow prod:railway' command."""
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

    start_command = getattr(args, "start_command", None)
    config = generate_railway_config(app_module, app_variable, start_command)

    config_path = Path.cwd() / "railway.toml"
    config_path.write_text(config)
    print(f"Generated {config_path}")

    if getattr(args, "config_only", False):
        return

    print()
    print("To deploy to Railway:")
    print("  1. Install Railway CLI: npm install -g @railway/cli")
    print("  2. Login: railway login")
    print("  3. Deploy: railway up")
    print()
    print("Or connect your GitHub repo at https://railway.app")
