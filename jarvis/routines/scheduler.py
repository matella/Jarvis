"""Routine scheduler — fires due routines, change-aware, suspended under maintenance.

`is_due` is pure (schedule + now + last_run → bool) so scheduling is unit-testable without a clock.
Actions compose existing capabilities (summarize / briefing / search) and never touch infrastructure
directly — a routine produces a `routine.completed` event + a notification, nothing more.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import psycopg

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.routines.models import ActionKind, Routine, Schedule, ScheduleKind
from jarvis.routines.repository import list_routines, mark_run


def is_due(schedule: Schedule, now: datetime, last_run: datetime | None) -> bool:
    """Pure scheduling decision. `daily.at` is HH:MM in `now`'s timezone (UTC in production)."""
    if schedule.kind is ScheduleKind.interval:
        return last_run is None or (now - last_run).total_seconds() >= schedule.seconds
    # daily: due once we've passed today's target time and haven't run since it
    try:
        hh, mm = (int(x) for x in schedule.at.split(":", 1))
    except ValueError:
        return False
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < target:
        return False
    return last_run is None or last_run < target


def _briefing_text(conn: psycopg.Connection, hours: int) -> str:
    since = utcnow() - timedelta(hours=hours)
    incidents = conn.execute(
        "SELECT count(*) AS n FROM incidents WHERE created_at >= %s", (since,)
    ).fetchone()["n"]
    crit = conn.execute(
        "SELECT type, entity_ref FROM events WHERE occurred_at >= %s "
        "AND severity IN ('error','critical') ORDER BY id DESC LIMIT 5", (since,)
    ).fetchall()
    from jarvis.agents.summarizer import summarize

    summary = summarize(timedelta(hours=hours)).summary
    lines = [f"Briefing (last {hours}h): {incidents} incidents."]
    if crit:
        lines.append("Critical/error events:")
        lines += [f"  - {r['type']} {r['entity_ref'] or ''}".rstrip() for r in crit]
    lines.append("")
    lines.append(summary)
    return "\n".join(lines)


def run_action(conn: psycopg.Connection, routine: Routine) -> str:
    """Execute a routine's action by composing existing capabilities. Returns the result text."""
    action = routine.action
    if action.kind is ActionKind.summary:
        from jarvis.agents.summarizer import summarize

        return summarize(timedelta(hours=action.hours)).summary
    if action.kind is ActionKind.briefing:
        return _briefing_text(conn, action.hours)
    if action.kind is ActionKind.search:
        from jarvis.search.rag import answer_with_search

        return answer_with_search(action.query)[0]
    return "(no action)"


def run_routine(routine: Routine, *, notify: bool = True) -> str:
    """Run one routine now: execute its action, emit routine.completed, notify. Returns the text."""
    with db.connect(autocommit=True) as conn:
        text = run_action(conn, routine)
        mark_run(conn, routine.id, utcnow())
    emit_event(Event(
        type="routine.completed", severity=Severity.info, source="routines",
        entity_ref=f"routine:{routine.id}", occurred_at=utcnow(),
        payload={"name": routine.name, "action": routine.action.kind.value, "chars": len(text)},
        correlation_id=ids.new_id(ids.CORRELATION),
    ))
    if notify:
        try:
            from jarvis.notify.channel import send

            send(title=f"Routine: {routine.name}", message=text[:1500], priority="default")
        except Exception:  # noqa: BLE001 — delivery is best-effort
            pass
    return text


def run_routine_scheduler(*, once: bool = False) -> None:
    """Daemon worker: fire due, enabled routines. Suspended under maintenance (kill switch)."""
    from jarvis.core.modes import Mode, get_mode

    interval = get_settings().routine_tick_s
    while True:
        now = utcnow()
        with db.connect(autocommit=True) as conn:
            suspended = get_mode(conn) is Mode.maintenance
            routines = list_routines(conn, only_enabled=True) if not suspended else []
            due = [r for r in routines if is_due(r.schedule, now, r.last_run)]
        for routine in due:
            try:
                run_routine(routine)
                print(f"[routines] fired {routine.name}", flush=True)
            except Exception as exc:  # noqa: BLE001 — one bad routine must not stall the rest
                print(f"[routines] {routine.name} failed: {exc!r}", flush=True)
        if once:
            return
        time.sleep(interval)
