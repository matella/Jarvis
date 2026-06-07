"""HotS Patch Notes connector — read-only client to the self-hosted HotsPatchNotes API.

One of the operator's homelab apps (C#/.NET, api on :5001). Jarvis presents its data on demand —
latest patches, the hero roster — via the same egress-guarded path every connector uses (host must
be allowlisted). All calls are best-effort: any failure surfaces as "not reachable", never a crash.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request


def _base() -> str:
    return get_settings().hots_api_url.rstrip("/")


def _host() -> str:
    return _base().split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def _get(path: str, *, timeout: float = 8.0) -> Any:
    if not _base():
        raise ValueError("hots_api_url not configured")
    if not allowed(_host()):
        raise ValueError(f"egress to {_host()} not allowlisted")
    return json.loads(guarded_request(f"{_base()}{path}", timeout=timeout).read())


def reachable() -> bool:
    """True if the HotS API answers — a live check for the presenter's accurate failure message."""
    try:
        _get("/api/heroes/roles", timeout=4.0)
        return True
    except Exception:  # noqa: BLE001 — any error → treat as unreachable
        return False


def latest_patches(limit: int = 10) -> list[dict[str, Any]]:
    items = _get("/api/patches").get("items", [])
    return [
        {
            "patch": p.get("patchName"),
            "type": p.get("patchType"),
            "version": p.get("gameVersion"),
            "date": (p.get("liveDate") or "")[:10],
            "link": p.get("officialLink") or p.get("alternateLink") or "",
        }
        for p in items[:limit]
    ]


def heroes() -> list[dict[str, Any]]:
    return [
        {"name": h.get("name"), "role": h.get("role"), "type": h.get("type"),
         "universe": h.get("universe")}
        for h in _get("/api/heroes")
    ]
