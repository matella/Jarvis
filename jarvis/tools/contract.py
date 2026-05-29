"""The tool contract (frozen in CLAUDE.md / DECISIONS.md).

Every tool is capability-scoped: it declares a schema, runs in a permission scope, and
returns typed output. The LLM never touches a tool — only a validated Intent reaches the
registry, and only deterministic code runs `Tool.run`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Rollback(StrEnum):
    none = "none"
    manual = "manual"
    automatic = "automatic"


@dataclass(frozen=True)
class Tool:
    name: str  # matches an Intent type (e.g. "docker.restart_container")
    version: int
    permissions: list[str]
    side_effects: bool
    idempotent: bool
    max_retries: int
    timeout_seconds: int
    rollback: Rollback
    # Deterministic executors. `inspect` reads current state (for before/after); `run`
    # performs the action and returns result info. Both raise on failure.
    run: Callable[..., dict[str, Any]]
    inspect: Callable[[dict[str, Any]], dict[str, Any]] | None = field(default=None)
