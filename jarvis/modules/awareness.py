"""Light awareness events for user-document modules.

When a note/task/recipe/doc/local-calendar entry changes significantly, the module emits a small
`<entity>.<verb>` event so the causal timeline stays whole and Jarvis stays aware. This event is a
**notice, not the source of truth** (the module's table is the truth — foundation Evolution #1), so
emission is **best-effort**: a Redis hiccup must never fail the operator's CRUD write.
"""

from __future__ import annotations

import logging

from jarvis import ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

_log = logging.getLogger(__name__)


def emit_awareness(
    event_type: str,
    *,
    source: str,
    entity_ref: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    severity: Severity = Severity.info,
    **payload: object,
) -> Event:
    """Build + emit a module awareness event (best-effort); returns the Event either way.

    `event_type` is `entity.verb` past-tense (`note.created`, `task.completed`). `source` is the
    module name. Resist low-signal events (no `*.viewed`).
    """
    event = Event(
        type=event_type,
        severity=severity,
        source=source,
        entity_ref=entity_ref,
        occurred_at=utcnow(),
        payload=dict(payload),
        correlation_id=correlation_id or ids.new_id(ids.CORRELATION),
        causation_id=causation_id,
    )
    try:
        emit_event(event)
    except Exception:  # noqa: BLE001 — awareness is a notice, not the source of truth
        _log.debug("awareness event %s not published (transport down)", event_type, exc_info=True)
    return event
