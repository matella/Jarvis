"""Backlog #1 integration: outcome verification judges a real intent against live state."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from jarvis.events.models import utcnow
from jarvis.intents.models import Intent, IntentReasoning, Risk
from jarvis.intents.repository import insert_intent
from jarvis.verify.checks import VerifyStatus
from jarvis.verify.runner import verify_execution

pytestmark = pytest.mark.integration


def _seed_intent(conn: psycopg.Connection, corr: str, container: str) -> Intent:
    intent = Intent(
        type="docker.restart_container", target={"container": container},
        requested_by="verify-itest", correlation_id=corr,
        reasoning=IntentReasoning(
            summary="restart", confidence=0.8, risk=Risk.low, reversible=True
        ),
    )
    insert_intent(conn, intent)
    return intent


def test_verifies_recovered_container(db_conn: psycopg.Connection) -> None:
    corr = "corr_verify_ok"
    entity = "container:verify-itest-ok"
    intent = _seed_intent(db_conn, corr, "verify-itest-ok")
    db_conn.execute(
        "INSERT INTO state (entity, kind, status) VALUES (%s,'container','running') "
        "ON CONFLICT (entity, kind) DO UPDATE SET status = 'running'",
        (entity,),
    )
    row = {"intent_id": intent.intent_id, "correlation_id": corr,
           "created_at": utcnow() - timedelta(minutes=5)}
    try:
        assert verify_execution(db_conn, row) is VerifyStatus.verified
        v = db_conn.execute(
            "SELECT status FROM verifications WHERE subject_id = %s", (intent.intent_id,)
        ).fetchone()
        assert v["status"] == "verified"
    finally:
        db_conn.execute("DELETE FROM verifications WHERE subject_id = %s", (intent.intent_id,))
        db_conn.execute("DELETE FROM intents WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM state WHERE entity = %s", (entity,))


def test_unverified_when_container_still_down(db_conn: psycopg.Connection) -> None:
    corr = "corr_verify_bad"
    entity = "container:verify-itest-bad"
    intent = _seed_intent(db_conn, corr, "verify-itest-bad")
    db_conn.execute(
        "INSERT INTO state (entity, kind, status) VALUES (%s,'container','exited') "
        "ON CONFLICT (entity, kind) DO UPDATE SET status = 'exited'",
        (entity,),
    )
    row = {"intent_id": intent.intent_id, "correlation_id": corr,
           "created_at": utcnow() - timedelta(minutes=5)}
    try:
        assert verify_execution(db_conn, row) is VerifyStatus.unverified
    finally:
        db_conn.execute("DELETE FROM verifications WHERE subject_id = %s", (intent.intent_id,))
        db_conn.execute("DELETE FROM intents WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM state WHERE entity = %s", (entity,))
