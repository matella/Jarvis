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


def _token(source: str) -> str | None:
    return get_provider().get(f"WEBHOOK_TOKEN_{source.upper()}")


def _bearer(value: str) -> str:
    """Strip an optional 'Bearer ' prefix — apps set the Authorization value either way."""
    return value[7:].strip() if value.lower().startswith("bearer ") else value.strip()


def verify(source: str, body: bytes, headers: dict[str, str]) -> None:
    """Authenticate an inbound webhook. Raises WebhookUnverified on any failure.

    Two schemes (a source uses whichever its sender supports):
      • Shared-secret TOKEN in a header — for apps that can't HMAC-sign (Radarr/Sonarr/Jellyseerr
        can set a custom header). Set WEBHOOK_TOKEN_<SOURCE>; sender sends X-Jarvis-Token or
        Authorization with that value.
      • HMAC-SHA256 — GitHub/Grafana style. Set WEBHOOK_SECRET_<SOURCE>.
    """
    s = get_settings()
    h = {k.lower(): v for k, v in headers.items()}
    token_secret = _token(source)
    hmac_secret = _secret(source)

    # Token scheme (constant-time). Takes precedence when configured for this source.
    if token_secret:
        provided = h.get("x-jarvis-token", "") or _bearer(h.get("authorization", ""))
        if provided and hmac.compare_digest(provided, token_secret):
            return
        raise WebhookUnverified(f"missing/invalid token for {source!r}")

    # HMAC scheme. GitHub: X-Hub-Signature-256: sha256=<hex>. Others: X-Jarvis-Signature: <hex>.
    if hmac_secret:
        provided = h.get("x-hub-signature-256", "")
        if provided.startswith("sha256="):
            provided = provided.split("=", 1)[1]
        else:
            provided = h.get("x-jarvis-signature", "")
        expected = hmac.new(hmac_secret.encode(), body, hashlib.sha256).hexdigest()
        if not provided or not hmac.compare_digest(provided, expected):
            raise WebhookUnverified(f"bad signature for {source!r}")
        return

    # No credential configured for this source.
    if s.webhook_require_signature:
        raise WebhookUnverified(f"no signing secret or token configured for {source!r}")


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


def _norm(verb: str) -> str:
    """Normalize an eventType/notification_type to a snake-ish suffix (Grab → grab, MEDIA_PENDING
    → media_pending, HealthIssue → health_issue)."""
    import re

    # Split camelCase only at a lower→upper boundary (so HealthIssue → health_issue) without
    # mangling ALL_CAPS inputs (MEDIA_PENDING stays media_pending).
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", verb.strip()).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "event"


def _arr_event(source: str, payload: dict[str, Any]) -> Event:
    """Radarr/Sonarr webhook → `<source>.<eventtype>` (e.g. radarr.grab, sonarr.download)."""
    etype = _norm(str(payload.get("eventType", "event")))
    media = payload.get("movie") or payload.get("series") or {}
    title = sanitize(str(media.get("title", payload.get("instanceName", source))))
    kind = "movie" if "movie" in payload else "series" if "series" in payload else source
    severity = Severity.warning if etype in ("health_issue", "manual_interaction_required") \
        else Severity.info
    return Event(
        type=f"{source}.{etype}", severity=severity, source=f"webhook:{source}",
        entity_ref=f"{kind}:{title}", occurred_at=utcnow(),
        payload={"title": title, "event": etype,
                 "quality": sanitize(str((payload.get("release") or {}).get("quality", ""))),
                 "message": sanitize(str(payload.get("message", "")))[:500]},
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def _jellyseerr_event(payload: dict[str, Any]) -> Event:
    """Jellyseerr webhook → `jellyseerr.<notification_type>` (e.g. jellyseerr.media_pending)."""
    ntype = _norm(str(payload.get("notification_type", "notification")))
    subject = sanitize(str(payload.get("subject", "request")))
    requested_by = sanitize(str((payload.get("request") or {}).get("requestedBy_username", "")))
    severity = Severity.warning if ntype in ("media_failed", "issue_created") else Severity.info
    return Event(
        type=f"jellyseerr.{ntype}", severity=severity, source="webhook:jellyseerr",
        entity_ref=f"media:{subject}", occurred_at=utcnow(),
        payload={"subject": subject, "event": ntype, "requested_by": requested_by,
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
    if source in ("radarr", "sonarr"):
        return _arr_event(source, payload)
    if source == "jellyseerr":
        return _jellyseerr_event(payload)
    return _generic_event(source, payload)
