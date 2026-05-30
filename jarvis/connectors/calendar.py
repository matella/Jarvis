"""Calendar connector — ICS (CalDAV / Google secret-address) → `calendar.event` events.

Read-only, feeds-shaped: fetch each configured ICS URL through the egress guard, parse VEVENTs
with a small pure parser, and emit upcoming events within the horizon, deduped by a stable
`calendar:<uid>` entity_ref so a re-poll doesn't replay. Every field is sanitized — calendar text
is external content, inert data on the spine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.connectors.base import register_connector
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.security.egress import guarded_request
from jarvis.security.sanitize import sanitize


@dataclass(frozen=True)
class CalEvent:
    uid: str
    summary: str
    start: datetime


def _unfold(text: str) -> list[str]:
    """ICS line-unfolding: a leading space/tab continues the previous line (RFC 5545)."""
    out: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _parse_dt(value: str) -> datetime | None:
    """Parse common ICS DTSTART forms: 20260530T180000Z, 20260530T180000, or a date 20260530."""
    v = value.strip()
    try:
        if v.endswith("Z"):
            return datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if "T" in v:
            return datetime.strptime(v, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        return datetime.strptime(v, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_ics(text: str) -> list[CalEvent]:
    """Parse VEVENTs into normalized, sanitized events. Pure — no I/O."""
    events: list[CalEvent] = []
    uid = summary = ""
    start: datetime | None = None
    in_event = False
    for line in _unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            in_event, uid, summary, start = True, "", "", None
        elif line.startswith("END:VEVENT"):
            if in_event and start is not None:
                events.append(CalEvent(uid=uid or summary, summary=sanitize(summary), start=start))
            in_event = False
        elif not in_event:
            continue
        elif line.startswith("UID:"):
            uid = line[4:].strip()
        elif line.startswith("SUMMARY:"):
            summary = line[8:].strip()
        elif line.startswith("DTSTART"):
            start = _parse_dt(line.split(":", 1)[-1])
    return events


def _already_seen(conn, entity_ref: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM events WHERE entity_ref = %s LIMIT 1", (entity_ref,)
    ).fetchone() is not None


def poll_once() -> int:
    """Fetch each calendar, emit new upcoming events within the horizon. Returns count emitted."""
    s = get_settings()
    now = utcnow()
    horizon = now + timedelta(hours=s.calendar_horizon_h)
    emitted = 0
    with db.connect() as conn:
        for url in s.calendar_ics_urls:
            try:
                body = guarded_request(url, timeout=15).read().decode("utf-8", "replace")
            except Exception as exc:  # noqa: BLE001 — egress-blocked or fetch error; skip this cal
                print(f"[calendar] {url} failed: {exc!r}", flush=True)
                continue
            for ev in parse_ics(body):
                if not (now <= ev.start <= horizon):
                    continue  # only upcoming-within-horizon
                entity_ref = f"calendar:{ev.uid}"
                if _already_seen(conn, entity_ref):
                    continue
                emit_event(Event(
                    type="calendar.event", severity=Severity.info, source="calendar",
                    entity_ref=entity_ref, occurred_at=utcnow(),
                    payload={"summary": ev.summary, "start": ev.start.isoformat()},
                    correlation_id=ids.new_id(ids.CORRELATION),
                ))
                emitted += 1
    return emitted


class CalendarConnector:
    name = "calendar"

    def ingest(self, *, once: bool = True) -> int:
        return poll_once()


register_connector(CalendarConnector())
