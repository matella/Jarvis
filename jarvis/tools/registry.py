"""Capability registry + the M4 executor.

Maps an Intent `type` to a `Tool`. Only types present here (plus advisory types) are valid
agent proposals; everything else is rejected at the boundary. M4 ships one real capability:
`docker.restart_container`.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from jarvis.config import get_settings
from jarvis.tools.contract import Rollback, Tool

# Advisory intent types have no executor (recommend / investigate only).
ADVISORY_TYPES = ("infra.investigate", "infra.recommend")

_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(intent_type: str) -> Tool | None:
    return _REGISTRY.get(intent_type)


def capabilities() -> list[str]:
    return sorted(_REGISTRY)


def valid_intent_types() -> set[str]:
    return set(_REGISTRY) | set(ADVISORY_TYPES)


def _require_container(target: dict[str, Any]) -> str:
    name = target.get("container")
    if not isinstance(name, str) or not _CONTAINER_NAME.match(name):
        raise ValueError(f"invalid container target: {target!r}")
    return name


def _restart_inspect(target: dict[str, Any]) -> dict[str, Any]:
    name = _require_container(target)
    proc = subprocess.run(
        ["docker", "--context", get_settings().docker_context, "inspect",
         "--format", "{{.State.Status}}", name],
        capture_output=True, text=True, timeout=10,
    )
    return {"status": proc.stdout.strip() or "unknown"}


def _restart_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    name = _require_container(target)
    subprocess.run(
        ["docker", "--context", get_settings().docker_context, "restart", "-t", "10", name],
        capture_output=True, text=True, timeout=timeout_s, check=True,
    )
    return {"restarted": name}


register(
    Tool(
        name="docker.restart_container",
        version=1,
        permissions=["docker:restart"],
        side_effects=True,
        idempotent=False,
        max_retries=1,
        timeout_seconds=30,
        rollback=Rollback.none,
        run=_restart_run,
        inspect=_restart_inspect,
    )
)
