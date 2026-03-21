"""Tests for multi-platform deployment tooling."""

import pytest

from water.utils.deploy.railway import generate_railway_config
from water.utils.deploy.fly import generate_fly_config
from water.utils.deploy.docker import (
    generate_dockerfile,
    generate_docker_compose,
    generate_docker_config,
)


# --- Railway tests ---

def test_railway_config_default():
    config = generate_railway_config("myapp")
    assert "uvicorn myapp:app" in config
    assert "[build]" in config
    assert "[deploy]" in config
    assert "healthcheckPath" in config


def test_railway_config_custom():
    config = generate_railway_config("myapp", "server", start_command="gunicorn myapp:server")
    assert "gunicorn myapp:server" in config


# --- Fly.io tests ---

def test_fly_config_default():
    config = generate_fly_config("myapp")
    assert 'app = "water-flow-server"' in config
    assert "uvicorn myapp:app" in config
    assert "/health" in config
    assert "internal_port = 8080" in config


def test_fly_config_custom():
    config = generate_fly_config("myapp", app_name="my-agent", region="lax")
    assert 'app = "my-agent"' in config
    assert 'primary_region = "lax"' in config


# --- Docker tests ---

def test_dockerfile_default():
    df = generate_dockerfile("myapp")
    assert "FROM python:3.11-slim" in df
    assert "uvicorn" in df
    assert "EXPOSE 8000" in df
    assert "HEALTHCHECK" in df


def test_dockerfile_custom_python():
    df = generate_dockerfile("myapp", python_version="3.12")
    assert "FROM python:3.12-slim" in df


def test_docker_compose_basic():
    dc = generate_docker_compose("myapp")
    assert "services:" in dc
    assert "build: ." in dc
    assert '"8000:8000"' in dc


def test_docker_compose_with_redis():
    dc = generate_docker_compose("myapp", include_redis=True)
    assert "redis:" in dc
    assert "redis:7-alpine" in dc
    assert "REDIS_URL" in dc


def test_docker_compose_with_postgres():
    dc = generate_docker_compose("myapp", include_postgres=True)
    assert "postgres:" in dc
    assert "postgres:16-alpine" in dc
    assert "DATABASE_URL" in dc
    assert "volumes:" in dc


def test_docker_compose_full():
    dc = generate_docker_compose("myapp", include_redis=True, include_postgres=True)
    assert "redis:" in dc
    assert "postgres:" in dc
    assert "depends_on:" in dc


def test_generate_docker_config():
    configs = generate_docker_config("myapp", include_redis=True)
    assert "dockerfile" in configs
    assert "compose" in configs
    assert "FROM python" in configs["dockerfile"]
    assert "redis:" in configs["compose"]
