"""Pi-hole connector — read-only DNS/ad-blocking stats from the Pi-hole v6 API.

v6 flow: POST /api/auth {password} → session id → GET /api/stats/summary with the sid header →
best-effort logout (sessions are a finite resource). Same egress-guarded path as every connector;
the password lives only in the box .env.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request


def _base() -> str:
    return get_settings().pihole_url.rstrip("/")


def _host() -> str:
    return _base().split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def _auth() -> str | None:
    """A session id, or None (no password configured / wrong password / unreachable)."""
    pw = get_settings().pihole_password
    if not pw or not allowed(_host()):
        return None
    try:
        body = json.dumps({"password": pw}).encode()
        resp = guarded_request(f"{_base()}/api/auth", data=body,
                               headers={"Content-Type": "application/json"}, timeout=6.0)
        return (json.loads(resp.read()).get("session") or {}).get("sid")
    except Exception:  # noqa: BLE001 — any failure → unauthenticated
        return None


def _logout(sid: str) -> None:
    try:  # DELETE via method override isn't worth a custom opener — v6 accepts GET logout too
        guarded_request(f"{_base()}/api/logout", headers={"sid": sid}, timeout=4.0)
    except Exception:  # noqa: BLE001 — best-effort; sessions also expire on their own
        pass


def reachable() -> bool:
    """True if Pi-hole answers AND the configured password authenticates."""
    sid = _auth()
    if sid:
        _logout(sid)
        return True
    return False


def summary() -> dict[str, Any]:
    """Today's DNS picture: total queries, blocked, block %, active clients, gravity size."""
    sid = _auth()
    if not sid:
        return {}
    try:
        resp = guarded_request(f"{_base()}/api/stats/summary", headers={"sid": sid}, timeout=6.0)
        d = json.loads(resp.read())
        q = d.get("queries") or {}
        return {
            "queries_today": q.get("total"),
            "blocked_today": q.get("blocked"),
            "percent_blocked": round(float(q.get("percent_blocked") or 0), 1),
            "active_clients": (d.get("clients") or {}).get("active"),
            "domains_on_blocklist": (d.get("gravity") or {}).get("domains_being_blocked"),
        }
    except Exception:  # noqa: BLE001 — presenter shows "temporarily unavailable"
        return {}
    finally:
        _logout(sid)
