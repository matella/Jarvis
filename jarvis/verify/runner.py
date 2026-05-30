"""Verification runner — find settled executions, check the effect, record the verdict.

Periodic + deterministic: pick successful executions old enough to have settled but still within the
window and not yet judged; for container-targeting intents, read current state + count fresh failure
events since the action, classify, persist a `verifications` row, and emit `verification.completed`.
Non-container actions are recorded `inconclusive` (nothing deterministic to check yet).
"""

from __future__ import annotations

import time
from datetime import timedelta

import psycopg

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.intents.repository import get_intent
from jarvis.verify.checks import VerifyStatus, classify_container_recovery, container_target

_BAD_TYPES = ("container.died", "container.oom_killed")


def _bad_events_since(conn: psycopg.Connection, entity: str, since) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM events WHERE entity_ref = %s AND occurred_at >= %s "
        "AND (type = ANY(%s) OR severity IN ('error','critical'))",
        (entity, since, list(_BAD_TYPES)),
    ).fetchone()
    return int(row["n"]) if row else 0


def _status_of(conn: psycopg.Connection, entity: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM state WHERE entity = %s", (entity,)
    ).fetchone()
    return row["status"] if row else None


def _pending_executions(conn: psycopg.Connection, *, settle_before, window_after) -> list[dict]:
    """Successful executions that have settled, are still in-window, and aren't verified yet."""
    return conn.execute(
        "SELECT e.exec_id, e.intent_id, e.correlation_id, e.created_at "
        "FROM executions e LEFT JOIN verifications v "
        "  ON v.subject_type = 'intent' AND v.subject_id = e.intent_id "
        "WHERE e.outcome = 'success' AND v.id IS NULL "
        "  AND e.created_at <= %s AND e.created_at >= %s "
        "ORDER BY e.created_at",
        (settle_before, window_after),
    ).fetchall()


def verify_execution(conn: psycopg.Connection, row: dict) -> VerifyStatus:
    """Judge one execution; persist a verification row + emit the event. Returns the verdict."""
    intent = get_intent(conn, row["intent_id"])
    entity = container_target(intent.target) if intent else None
    if entity is None:
        status, detail = VerifyStatus.inconclusive, "no container target to verify"
    else:
        cur = _status_of(conn, entity)
        bad = _bad_events_since(conn, entity, row["created_at"])
        status = classify_container_recovery(cur, bad)
        detail = f"{entity} status={cur or 'unknown'} bad_events_since={bad}"

    vid = ids.new_id(ids.VERIFICATION)
    conn.execute(
        "INSERT INTO verifications (id, subject_type, subject_id, check_kind, status, detail, "
        "correlation_id) VALUES (%s,'intent',%s,'container_recovery',%s,%s,%s) "
        "ON CONFLICT (subject_type, subject_id) DO NOTHING",
        (vid, row["intent_id"], status.value, detail, row["correlation_id"]),
    )
    emit_event(Event(
        type="verification.completed",
        severity=Severity.warning if status is VerifyStatus.unverified else Severity.info,
        source="verify", entity_ref=f"intent:{row['intent_id']}", occurred_at=utcnow(),
        payload={"intent_id": row["intent_id"], "status": status.value, "detail": detail},
        correlation_id=row["correlation_id"], causation_id=row["intent_id"],
    ))
    return status


def run_once() -> int:
    """Verify all settled-but-unjudged successful executions. Returns count verified."""
    s = get_settings()
    now = utcnow()
    settle_before = now - timedelta(seconds=s.verify_settle_s)
    window_after = now - timedelta(minutes=s.verify_window_min)
    count = 0
    with db.connect(autocommit=True) as conn:
        pending = _pending_executions(conn, settle_before=settle_before, window_after=window_after)
        for row in pending:
            verify_execution(conn, row)
            count += 1
    return count


def run_verifier(*, once: bool = False) -> None:
    interval = get_settings().verify_interval_s
    while True:
        n = run_once()
        if n:
            print(f"[verify] judged {n} execution(s)", flush=True)
        if once:
            return
        time.sleep(interval)
