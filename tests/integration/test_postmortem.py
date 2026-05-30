"""Backlog #2 integration: generate a postmortem for an incident, then adopt its playbook.

The model is mocked (deterministic JSON) so it runs offline; the incident, memory write, and
playbook insert are live. Proves procedural memory grows from experience under operator control.
"""

from __future__ import annotations

import psycopg
import pytest

from jarvis.agents import postmortem as pm_mod
from jarvis.incidents.models import Incident
from jarvis.incidents.repository import insert_incident

pytestmark = pytest.mark.integration

FAKE = {
    "what_happened": "nginx OOM-killed twice in 5 minutes",
    "root_cause": "memory limit too low for traffic spike",
    "resolution": "raised the container memory limit and restarted",
    "playbook_title": "Recover an OOM-killed container",
    "playbook_when": "container exits with code 137 / oom_killed events",
    "playbook_procedure": "1) check mem limit 2) raise limit 3) restart 4) verify recovery",
}


def test_generate_then_adopt(db_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm_mod, "_decide", lambda *_a, **_k: FAKE)
    monkeypatch.setattr("jarvis.models.router.embed", lambda _t: [0.05] * 768)

    corr = "corr_pm_itest"
    incident = Incident(
        window_label="1h", severity="error", summary="nginx flapping",
        root_cause="oom", entity_refs=["container:nginx"], correlation_id=corr,
    )
    insert_incident(db_conn, incident)
    new_playbook_id = None
    try:
        pm = pm_mod.generate(incident.incident_id)
        assert "OOM" in pm.what_happened
        assert pm.playbook_title == "Recover an OOM-killed container"
        # postmortem stored as a memory record
        mem = db_conn.execute(
            "SELECT content FROM memory WHERE kind = 'postmortem' "
            "AND content LIKE %s ORDER BY ts DESC LIMIT 1",
            (f"%{incident.incident_id}%",),
        ).fetchone()
        assert mem is not None and "Root cause" in mem["content"]

        new_playbook_id = pm_mod.adopt_playbook(pm)
        assert new_playbook_id is not None
        pb = db_conn.execute(
            "SELECT title FROM playbooks WHERE id = %s", (new_playbook_id,)
        ).fetchone()
        assert pb["title"] == "Recover an OOM-killed container"
    finally:
        db_conn.execute("DELETE FROM memory WHERE kind = 'postmortem' AND content LIKE %s",
                        (f"%{incident.incident_id}%",))
        if new_playbook_id:
            db_conn.execute("DELETE FROM playbooks WHERE id = %s", (new_playbook_id,))
        db_conn.execute("DELETE FROM incidents WHERE correlation_id = %s", (corr,))
