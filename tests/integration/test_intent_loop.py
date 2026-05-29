"""M4 integration: agent proposes a validated intent; the gate blocks then dry-runs.

Needs DB (+ Ollama for the propose test) via the tunnel. Skips cleanly if unavailable.
"""

from __future__ import annotations

import psycopg
import pytest

from jarvis import ids
from jarvis.core.context_store import get_context
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.repository import insert_event
from jarvis.intents import service
from jarvis.intents.models import Intent, IntentReasoning
from jarvis.intents.repository import insert_intent
from jarvis.tools.registry import valid_intent_types

pytestmark = pytest.mark.integration


def test_propose_persists_validated_intent_and_context(db_conn: psycopg.Connection) -> None:
    from jarvis.agents.infrastructure import propose_intent

    suffix = ids.new_id("t").split("_")[1]
    entity = f"container:itest-{suffix}"
    corr = ids.new_id(ids.CORRELATION)
    trigger = Event(
        type="container.died", severity=Severity.warning, source="docker",
        entity_ref=entity, occurred_at=utcnow(), payload={"exit_code": 137, "image": "alpine"},
        correlation_id=corr,
    )
    insert_event(db_conn, trigger)

    try:
        intent = propose_intent(entity)
    except Exception as exc:  # noqa: BLE001
        if "connect" in str(exc).lower():
            pytest.skip(f"Ollama unavailable — {exc}")
        raise

    try:
        assert intent.type in valid_intent_types()
        assert intent.correlation_id == corr  # adopted the trigger's chain
        assert intent.causation_id == trigger.id
        assert intent.context_ref
        # provenance was stored
        ctx = get_context(db_conn, intent.context_ref)
        assert ctx is not None and ctx.prompt
        # intent persisted
        row = db_conn.execute(
            "SELECT status FROM intents WHERE intent_id = %s", (intent.intent_id,)
        ).fetchone()
        assert row is not None and row["status"] == "proposed"
    finally:
        db_conn.execute("DELETE FROM intents WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM events WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM contexts WHERE context_ref = %s", (intent.context_ref,))


def test_gate_blocks_unapproved_then_dry_runs_under_observe(db_conn: psycopg.Connection) -> None:
    suffix = ids.new_id("t").split("_")[1]
    corr = ids.new_id(ids.CORRELATION)
    intent = Intent(
        type="docker.restart_container",
        target={"container": f"itest-absent-{suffix}"},
        reasoning=IntentReasoning(summary="down", confidence=0.9, risk="low", reversible=True),
        requested_by="infrastructure_agent",
        requires_approval=True,
        correlation_id=corr,
    )
    insert_intent(db_conn, intent)

    try:
        # Gate: unapproved → blocked, no execution row.
        with pytest.raises(service.ApprovalRequired):
            service.execute(db_conn, intent.intent_id)
        assert db_conn.execute(
            "SELECT count(*) AS c FROM executions WHERE intent_id = %s", (intent.intent_id,)
        ).fetchone()["c"] == 0

        # Approve, then execute under observe (default) → dry-run skipped row.
        service.approve(db_conn, intent.intent_id)
        execution = service.execute(db_conn, intent.intent_id)
        assert execution.outcome.value == "skipped"
        assert execution.correlation_id == corr
        assert execution.causation_id == intent.intent_id

        # The execution is its own row sharing the correlation_id.
        row = db_conn.execute(
            "SELECT correlation_id FROM executions WHERE exec_id = %s", (execution.exec_id,)
        ).fetchone()
        assert row is not None and row["correlation_id"] == corr
    finally:
        db_conn.execute("DELETE FROM executions WHERE correlation_id = %s", (corr,))
        db_conn.execute("DELETE FROM intents WHERE correlation_id = %s", (corr,))
