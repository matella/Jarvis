"""qBittorrent connector — live download status (read-only) + completion events.

qBittorrent sits behind gluetun, so its "bypass auth on localhost" never applies (requests never
look like 127.0.0.1 to it). We log in to the WebUI API (`/api/v2/auth/login` → session cookie;
creds via SecretsProvider) and read `torrents/info` + `transfer/info`. `summarize()` is pure and
unit-tested. Torrent names are external-ish text → `sanitize()`d before they touch the spine.

Two surfaces: a live snapshot (CLI `jarvis torrents` + gateway `/api/torrents`) for "how active are
we / how long left", and a `torrent.completed` event per finished torrent for the timeline.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.parse
import urllib.request
from typing import Any

from jarvis import ids
from jarvis.config import get_settings
from jarvis.connectors.base import register_connector
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.security.sanitize import sanitize
from jarvis.security.secrets import get_provider

# qBittorrent reports this (100 days, in seconds) for "unknown / not downloading" ETA.
_ETA_INFINITY = 8640000
_DOWNLOADING = {"downloading", "forcedDL", "metaDL", "stalledDL", "checkingDL", "allocating"}
_SEEDING = {"uploading", "forcedUP", "stalledUP", "queuedUP", "checkingUP"}


def summarize(torrents: list[dict], transfer: dict) -> dict[str, Any]:
    """Pure: collapse qBittorrent's torrents/info + transfer/info into a status summary."""
    downloading = [t for t in torrents if t.get("state") in _DOWNLOADING]
    seeding = [t for t in torrents if t.get("state") in _SEEDING]
    queued = [t for t in torrents if t.get("state") == "queuedDL"]

    etas = [int(t.get("eta", 0)) for t in downloading if 0 < int(t.get("eta", 0)) < _ETA_INFINITY]
    items = sorted(downloading, key=lambda t: float(t.get("progress", 0)), reverse=True)
    return {
        "total": len(torrents),
        "downloading": len(downloading),
        "seeding": len(seeding),
        "queued": len(queued),
        "dl_speed": int(transfer.get("dl_info_speed", 0)),  # bytes/s
        "up_speed": int(transfer.get("up_info_speed", 0)),
        "eta_s": max(etas) if etas else None,  # longest finite ETA among active downloads
        "items": [
            {
                "name": sanitize(str(t.get("name", ""))),
                "state": str(t.get("state", "")),
                "progress": round(float(t.get("progress", 0)), 4),
                "eta_s": (int(t["eta"]) if 0 < int(t.get("eta", 0)) < _ETA_INFINITY else None),
                "dl_speed": int(t.get("dlspeed", 0)),
            }
            for t in items[:20]
        ],
    }


def _opener(base: str):
    """Log in and return a cookie-bearing opener (or raise on failure)."""
    provider = get_provider()
    user = provider.required("QBITTORRENT_USER")
    password = provider.required("QBITTORRENT_PASS")
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"username": user, "password": password}).encode()
    req = urllib.request.Request(  # noqa: S310 — operator-configured internal service
        base + "/api/v2/auth/login", data=data,
        headers={"Referer": base, "Content-Type": "application/x-www-form-urlencoded"},
    )
    opener.open(req, timeout=10).read()  # 200/204 + sets SID cookie; raises on bad creds/host
    return opener


def _get(opener, base: str, path: str) -> Any:
    req = urllib.request.Request(base + path, headers={"Referer": base})  # noqa: S310
    return json.loads(opener.open(req, timeout=10).read())


def fetch_snapshot() -> dict[str, Any]:
    """Live download status. Returns {available: False, ...} when unconfigured/unreachable."""
    s = get_settings()
    if not s.qbittorrent_url:
        return {"available": False, "reason": "qbittorrent_url not configured"}
    base = s.qbittorrent_url.rstrip("/")
    try:
        opener = _opener(base)
        snap = summarize(_get(opener, base, "/api/v2/torrents/info"),
                         _get(opener, base, "/api/v2/transfer/info"))
        snap["available"] = True
        return snap
    except Exception as exc:  # noqa: BLE001 — degrade to an "unavailable" snapshot, never raise
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"[:160]}


_done_hashes: set[str] = set()
_initialized = False


def poll_once() -> int:
    """Emit a `torrent.completed` event for torrents newly finished since last poll. Returns count.

    The first poll seeds the baseline (no flood of events for already-complete torrents)."""
    global _initialized
    s = get_settings()
    if not s.qbittorrent_url:
        return 0
    base = s.qbittorrent_url.rstrip("/")
    try:
        opener = _opener(base)
        torrents = _get(opener, base, "/api/v2/torrents/info")
    except Exception as exc:  # noqa: BLE001
        print(f"[qbittorrent] poll failed: {exc!r}", flush=True)
        return 0

    done_now = {str(t.get("hash")): t for t in torrents if float(t.get("progress", 0)) >= 1.0}
    if not _initialized:
        _done_hashes.update(done_now)
        _initialized = True
        return 0

    emitted = 0
    for h, t in done_now.items():
        if h in _done_hashes:
            continue
        _done_hashes.add(h)
        name = sanitize(str(t.get("name", "")))
        emit_event(Event(
            type="torrent.completed", severity=Severity.info, source="qbittorrent",
            entity_ref=f"torrent:{h[:12]}", occurred_at=utcnow(),
            payload={"name": name, "category": sanitize(str(t.get("category", "")))},
            correlation_id=ids.new_id(ids.CORRELATION),
        ))
        emitted += 1
    return emitted


class QbittorrentConnector:
    name = "qbittorrent"

    def ingest(self, *, once: bool = True) -> int:
        return poll_once()


register_connector(QbittorrentConnector())
