"""Backlog #6 integration: defer reasoning, then drain it (graceful degradation)."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.core import degrade

pytestmark = pytest.mark.integration


def test_defer_drain_roundtrip(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pretend the LLM is up so drain runs
    monkeypatch.setattr(degrade, "reasoning_available", lambda: True)
    did = degrade.defer(db_conn, "test_kind", {"entity": "container:x"})
    try:
        rows = degrade.pending(db_conn)
        assert any(r["id"] == did for r in rows)

        handled: list[dict] = []
        n = degrade.drain(db_conn, {"test_kind": lambda payload: handled.append(payload)})
        assert n >= 1
        assert {"entity": "container:x"} in handled
        # resolved → no longer pending
        assert not any(r["id"] == did for r in degrade.pending(db_conn))
    finally:
        db_conn.execute("DELETE FROM deferrals WHERE id = %s", (did,))


def test_drain_skips_when_reasoning_down(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(degrade, "reasoning_available", lambda: False)
    did = degrade.defer(db_conn, "test_kind", {"entity": "container:y"})
    try:
        # LLM down → drain is a no-op, the deferral stays queued (don't lose work)
        assert degrade.drain(db_conn, {"test_kind": lambda p: None}) == 0
        assert any(r["id"] == did for r in degrade.pending(db_conn))
    finally:
        db_conn.execute("DELETE FROM deferrals WHERE id = %s", (did,))


def test_failing_handler_bumps_attempts_keeps_queued(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(degrade, "reasoning_available", lambda: True)
    did = degrade.defer(db_conn, "test_kind", {"entity": "container:z"})

    def _boom(_p: dict) -> None:
        raise RuntimeError("still down downstream")

    try:
        assert degrade.drain(db_conn, {"test_kind": _boom}) == 0  # nothing resolved
        row = next(r for r in degrade.pending(db_conn) if r["id"] == did)
        assert row["attempts"] == 1  # bumped, still queued for a later retry
    finally:
        db_conn.execute("DELETE FROM deferrals WHERE id = %s", (did,))
