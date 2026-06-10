"""Sonarr + Radarr connector — read-only queue (downloading now) + calendar (next 7 days).

One module for both: identical /api/v3 surface, only base URL + key differ. X-Api-Key header,
egress-guarded like every connector. Keys live in the box .env.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jarvis.config import get_settings
from jarvis.security.egress import allowed, guarded_request

App = Literal["sonarr", "radarr"]


def _conf(app: App) -> tuple[str, str]:
    s = get_settings()
    if app == "sonarr":
        return s.sonarr_url.rstrip("/"), s.sonarr_api_key
    return s.radarr_url.rstrip("/"), s.radarr_api_key


def _get(app: App, path: str, *, timeout: float = 8.0) -> Any:
    base, key = _conf(app)
    if not key:
        raise ValueError(f"{app} api key not configured")
    host = base.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    if not allowed(host):
        raise ValueError(f"egress to {host} not allowlisted")
    resp = guarded_request(f"{base}/api/v3{path}", headers={"X-Api-Key": key}, timeout=timeout)
    return json.loads(resp.read())


def reachable(app: App) -> bool:
    try:
        return bool(_get(app, "/system/status", timeout=5.0).get("version"))
    except Exception:  # noqa: BLE001 — any error → unreachable
        return False


def queue(app: App, limit: int = 10) -> list[dict[str, Any]]:
    """What's downloading right now (title, status, time left, % done)."""
    d = _get(app, f"/queue?pageSize={limit}&includeUnknownSeriesItems=true")
    out = []
    for r in (d.get("records") or [])[:limit]:
        size, left = float(r.get("size") or 0), float(r.get("sizeleft") or 0)
        out.append({
            "title": r.get("title") or "?",
            "status": r.get("status") or "?",
            "time_left": r.get("timeleft") or "—",
            "done_pct": round((1 - left / size) * 100, 1) if size else 0.0,
        })
    return out


def upcoming(app: App, days: int = 7, limit: int = 12) -> list[dict[str, Any]]:
    """The next `days` of releases — airing episodes (Sonarr) / movie releases (Radarr)."""
    start = datetime.now(UTC).date()
    end = start + timedelta(days=days)
    rows = _get(app, f"/calendar?start={start}&end={end}&includeSeries=true")
    out = []
    for r in rows[:limit]:
        if app == "sonarr":
            series = (r.get("series") or {}).get("title", "?")
            label = f"{series} S{r.get('seasonNumber', 0):02d}E{r.get('episodeNumber', 0):02d}"
            when = (r.get("airDateUtc") or r.get("airDate") or "")[:10]
        else:
            label = r.get("title", "?")
            when = (r.get("digitalRelease") or r.get("inCinemas") or "")[:10]
        out.append({"title": label, "date": when})
    return out
