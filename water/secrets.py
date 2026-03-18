"""
Secrets management for the Water framework.

Provides secure injection of API keys and credentials into task context
with automatic masking in string representations to prevent accidental
leakage in logs and debug output.
"""

import os
from typing import Dict, List


class SecretValue:
    """
    A wrapper around a secret string that masks the value in string representations.

    Use ``reveal()`` to access the actual secret value. All standard string
    conversions (``str()``, ``repr()``, ``print()``) return ``***`` to prevent
    accidental exposure in logs.
    """

    def __init__(self, value: str) -> None:
        """
        Initialize a SecretValue.

        Args:
            value: The actual secret string to protect.
        """
        self._value = value

    def __repr__(self) -> str:
        return "***"

    def __str__(self) -> str:
        return "***"

    def reveal(self) -> str:
        """Return the actual secret value."""
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretValue):
            return self._value == other._value
        return NotImplemented


class SecretsManager:
    """
    A registry for named secrets with masked access.

    Secrets are stored as :class:`SecretValue` instances so they are never
    accidentally printed or logged in cleartext.
    """

    def __init__(self) -> None:
        self._secrets: Dict[str, SecretValue] = {}

    def set(self, name: str, value: str) -> None:
        """
        Store a secret under the given name.

        Args:
            name: Identifier for the secret (e.g. ``"api_key"``).
            value: The raw secret string.
        """
        self._secrets[name] = SecretValue(value)

    def get(self, name: str) -> SecretValue:
        """
        Retrieve a :class:`SecretValue` by name.

        Args:
            name: The secret name.

        Returns:
            The corresponding :class:`SecretValue`.

        Raises:
            KeyError: If no secret is registered under *name*.
        """
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found")
        return self._secrets[name]

    def has(self, name: str) -> bool:
        """Return whether a secret with *name* is registered."""
        return name in self._secrets

    def reveal(self, name: str) -> str:
        """
        Convenience method to get the raw string value of a secret.

        Args:
            name: The secret name.

        Returns:
            The actual secret string.

        Raises:
            KeyError: If no secret is registered under *name*.
        """
        return self.get(name).reveal()

    def list_names(self) -> List[str]:
        """Return a list of registered secret names (values are never exposed)."""
        return list(self._secrets.keys())


class EnvSecretsManager(SecretsManager):
    """
    A :class:`SecretsManager` that can bulk-load secrets from environment variables.
    """

    def load_from_env(self, mapping: Dict[str, str]) -> None:
        """
        Load secrets from environment variables.

        Args:
            mapping: A dict of ``{secret_name: env_var_name}``. For each entry
                     the value of ``os.environ[env_var_name]`` is stored under
                     *secret_name*. Missing environment variables are silently
                     skipped.
        """
        for secret_name, env_var in mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                self.set(secret_name, value)
