"""Notification channel — a generic webhook (or log-only if unconfigured).

POSTs a JSON payload to `NOTIFY_WEBHOOK_URL` (works with ntfy/Discord/Slack/Gotify relays).
Best-effort: delivery failures are logged, never raised — a down notifier must not break the
spine.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from jarvis.config import get_settings


def send(*, title: str, message: str, priority: str = "default", **fields: Any) -> bool:
    """Send a notification. Returns True if POSTed, False if log-only or on failure."""
    url = get_settings().notify_webhook_url
    payload = {"title": title, "message": message, "priority": priority, **fields}
    if not url:
        print(f"[notify:log] ({priority}) {title} — {message}", flush=True)
        return False
    try:
        req = urllib.request.Request(  # noqa: S310 — operator-configured URL
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            resp.read()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[notify:error] failed to POST {url}: {exc}", flush=True)
        return False
