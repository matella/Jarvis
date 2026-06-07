"""HotS Overlay connector — read-only client to the self-hosted match-overlay server.

The streaming-overlay app (Node + MongoDB). Its match data is populated by the Rust replay uploader
running on the operator's gaming PC, so the server may be reachable but empty until a game is played
and uploaded. The presenter distinguishes those states. Egress-guarded like every connector.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request


def _base() -> str:
    return get_settings().hots_overlay_url.rstrip("/")


def _host() -> str:
    return _base().split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def _get(path: str, *, timeout: float = 6.0) -> Any:
    if not _base():
        raise ValueError("hots_overlay_url not configured")
    if not allowed(_host()):
        raise ValueError(f"egress to {_host()} not allowlisted")
    return json.loads(guarded_request(f"{_base()}{path}", timeout=timeout).read())


def reachable() -> bool:
    try:
        _get("/api/health", timeout=4.0)
        return True
    except Exception:  # noqa: BLE001 — any error → unreachable
        return False


def recent_matches(limit: int = 10) -> list[dict[str, Any]]:
    """Recent matches from the overlay. Tolerant to the response shape (list or wrapped)."""
    data = _get("/api/recent")
    if isinstance(data, dict):
        for key in ("games", "matches", "recent", "data", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    return data[:limit] if isinstance(data, list) else []
