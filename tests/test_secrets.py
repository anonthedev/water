import pytest
import os
from pydantic import BaseModel
from water import create_task, Flow, SecretsManager, SecretValue, EnvSecretsManager


# --- Schemas ---

class SimpleInput(BaseModel):
    value: str


class SimpleOutput(BaseModel):
    result: str


# --- Tests ---

def test_secret_value_masked():
    """str() and repr() of a SecretValue return '***'."""
    secret = SecretValue("super-secret-key")
    assert str(secret) == "***"
    assert repr(secret) == "***"
    assert f"{secret}" == "***"


def test_secret_value_reveal():
    """reveal() returns the actual secret value."""
    secret = SecretValue("my-api-key-123")
    assert secret.reveal() == "my-api-key-123"


def test_secret_value_equality():
    """SecretValue equality compares actual values."""
    a = SecretValue("same")
    b = SecretValue("same")
    c = SecretValue("different")
    assert a == b
    assert a != c


def test_secrets_manager_set_get():
    """Basic set and get round-trip."""
    mgr = SecretsManager()
    mgr.set("api_key", "sk-12345")
    secret = mgr.get("api_key")
    assert isinstance(secret, SecretValue)
    assert secret.reveal() == "sk-12345"
    # str representation is masked
    assert str(secret) == "***"


def test_secrets_manager_has():
    """has() returns correct bool for present and absent keys."""
    mgr = SecretsManager()
    assert mgr.has("api_key") is False
    mgr.set("api_key", "value")
    assert mgr.has("api_key") is True


def test_secrets_manager_not_found():
    """get() raises KeyError for missing secrets."""
    mgr = SecretsManager()
    with pytest.raises(KeyError, match="Secret 'missing' not found"):
        mgr.get("missing")


def test_secrets_manager_reveal():
    """reveal() convenience method returns raw string."""
    mgr = SecretsManager()
    mgr.set("token", "abc-xyz")
    assert mgr.reveal("token") == "abc-xyz"


def test_secrets_manager_list_names():
    """list_names() returns registered names without values."""
    mgr = SecretsManager()
    mgr.set("key_a", "val_a")
    mgr.set("key_b", "val_b")
    names = mgr.list_names()
    assert sorted(names) == ["key_a", "key_b"]


@pytest.mark.asyncio
async def test_secrets_in_flow():
    """Task accesses secrets via context.get_service('secrets')."""
    secrets = SecretsManager()
    secrets.set("api_key", "sk-secret-flow-test")

    async def use_secret_fn(params, context):
        mgr = context.get_service("secrets")
        key = mgr.reveal("api_key")
        # Verify masking still works
        masked = str(mgr.get("api_key"))
        return {"result": f"key={key} masked={masked}"}

    task = create_task(
        id="use_secret",
        description="Uses a secret from the manager",
        input_schema=SimpleInput,
        output_schema=SimpleOutput,
        execute=use_secret_fn,
    )

    flow = Flow(id="secrets_flow")
    flow.secrets = secrets
    flow.then(task).register()

    result = await flow.run({"value": "test"})
    assert result["result"] == "key=sk-secret-flow-test masked=***"


def test_env_secrets_manager(monkeypatch):
    """EnvSecretsManager loads secrets from environment variables."""
    monkeypatch.setenv("MY_API_KEY", "env-key-value")
    monkeypatch.setenv("MY_DB_PASSWORD", "env-db-pass")

    mgr = EnvSecretsManager()
    mgr.load_from_env({
        "api_key": "MY_API_KEY",
        "db_password": "MY_DB_PASSWORD",
        "missing_secret": "NONEXISTENT_VAR",
    })

    assert mgr.has("api_key") is True
    assert mgr.reveal("api_key") == "env-key-value"
    assert mgr.has("db_password") is True
    assert mgr.reveal("db_password") == "env-db-pass"
    # Missing env var is silently skipped
    assert mgr.has("missing_secret") is False
