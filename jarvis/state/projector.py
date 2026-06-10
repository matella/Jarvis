"""Event → state projector.

The ONLY writer of the `state` table. `project()` is a pure dispatch on `event.type`:
live in the consumer, and (later) re-runnable over the event log to rebuild state. M2
handles the container family only; adding a family is a new branch here, nothing else.

Projection is **monotonic**: because ids are ULID (time-sortable), an upsert only advances a
row when the incoming `last_event_id` is newer, so at-least-once redelivery or out-of-order
arrival can never regress state.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.events.models import Event

CONTAINER_KIND = "container"

# event.type -> container status. None means "this event carries no status change"
# (e.g. health transitions), so the projector leaves the existing status intact.
_CONTAINER_STATUS: dict[str, str | None] = {
    "container.started": "running",
    "container.restarted": "running",
    "container.unpaused": "running",
    "container.died": "exited",
    "container.stopped": "exited",
    "container.killed": "exited",
    "container.oom_killed": "oom_killed",
    "container.paused": "paused",
    "container.created": "created",
    "container.destroyed": "destroyed",
    "container.health_changed": None,
}


# Metric signal events update health attrs (cpu_status / mem_status) without touching the
# lifecycle status — so `state show` reflects resource health, not just up/down.
_SIGNAL_ATTRS: dict[str, tuple[str, str]] = {
    "container.cpu_high": ("cpu_status", "high"),
    "container.cpu_normal": ("cpu_status", "normal"),
    "container.memory_high": ("mem_status", "high"),
    "container.memory_normal": ("mem_status", "normal"),
}


def status_for_type(event_type: str) -> str | None:
    """Container status implied by an event type (None = no status change)."""
    return _CONTAINER_STATUS.get(event_type)


def signal_attr_for_type(event_type: str) -> tuple[str, str] | None:
    """Health (attrs key, value) implied by a metric signal event, if any."""
    return _SIGNAL_ATTRS.get(event_type)


def project(conn: psycopg.Connection, event: Event) -> bool:
    """Apply an event to the state projection. Returns True if it was projected."""
    if event.entity_ref is None or not event.type.startswith("container."):
        return False

    # Reconciliation events (ingest/reconcile.py) heal drift from missed docker events:
    # vanished/destroyed entities are REMOVED (state is a snapshot of the present, not history —
    # the event log keeps the past), observed entities snap to their real status.
    if event.type in ("container.vanished", "container.destroyed"):
        conn.execute(
            "DELETE FROM state WHERE entity = %s AND kind = %s",
            (event.entity_ref, CONTAINER_KIND),
        )
        return True

    attrs: dict[str, object] = {
        "last_action": event.type,
        "last_severity": event.severity.value,
    }
    if event.type == "container.observed":
        status = str(event.payload.get("status") or "unknown")
    elif event.type in _CONTAINER_STATUS:
        status = _CONTAINER_STATUS[event.type]
        for key in ("image", "exit_code", "health"):
            if event.payload.get(key) is not None:
                attrs[key] = event.payload[key]
    elif event.type in _SIGNAL_ATTRS:
        status = None  # health signal — don't change lifecycle status
        key, value = _SIGNAL_ATTRS[event.type]
        attrs[key] = value
    else:
        return False

    # Upsert, but only advance when the incoming event is newer (ULID-sortable id).
    conn.execute(
        """
        INSERT INTO state (entity, kind, status, attrs, updated_at, last_event_id)
        VALUES (%s, %s, %s, %s, now(), %s)
        ON CONFLICT (entity, kind) DO UPDATE SET
            status        = COALESCE(EXCLUDED.status, state.status),
            attrs         = state.attrs || EXCLUDED.attrs,
            updated_at    = now(),
            last_event_id = EXCLUDED.last_event_id
        WHERE state.last_event_id IS NULL
           OR state.last_event_id < EXCLUDED.last_event_id
        """,
        (event.entity_ref, CONTAINER_KIND, status, Json(attrs), event.id),
    )
    return True
