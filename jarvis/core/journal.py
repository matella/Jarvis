"""Operational journal — a derived chronological timeline, not a stored table.

Merges the significant operational records (incidents, intents, executions, and warning+
operational events) into one time-sorted diary. The event log is already the source-of-truth
timeline; this just curates and renders it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg

from jarvis.events.models import utcnow

_ALERT_SEVERITIES = ("warning", "error", "critical")
# Operational sources only — exclude Jarvis's own cognition events so incident.correlated /
# execution.recorded don't double-count the incident / execution rows.
_META_SOURCES = ("correlator", "router", "orchestrator", "infrastructure_agent")


@dataclass
class JournalEntry:
    ts: datetime
    kind: str  # event | incident | intent | execution
    severity: str
    title: str
    ref: str


def build_journal(conn: psycopg.Connection, since: timedelta) -> list[JournalEntry]:
    since_dt = utcnow() - since
    entries: list[JournalEntry] = []

    for r in conn.execute(
        "SELECT id, type, severity, entity_ref, occurred_at FROM events "
        "WHERE severity = ANY(%s) AND source <> ALL(%s) AND occurred_at >= %s",
        (list(_ALERT_SEVERITIES), list(_META_SOURCES), since_dt),
    ).fetchall():
        title = f"{r['type']} {r['entity_ref'] or ''}".strip()
        entries.append(JournalEntry(r["occurred_at"], "event", r["severity"], title, r["id"]))

    for r in conn.execute(
        "SELECT incident_id, severity, summary, created_at FROM incidents WHERE created_at >= %s",
        (since_dt,),
    ).fetchall():
        entries.append(
            JournalEntry(r["created_at"], "incident", r["severity"], r["summary"], r["incident_id"])
        )

    for r in conn.execute(
        "SELECT intent_id, type, status, reasoning->>'risk' AS risk, "
        "reasoning->>'summary' AS summary, created_at FROM intents WHERE created_at >= %s",
        (since_dt,),
    ).fetchall():
        severity = "warning" if r["risk"] == "high" else "info"
        title = f"{r['type']} ({r['status']}): {r['summary']}"
        entries.append(JournalEntry(r["created_at"], "intent", severity, title, r["intent_id"]))

    for r in conn.execute(
        "SELECT exec_id, intent_id, outcome, failure_class, created_at FROM executions "
        "WHERE created_at >= %s",
        (since_dt,),
    ).fetchall():
        severity = "warning" if r["outcome"] == "failure" else "info"
        title = f"{r['outcome']} for {r['intent_id']}"
        if r["failure_class"]:
            title += f" ({r['failure_class']})"
        entries.append(JournalEntry(r["created_at"], "execution", severity, title, r["exec_id"]))

    entries.sort(key=lambda e: e.ts)
    return entries
