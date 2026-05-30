"""6a integration: the WS chat flow end-to-end over a test client + REST reads.

Exercises the real safety path: a question returns an answer; "restart X" becomes a *gated* proposed
Intent (never executed on the spot); a confirming "yes" approves + executes per mode and writes an
audit row attributed to the authenticated actor; presence transitions stream for the orb. The model
is mocked (`_decide`) so the test is deterministic and offline; everything else is live.
"""

from __future__ import annotations

import psycopg
import pytest
from starlette.testclient import TestClient

from jarvis.agents import conversation as convo
from jarvis.agents.conversation import _Decision
from jarvis.core.modes import Mode, get_mode, set_mode
from jarvis.gateway.app import app
from jarvis.intents.models import Risk

pytestmark = pytest.mark.integration


def _fake_decide(prompt: str, *, correlation_id: str, context_ref: str) -> _Decision:
    # Key off the user's utterance ("User: ..."), not the prompt — the capability summary itself
    # mentions docker.restart_container, so a bare "restart" substring would match every prompt.
    if "user: restart" in prompt.lower():
        return _Decision(
            route="propose", message="I'll restart nginx.",
            intent_type="docker.restart_container", target={"container": "nginx"},
            summary="restart nginx", risk=Risk.medium, reversible=True, confidence=0.9,
        )
    return _Decision(route="answer", message="All containers look healthy.")


def test_ws_chat_propose_confirm_flow(
    db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(convo, "_decide", _fake_decide)
    original_mode = get_mode(db_conn)
    set_mode(db_conn, Mode.observe)  # deterministic: execute is a dry-run (skipped); no infra touch

    conversation_id = None
    intent_id = None
    try:
        with TestClient(app).websocket_connect("/ws") as ws:
            ready = ws.receive_json()
            assert ready["kind"] == "ready"
            conversation_id = ready["conversation_id"]
            assert ws.receive_json()["kind"] == "presence"  # baseline

            # 1) a question → grounded answer
            ws.send_json({"text": "how are things?"})
            assert ws.receive_json() == {"kind": "presence", "state": "thinking"}
            turn = ws.receive_json()
            assert turn["kind"] == "turn"
            assert turn["result"]["route"] == "answer"
            assert ws.receive_json()["state"] == "speaking"
            assert ws.receive_json()["kind"] == "presence"  # back to baseline

            # 2) "restart nginx" → a GATED proposal, not an execution
            ws.send_json({"text": "restart nginx"})
            assert ws.receive_json()["state"] == "thinking"
            turn = ws.receive_json()
            assert turn["result"]["route"] == "propose"
            intent_id = turn["result"]["intent_id"]
            assert intent_id is not None
            ws.receive_json()  # speaking
            ws.receive_json()  # baseline

            row = db_conn.execute(
                "SELECT status, requested_by FROM intents WHERE intent_id = %s", (intent_id,)
            ).fetchone()
            assert row["status"] == "proposed"  # gated — nothing ran yet
            assert row["requested_by"] == "user:local"

            # 3) "yes" → approve + execute (dry-run under observe) + audit row
            ws.send_json({"text": "yes"})
            assert ws.receive_json()["state"] == "thinking"
            turn = ws.receive_json()
            assert turn["result"]["route"] == "confirm"
            assert turn["result"]["intent_id"] == intent_id

        # the action is attributed to the authenticated actor in the audit log
        audit = db_conn.execute(
            "SELECT actor, action FROM audit_log WHERE target = %s ORDER BY id", (intent_id,)
        ).fetchall()
        actions = {(a["actor"], a["action"]) for a in audit}
        assert ("user:local", "intent.approve") in actions
        assert ("user:local", "intent.execute") in actions
    finally:
        set_mode(db_conn, original_mode)
        db_conn.execute("DELETE FROM audit_log WHERE target = %s", (intent_id,))
        if intent_id:
            db_conn.execute("DELETE FROM executions WHERE intent_id = %s", (intent_id,))
            db_conn.execute("DELETE FROM intents WHERE intent_id = %s", (intent_id,))
        if conversation_id:
            db_conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))


def test_rest_reads_open_dev_mode() -> None:
    client = TestClient(app)
    assert client.get("/api/events?n=3").status_code == 200
    assert client.get("/api/state").status_code == 200
    assert client.get("/health").status_code == 200
    body = client.get("/api/events?n=1").json()
    assert isinstance(body, list)
