import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


RENDER_API_BASE = "https://api.render.com/v1"


def _find_app_module():
    """Auto-detect the module containing a FlowServer .get_app() call."""
    cwd = Path.cwd()
    for py_file in cwd.glob("*.py"):
        try:
            content = py_file.read_text()
            if "FlowServer" in content and "get_app()" in content:
                return py_file.stem
        except Exception:
            continue
    return None


def _render_api_request(path, method="GET", data=None, api_key=None):
    """Make a request to the Render API."""
    url = f"{RENDER_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"Error: Render API returned {e.code}: {error_body}", file=sys.stderr)
        sys.exit(1)


def _get_repo_url():
    """Get the git remote origin URL."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        # Convert SSH URL to HTTPS if needed
        if url.startswith("git@github.com:"):
            url = url.replace("git@github.com:", "https://github.com/")
        if url.endswith(".git"):
            url = url[:-4]
        return url
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _generate_render_yaml(app_module, app_variable="app", start_command=None):
    """Generate a render.yaml blueprint file."""
    if start_command is None:
        start_command = f"uvicorn {app_module}:{app_variable} --host 0.0.0.0 --port $PORT"

    render_config = {
        "services": [
            {
                "type": "web",
                "name": "water-flow-server",
                "runtime": "python",
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": start_command,
                "envVars": [
                    {"key": "PYTHON_VERSION", "value": "3.11.6"},
                ],
            }
        ]
    }

    return render_config


def _ensure_requirements_txt():
    """Ensure requirements.txt exists with water-ai dependency."""
    req_path = Path.cwd() / "requirements.txt"
    if req_path.exists():
        content = req_path.read_text()
        if "water-ai" not in content:
            print("Warning: requirements.txt exists but doesn't include 'water-ai'.")
            print("  Add 'water-ai' to your requirements.txt for deployment.")
        return

    # Create a basic requirements.txt
    req_path.write_text("water-ai\n")
    print("Created requirements.txt with water-ai dependency.")


def cmd_flow_prod_render(args):
    """Handle 'water flow prod:render' command."""
    api_key = os.environ.get("RENDER_API_KEY")

    # Determine the app module
    app_module = args.app
    if not app_module:
        app_module = _find_app_module()
        if not app_module:
            print(
                "Error: Could not auto-detect your FlowServer app module.",
                file=sys.stderr,
            )
            print(
                "  Use --app <module_name> to specify it (e.g., --app playground).",
                file=sys.stderr,
            )
            sys.exit(1)

    app_variable = args.var or "app"
    print(f"Detected app: {app_module}:{app_variable}")

    # Ensure requirements.txt
    _ensure_requirements_txt()

    # Generate render.yaml
    start_command = args.start_command
    render_config = _generate_render_yaml(app_module, app_variable, start_command)

    render_yaml_path = Path.cwd() / "render.yaml"

    # Write render.yaml as YAML-like format (simple enough to avoid PyYAML dependency)
    _write_render_yaml(render_yaml_path, render_config)
    print(f"Generated {render_yaml_path}")

    if not api_key:
        print()
        print("No RENDER_API_KEY found. To deploy automatically:")
        print("  1. Get your API key from https://dashboard.render.com/settings#api-keys")
        print("  2. Set it: export RENDER_API_KEY=<your-key>")
        print("  3. Re-run: water flow prod:render")
        print()
        print("Or deploy manually:")
        print("  1. Push your code (with render.yaml) to GitHub")
        print("  2. Go to https://dashboard.render.com/select-repo?type=blueprint")
        print("  3. Connect your repo and deploy")
        return

    # Deploy via Render API
    repo_url = _get_repo_url()
    if not repo_url:
        print(
            "Error: Could not detect git remote URL. Ensure you're in a git repo with an origin remote.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Deploying from repo: {repo_url}")

    service_name = args.name or "water-flow-server"
    start_cmd = start_command or f"uvicorn {app_module}:{app_variable} --host 0.0.0.0 --port $PORT"

    service_payload = {
        "type": "web_service",
        "name": service_name,
        "repo": repo_url,
        "autoDeploy": "yes",
        "branch": args.branch or "main",
        "runtime": "python",
        "buildCommand": "pip install -r requirements.txt",
        "startCommand": start_cmd,
        "plan": args.plan or "free",
        "region": args.region or "oregon",
        "envVars": [
            {"key": "PYTHON_VERSION", "value": "3.11.6"},
        ],
    }

    print("Creating Render web service...")
    result = _render_api_request("/services", method="POST", data=service_payload, api_key=api_key)

    service = result.get("service", result)
    service_id = service.get("id", "unknown")
    service_url = service.get("serviceDetails", {}).get("url", "")

    print()
    print("Deployment initiated!")
    print(f"  Service ID: {service_id}")
    if service_url:
        print(f"  URL: {service_url}")
    print(f"  Dashboard: https://dashboard.render.com")
    print()
    print("Your Water flows will be available once the build completes.")


def _write_render_yaml(path, config):
    """Write render.yaml without requiring PyYAML."""
    lines = []
    lines.append("services:")
    for svc in config["services"]:
        lines.append(f"  - type: {svc['type']}")
        lines.append(f"    name: {svc['name']}")
        lines.append(f"    runtime: {svc['runtime']}")
        lines.append(f"    buildCommand: \"{svc['buildCommand']}\"")
        lines.append(f"    startCommand: \"{svc['startCommand']}\"")
        if svc.get("envVars"):
            lines.append("    envVars:")
            for env in svc["envVars"]:
                lines.append(f"      - key: {env['key']}")
                lines.append(f"        value: {env['value']}")

    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(
        prog="water",
        description="Water - Multi-agent orchestration framework CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # water flow
    flow_parser = subparsers.add_parser("flow", help="Flow management commands")
    flow_subparsers = flow_parser.add_subparsers(dest="flow_command", help="Flow subcommands")

    # water flow prod:render
    render_parser = flow_subparsers.add_parser(
        "prod:render",
        help="Deploy flows to Render",
    )
    render_parser.add_argument(
        "--app",
        help="Python module containing FlowServer app (e.g., 'playground')",
    )
    render_parser.add_argument(
        "--var",
        default="app",
        help="Variable name of the ASGI app (default: 'app')",
    )
    render_parser.add_argument(
        "--name",
        help="Render service name (default: 'water-flow-server')",
    )
    render_parser.add_argument(
        "--branch",
        default="main",
        help="Git branch to deploy (default: 'main')",
    )
    render_parser.add_argument(
        "--plan",
        default="free",
        help="Render plan type (default: 'free')",
    )
    render_parser.add_argument(
        "--region",
        default="oregon",
        help="Render region (default: 'oregon')",
    )
    render_parser.add_argument(
        "--start-command",
        help="Custom start command (overrides auto-detected)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "flow":
        if args.flow_command == "prod:render":
            cmd_flow_prod_render(args)
        else:
            flow_parser.print_help()
            sys.exit(0)


if __name__ == "__main__":
    main()
