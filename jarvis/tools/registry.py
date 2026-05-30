"""Capability registry + the M4 executor.

Maps an Intent `type` to a `Tool`. Only types present here (plus advisory types) are valid
agent proposals; everything else is rejected at the boundary. M4 ships one real capability:
`docker.restart_container`.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from typing import Any

import yaml

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


def _restart_preview(target: dict[str, Any]) -> dict[str, Any]:
    """What a restart would do — current status + the action — touching nothing."""
    name = _require_container(target)
    return {"action": "restart", "container": name, "current": _restart_inspect(target)}


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
        preview=_restart_preview,
    )
)


# --- code.edit_file: capability-scoped file rewrite over SSH --------------------------------

def _validate_path(target: dict[str, Any]) -> str:
    """Path must be an existing file INSIDE the configured repo root (no escape)."""
    path = target.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError(f"invalid edit path: {path!r}")
    norm = os.path.normpath(path)
    if ".." in norm.split("/"):
        raise ValueError(f"path escapes via '..': {path!r}")
    root = os.path.normpath(get_settings().code_repo_path)
    if norm != root and not norm.startswith(root.rstrip("/") + "/"):
        raise ValueError(f"path outside repo root {root!r}: {norm!r}")
    return norm


def _validate_content(path: str, content: str) -> None:
    if not content.strip():
        raise ValueError("refusing to write empty content")
    if path.endswith((".yml", ".yaml")):
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ValueError(f"new content is not valid YAML: {exc}") from exc


def _edit_inspect(target: dict[str, Any]) -> dict[str, Any]:
    path = _validate_path(target)
    settings = get_settings()
    proc = subprocess.run(
        ["ssh", settings.remote_ssh, f"head -c {settings.code_max_file_bytes} {shlex.quote(path)}"],
        capture_output=True, text=True, timeout=15,
    )
    return {"path": path, "current_content": proc.stdout}


def _edit_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    path = _validate_path(target)
    content = target.get("new_content", "")
    _validate_content(path, content)
    backup = f"{path}.jarvis.bak"
    # Back up the original (no-clobber so the first backup is preserved), then overwrite.
    cmd = f"cp -n {shlex.quote(path)} {shlex.quote(backup)} 2>/dev/null; cat > {shlex.quote(path)}"
    subprocess.run(
        ["ssh", get_settings().remote_ssh, cmd],
        input=content, capture_output=True, text=True, timeout=timeout_s, check=True,
    )
    return {"written": path, "backup": backup}


register(
    Tool(
        name="code.edit_file",
        version=1,
        permissions=["code:write"],
        side_effects=True,
        idempotent=True,
        max_retries=0,
        timeout_seconds=15,
        rollback=Rollback.manual,
        run=_edit_run,
        inspect=_edit_inspect,
    )
)
