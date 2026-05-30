"""Notification channels — fan a notification out to every configured sink.

Two channels today: a self-hosted **ntfy** (local-first push to phone/desktop/watch) and a
generic **webhook** (Discord/Slack/Gotify relays). Web Push will slot in here as a third.
`send()` dispatches to all enabled channels; if none is configured it logs only. Best-effort
throughout — a channel that errors is logged and skipped, never raised: a down notifier must
not break the spine.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from jarvis.config import get_settings

# ntfy priority is an integer 1..5 (1=min … 5=max); map our string levels onto it.
_PRIORITY_TO_NTFY = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5, "max": 5}


def _ntfy_tags(priority: str, severity: str | None) -> list[str]:
    """Severity/priority → an ntfy emoji tag (ntfy renders known tags as emoji)."""
    if severity == "critical" or priority in ("urgent", "max"):
        return ["rotating_light"]
    if severity == "error":
        return ["x"]
    if severity == "warning" or priority == "high":
        return ["warning"]
    return ["robot"]


def ntfy_payload(
    *, topic: str, title: str, message: str, priority: str = "default", severity: str | None = None
) -> dict[str, Any]:
    """Pure: build the JSON body for ntfy's publish-as-JSON API (POST to the base URL)."""
    return {
        "topic": topic,
        "title": title,
        "message": message or " ",  # ntfy rejects an empty message body
        "priority": _PRIORITY_TO_NTFY.get(priority, 3),
        "tags": _ntfy_tags(priority, severity),
    }


def _post_json(url: str, payload: dict[str, Any], *, label: str) -> bool:
    """Best-effort JSON POST to an operator-configured sink. Returns True on a 2xx."""
    try:
        req = urllib.request.Request(  # noqa: S310 — operator-configured URL, not untrusted input
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            resp.read()
        return True
    except Exception as exc:  # noqa: BLE001 — delivery is best-effort; log and move on
        print(f"[notify:error] {label} POST {url} failed: {exc}", flush=True)
        return False


def send(*, title: str, message: str, priority: str = "default", **fields: Any) -> bool:
    """Fan a notification out to every configured channel. True if any channel delivered."""
    s = get_settings()
    severity = fields.get("severity")
    delivered = False
    configured = False

    if s.ntfy_url and s.ntfy_topic:
        configured = True
        payload = ntfy_payload(
            topic=s.ntfy_topic, title=title, message=message, priority=priority, severity=severity
        )
        delivered |= _post_json(s.ntfy_url, payload, label="ntfy")

    if s.notify_webhook_url:
        configured = True
        payload = {"title": title, "message": message, "priority": priority, **fields}
        delivered |= _post_json(s.notify_webhook_url, payload, label="webhook")

    if not configured:
        print(f"[notify:log] ({priority}) {title} — {message}", flush=True)
    return delivered
