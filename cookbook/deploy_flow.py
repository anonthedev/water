"""
Multi-Platform Deployment Flow Example: Generating Deployment Configs

This example demonstrates Water's deployment utilities for generating
platform-specific configuration files. It shows:
  - generate_dockerfile for Docker multi-stage builds
  - generate_docker_compose for Docker Compose with optional services
  - generate_railway_config for Railway.app deployment
  - generate_fly_config for Fly.io deployment

NOTE: This example only generates configuration strings; it does not
      write files or perform actual deployments.
"""

import asyncio

from water.utils.deploy import (
    generate_docker_config,
    generate_railway_config,
    generate_fly_config,
)
from water.utils.deploy.docker import generate_dockerfile, generate_docker_compose


# ---------------------------------------------------------------------------
# Example 1: Docker deployment (Dockerfile + docker-compose)
# ---------------------------------------------------------------------------

async def example_docker_deployment():
    """Generate Dockerfile and docker-compose.yml for a Water flow server."""
    print("=== Example 1: Docker Deployment ===\n")

    # Generate a basic Dockerfile
    dockerfile = generate_dockerfile(
        app_module="my_app.server",
        app_variable="app",
        python_version="3.11",
    )
    print("--- Dockerfile ---")
    print(dockerfile)

    # Generate docker-compose with Redis and Postgres
    compose = generate_docker_compose(
        app_module="my_app.server",
        app_variable="app",
        include_redis=True,
        include_postgres=True,
    )
    print("--- docker-compose.yml (with Redis + Postgres) ---")
    print(compose)

    # Generate both at once using the convenience function
    config = generate_docker_config(
        app_module="my_app.server",
        include_redis=False,
        include_postgres=False,
    )
    print(f"Config keys: {list(config.keys())}")
    print(f"Dockerfile length:  {len(config['dockerfile'])} chars")
    print(f"Compose length:     {len(config['compose'])} chars")
    print()


# ---------------------------------------------------------------------------
# Example 2: Railway deployment
# ---------------------------------------------------------------------------

async def example_railway_deployment():
    """Generate railway.toml for Railway.app deployment."""
    print("=== Example 2: Railway Deployment ===\n")

    config = generate_railway_config(
        app_module="my_app.server",
        app_variable="app",
    )
    print("--- railway.toml ---")
    print(config)

    # With custom start command
    custom_config = generate_railway_config(
        app_module="my_app.server",
        start_command="gunicorn my_app.server:app --bind 0.0.0.0:${PORT:-8000} --workers 4",
    )
    print("--- railway.toml (custom command) ---")
    print(custom_config)


# ---------------------------------------------------------------------------
# Example 3: Fly.io deployment
# ---------------------------------------------------------------------------

async def example_fly_deployment():
    """Generate fly.toml for Fly.io deployment."""
    print("=== Example 3: Fly.io Deployment ===\n")

    config = generate_fly_config(
        app_module="my_app.server",
        app_variable="app",
        app_name="my-water-flows",
        region="iad",
    )
    print("--- fly.toml ---")
    print(config)

    # Different region and custom name
    eu_config = generate_fly_config(
        app_module="my_app.server",
        app_name="water-eu-prod",
        region="lhr",
    )
    print("--- fly.toml (EU region) ---")
    # Just show first few lines to keep output concise
    lines = eu_config.strip().split("\n")
    for line in lines[:5]:
        print(f"  {line}")
    print(f"  ... ({len(lines)} total lines)")
    print()


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

async def main():
    await example_docker_deployment()
    await example_railway_deployment()
    await example_fly_deployment()
    print("All deployment config examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
