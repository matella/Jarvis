"""Auto-postmortems (backlog #2) — turn a resolved incident into a postmortem + a playbook draft.

One inference over the incident (summary + root cause + the entities/events it spans) yields a
structured postmortem AND a suggested playbook (title/when/procedure). The postmortem is stored as
a `postmortem` memory record + a `postmortem.generated` event; adopting the suggestion is a
deterministic step that embeds + inserts a playbook — so procedural memory GROWS from experience,
never bypassing the operator's confirmation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from jarvis import db
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.incidents.repository import get_incident
from jarvis.memory.store import MemoryRecord, PgVectorMemoryStore

_SCHEMA = {
    "type": "object",
    "properties": {
        "what_happened": {"type": "string"},
        "root_cause": {"type": "string"},
        "resolution": {"type": "string"},
        "playbook_title": {"type": "string"},
        "playbook_when": {"type": "string"},
        "playbook_procedure": {"type": "string"},
    },
    "required": ["what_happened", "root_cause", "resolution", "playbook_title"],
}


class Postmortem(BaseModel):
    incident_id: str
    what_happened: str = ""
    root_cause: str = ""
    resolution: str = ""
    playbook_title: str = ""
    playbook_when: str = ""
    playbook_procedure: str = ""

    def as_text(self) -> str:
        return (
            f"Postmortem for {self.incident_id}\n"
            f"What happened: {self.what_happened}\n"
            f"Root cause: {self.root_cause}\n"
            f"Resolution: {self.resolution}"
        )


def _prompt(summary: str, root_cause: str, entities: list[str]) -> str:
    return (
        "Write a concise incident postmortem and suggest a reusable playbook. Incident:\n"
        f"- summary: {summary}\n- root cause: {root_cause or 'unknown'}\n"
        f"- entities: {', '.join(entities) or 'n/a'}\n\n"
        'Reply JSON {"what_happened","root_cause","resolution","playbook_title",'
        '"playbook_when","playbook_procedure"}. The playbook should be a generally reusable fix '
        "for this class of problem, not specific to one container instance."
    )


def _decide(prompt: str, correlation_id: str) -> dict[str, Any]:
    import json

    from jarvis.models.scheduler import Priority
    from jarvis.models.scheduler import chat as sched_chat

    resp = sched_chat(
        "reasoning", [{"role": "user", "content": prompt}],
        priority=Priority.BACKGROUND, correlation_id=correlation_id, format=_SCHEMA,
    )
    try:
        return json.loads(str(resp["message"]["content"]))
    except Exception:  # noqa: BLE001 — a malformed postmortem degrades to empty fields
        return {}


def generate(incident_id: str, *, store: PgVectorMemoryStore | None = None) -> Postmortem:
    """Generate + persist a postmortem for an incident (memory record + event). Does NOT add a
    playbook — that's the explicit `adopt` step."""
    with db.connect() as conn:
        incident = get_incident(conn, incident_id)
    if incident is None:
        raise ValueError(f"unknown incident: {incident_id}")

    data = _decide(
        _prompt(incident.summary, incident.root_cause or "", incident.entity_refs),
        incident.correlation_id,
    )
    pm = Postmortem(incident_id=incident_id, **{k: data.get(k, "") for k in (
        "what_happened", "root_cause", "resolution",
        "playbook_title", "playbook_when", "playbook_procedure",
    )})

    from jarvis.models.router import embed

    store = store or PgVectorMemoryStore()
    store.add(MemoryRecord(
        kind="postmortem", content=pm.as_text(), embedding=embed(pm.as_text()),
        metadata={"incident_id": incident_id, "suggested_playbook": pm.playbook_title},
    ))
    emit_event(Event(
        type="postmortem.generated", severity=Severity.info, source="postmortem",
        entity_ref=f"incident:{incident_id}", occurred_at=utcnow(),
        payload={"incident_id": incident_id, "suggested_playbook": pm.playbook_title},
        correlation_id=incident.correlation_id, causation_id=incident_id,
    ))
    return pm


def adopt_playbook(pm: Postmortem) -> str | None:
    """Codify the suggested playbook (embed + insert). Returns the new playbook id, or None."""
    if not pm.playbook_title or not pm.playbook_procedure:
        return None
    from jarvis.models.router import embed
    from jarvis.playbooks.models import Playbook
    from jarvis.playbooks.repository import add_playbook

    playbook = Playbook(
        title=pm.playbook_title, when_to_use=pm.playbook_when, procedure=pm.playbook_procedure,
    )
    index_text = f"{playbook.title}\n{playbook.when_to_use}"
    with db.connect(autocommit=True) as conn:
        add_playbook(conn, playbook, embed(index_text))
    return playbook.id
