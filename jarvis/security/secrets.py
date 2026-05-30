"""Secrets access — fetched by deterministic code only, never logged, never placed in a prompt.

A thin `SecretsProvider` interface with an env-backed implementation now (the existing `.env`/env
pattern), pluggable to a real vault later. Connectors (Phase 8) and search (Phase 9) read
credentials through this — keeping the access path in one auditable place. `repr` is deliberately
opaque so a provider never leaks values into logs or tracebacks.
"""

from __future__ import annotations

import os
from typing import Protocol


class SecretMissing(Exception):
    """A required secret was not configured."""


class SecretsProvider(Protocol):
    def get(self, name: str, default: str | None = None) -> str | None: ...
    def required(self, name: str) -> str: ...


class EnvSecretsProvider:
    """Reads secrets from the process environment (populated from `.env`). Never logs values."""

    def get(self, name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, default)

    def required(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise SecretMissing(f"required secret {name!r} is not set")
        return value

    def __repr__(self) -> str:  # never expose values
        return "EnvSecretsProvider()"


_provider: SecretsProvider = EnvSecretsProvider()


def get_provider() -> SecretsProvider:
    """The process-wide secrets provider (swap for a vault-backed one later)."""
    return _provider
