"""Inbound webhooks — the *push* complement to connector *pull*.

A signed POST to `/inbound/<source>` is HMAC-verified (per-source secret via SecretsProvider), then
mapped to a normalized, sanitized event on the spine. Unverified payloads are rejected outright;
verified ones are still just *data* — a webhook can raise a signal, never run an action (that path
is Intent→gate only). GitHub and Grafana are mapped specifically; anything else lands generic.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.security.sanitize import sanitize
from jarvis.security.secrets import get_provider


class WebhookUnverified(Exception):
    """Signature missing or invalid for the source."""


def _secret(source: str) -> str | None:
    return get_provider().get(f"WEBHOOK_SECRET_{source.upper()}")


def verify(source: str, body: bytes, headers: dict[str, str]) -> None:
    """Constant-time HMAC-SHA256 check. Raises WebhookUnverified on any failure."""
    s = get_settings()
    secret = _secret(source)
    if not secret:
        if s.webhook_require_signature:
            raise WebhookUnverified(f"no signing secret configured for {source!r}")
        return
    # GitHub: X-Hub-Signature-256: sha256=<hex>. Others: X-Jarvis-Signature: <hex>.
    h = {k.lower(): v for k, v in headers.items()}
    provided = h.get("x-hub-signature-256", "")
    if provided.startswith("sha256="):
        provided = provided.split("=", 1)[1]
    else:
        provided = h.get("x-jarvis-signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not provided or not hmac.compare_digest(provided, expected):
        raise WebhookUnverified(f"bad signature for {source!r}")


def _github_event(payload: dict[str, Any]) -> Event:
    repo = sanitize(str(payload.get("repository", {}).get("full_name", "unknown")))
    is_push = "commits" in payload or "head_commit" in payload
    return Event(
        type="github.push" if is_push else "github.event",
        severity=Severity.info, source="webhook:github", entity_ref=f"repo:{repo}",
        occurred_at=utcnow(),
        payload={"repo": repo, "ref": sanitize(str(payload.get("ref", ""))),
                 "sender": sanitize(str(payload.get("sender", {}).get("login", "")))},
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def _grafana_event(payload: dict[str, Any]) -> Event:
    state = str(payload.get("state", payload.get("status", "")))
    name = sanitize(str(payload.get("ruleName", payload.get("title", "alert"))))
    severity = Severity.critical if state in ("alerting", "firing") else Severity.info
    return Event(
        type="grafana.alert", severity=severity, source="webhook:grafana",
        entity_ref=f"alert:{name}", occurred_at=utcnow(),
        payload={"rule": name, "state": sanitize(state),
                 "message": sanitize(str(payload.get("message", "")))[:500]},
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def _generic_event(source: str, payload: dict[str, Any]) -> Event:
    return Event(
        type="webhook.received", severity=Severity.info, source=f"webhook:{sanitize(source)}",
        entity_ref=f"webhook:{sanitize(source)}", occurred_at=utcnow(),
        payload={"source": sanitize(source), "keys": sorted(payload)[:20]},
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def to_event(source: str, payload: dict[str, Any]) -> Event:
    if source == "github":
        return _github_event(payload)
    if source == "grafana":
        return _grafana_event(payload)
    return _generic_event(source, payload)
