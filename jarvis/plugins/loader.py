"""Manifest-driven plugin tools — declare a capability as a templated, egress-guarded HTTP call.

The manifest names an Intent type, its permissions/side-effects, and an HTTP request whose URL/body
may reference `{arg}` placeholders drawn ONLY from a declared `args` allowlist. Rendering validates
every arg (no unknown keys, scalar values only) before substitution, and the call goes through the
egress allowlist — so a plugin can't smuggle arbitrary shell or reach a non-allowlisted host. The
built Tool registers exactly like a built-in and is gated/audited identically.
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any

import yaml
from pydantic import BaseModel, Field

from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_INTENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class PluginManifest(BaseModel):
    name: str  # the Intent type, e.g. "ha.scene"
    version: int = 1
    permissions: list[str] = Field(default_factory=list)
    side_effects: bool = True
    idempotent: bool = False
    timeout_seconds: int = 15
    method: str = "POST"
    url: str  # may contain {arg} placeholders
    body: dict[str, Any] = Field(default_factory=dict)  # values may be "{arg}" placeholders
    args: list[str] = Field(default_factory=list)  # the ONLY allowed placeholder names
    headers: dict[str, str] = Field(default_factory=dict)


class PluginError(Exception):
    pass


def validate_manifest(m: PluginManifest) -> None:
    if not _INTENT_TYPE.match(m.name):
        raise PluginError(f"plugin name must be 'entity.verb', got {m.name!r}")
    referenced = set(_PLACEHOLDER.findall(m.url))
    for v in m.body.values():
        if isinstance(v, str):
            referenced |= set(_PLACEHOLDER.findall(v))
    unknown = referenced - set(m.args)
    if unknown:
        raise PluginError(f"{m.name}: template references undeclared args {sorted(unknown)}")
    if m.method.upper() not in ("GET", "POST", "PUT"):
        raise PluginError(f"{m.name}: unsupported method {m.method!r}")


def render(template: str, target: dict[str, Any], allowed: list[str]) -> str:
    """Substitute {arg} from target, restricted to `allowed` args + scalar values. Pure."""
    def _sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in allowed:
            raise PluginError(f"arg {key!r} not allowed")
        if key not in target:
            raise PluginError(f"missing arg {key!r}")
        val = target[key]
        if not isinstance(val, (str, int, float, bool)):
            raise PluginError(f"arg {key!r} must be scalar")
        return str(val)

    return _PLACEHOLDER.sub(_sub, template)


def _render_body(body: dict[str, Any], target: dict[str, Any], allowed: list[str]) -> dict:
    out: dict[str, Any] = {}
    for k, v in body.items():
        out[k] = render(v, target, allowed) if isinstance(v, str) else v
    return out


def build_tool(m: PluginManifest) -> Tool:
    validate_manifest(m)

    def _run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
        from jarvis.security.egress import guarded_request

        url = render(m.url, target, m.args)
        data = None
        if m.method.upper() != "GET" and m.body:
            data = json.dumps(_render_body(m.body, target, m.args)).encode()
        headers = {"Content-Type": "application/json", **m.headers}
        guarded_request(url, data=data, headers=headers, timeout=timeout_s).read()
        return {"plugin": m.name, "url": url}

    def _preview(target: dict[str, Any]) -> dict[str, Any]:
        return {"plugin": m.name, "would_call": f"{m.method} {render(m.url, target, m.args)}"}

    return Tool(
        name=m.name, version=m.version, permissions=m.permissions,
        side_effects=m.side_effects, idempotent=m.idempotent, max_retries=0,
        timeout_seconds=m.timeout_seconds, rollback=Rollback.none,
        run=_run, preview=_preview,
    )


def load_manifest(path: str) -> PluginManifest:
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    return PluginManifest(**data)


def load_plugins(plugins_dir: str | None = None) -> list[str]:
    """Load + register all *.yaml plugins from the dir. Returns the registered capability names."""
    from jarvis.config import get_settings

    plugins_dir = plugins_dir if plugins_dir is not None else get_settings().plugins_dir
    if not plugins_dir or not os.path.isdir(plugins_dir):
        return []
    loaded: list[str] = []
    for path in sorted(glob.glob(os.path.join(plugins_dir, "*.yaml"))):
        try:
            manifest = load_manifest(path)
            register(build_tool(manifest))
            loaded.append(manifest.name)
        except Exception as exc:  # noqa: BLE001 — a bad plugin manifest must not break startup
            print(f"[plugins] skipped {path}: {exc!r}", flush=True)
    return loaded
