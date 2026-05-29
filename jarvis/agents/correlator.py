"""Alert correlator — deterministic clustering, one-shot LLM root-cause.

Deterministic code decides WHAT correlates: warning+ alerts in the window are grouped into
temporal bursts and deduped. The LLM is handed one cluster at a time and only explains it
(summary + root-cause hypothesis); it never picks membership and never invents events.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import timedelta

from pydantic import ValidationError

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.core.context_store import save_context
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.incidents.models import Incident, IncidentAnalysis
from jarvis.incidents.repository import insert_incident
from jarvis.ingest.topology import edges_for
from jarvis.models import router

_SEVERITY_ORDER = [
    Severity.debug, Severity.info, Severity.warning, Severity.error, Severity.critical,
]
_ALERT_SEVERITIES = ("warning", "error", "critical")
# Correlate real operational alerts only — never Jarvis's own cognition/meta events
# (incident.correlated, execution.recorded, ...), else correlation feeds on its own output.
_META_SOURCES = ("correlator", "router", "orchestrator", "infrastructure_agent")

_SYSTEM = (
    "You are Jarvis's alert correlator. You are given ONE cluster of related infrastructure "
    "alerts (already grouped by time + entity). Respond with ONLY a JSON object "
    '{"summary": str, "root_cause": str}: a one-line summary of what happened and your best '
    "single root-cause hypothesis. Base it only on the alerts shown — never invent events. "
    "If the alerts are unrelated or the cause is unclear, say so in root_cause."
)


def _fetch_alerts(conn, since) -> list[Event]:
    rows = conn.execute(
        "SELECT * FROM events WHERE severity = ANY(%s) AND occurred_at >= %s "
        "AND source <> ALL(%s) ORDER BY occurred_at",
        (list(_ALERT_SEVERITIES), since, list(_META_SOURCES)),
    ).fetchall()
    return [Event(**row) for row in rows]


def cluster(alerts: list[Event], gap_s: int) -> list[list[Event]]:
    """Group time-sorted alerts into bursts: a gap > gap_s starts a new cluster."""
    clusters: list[list[Event]] = []
    for alert in alerts:  # already sorted by occurred_at
        if clusters and (alert.occurred_at - clusters[-1][-1].occurred_at).total_seconds() <= gap_s:
            clusters[-1].append(alert)
        else:
            clusters.append([alert])
    return clusters


def _max_severity(cluster_events: list[Event]) -> Severity:
    return max((e.severity for e in cluster_events), key=_SEVERITY_ORDER.index)


def _dedup_lines(cluster_events: list[Event]) -> list[str]:
    """Collapse repeats keyed (type, entity) into 'type entity (xN)' lines."""
    counts = Counter((e.type, e.entity_ref or "-") for e in cluster_events)
    return [
        f"{etype} {entity}" + (f" (x{n})" if n > 1 else "")
        for (etype, entity), n in counts.items()
    ]


def _recent_deploys(conn, entities: list[str], since) -> list[tuple[str, str]]:
    if not entities:
        return []
    rows = conn.execute(
        "SELECT entity_ref, payload->>'image' AS image FROM events "
        "WHERE type = 'container.deployed' AND entity_ref = ANY(%s) AND occurred_at >= %s "
        "ORDER BY occurred_at",
        (entities, since),
    ).fetchall()
    return [(r["entity_ref"], r["image"]) for r in rows]


def _render(
    cluster_events: list[Event],
    edges: list[tuple[str, str, str]] | None = None,
    deploys: list[tuple[str, str]] | None = None,
) -> str:
    start = cluster_events[0].occurred_at
    end = cluster_events[-1].occurred_at
    header = f"Cluster of {len(cluster_events)} alerts from {start:%H:%M:%S} to {end:%H:%M:%S} UTC:"
    text = header + "\n" + "\n".join(f"- {line}" for line in _dedup_lines(cluster_events))
    if edges:
        deps = sorted({f"{src} {rel} {dst}" for src, dst, rel in edges})
        text += "\n\nKnown dependencies:\n" + "\n".join(f"- {line}" for line in deps)
    if deploys:
        lines = sorted({f"{entity} -> {image}" for entity, image in deploys})
        text += "\n\nRecent deployments:\n" + "\n".join(f"- {line}" for line in lines)
    return text


def _context_ref(prompt: str, model: str) -> str:
    return "ctx_" + hashlib.sha256((prompt + model).encode()).hexdigest()[:16]


def _messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"{prompt}\n\nRespond with the JSON object only."},
    ]


def _analyze(prompt: str, correlation_id: str, context_ref: str) -> IncidentAnalysis:
    resp = router.chat(
        "reasoning", _messages(prompt),
        correlation_id=correlation_id, context_ref=context_ref, format="json",
    )
    try:
        return IncidentAnalysis.model_validate_json(str(resp["message"]["content"]))
    except ValidationError as exc:
        raise ValueError(f"correlation analysis failed schema validation: {exc}") from exc


def _window_label(since: timedelta) -> str:
    seconds = int(since.total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def correlate(since: timedelta) -> list[Incident]:
    """Correlate warning+ alerts in the window into incidents."""
    settings = get_settings()
    since_dt = utcnow() - since
    window = _window_label(since)
    incidents: list[Incident] = []

    with db.connect(autocommit=True) as conn:
        alerts = _fetch_alerts(conn, since_dt)
        for cluster_events in cluster(alerts, settings.incident_cluster_gap_s):
            if len(cluster_events) < settings.incident_min_alerts:
                continue
            correlation_id = ids.new_id(ids.CORRELATION)
            entities = sorted({e.entity_ref for e in cluster_events if e.entity_ref})
            prompt = _render(
                cluster_events, edges_for(conn, entities), _recent_deploys(conn, entities, since_dt)
            )
            context_ref = _context_ref(prompt, settings.model_reasoning)
            save_context(
                conn, context_ref=context_ref, prompt=prompt,
                model=settings.model_reasoning,
                params={"num_ctx": settings.inference_context, "keep_alive": settings.keep_alive},
            )
            analysis = _analyze(prompt, correlation_id, context_ref)
            incident = Incident(
                window_label=window,
                severity=_max_severity(cluster_events),
                summary=analysis.summary,
                root_cause=analysis.root_cause,
                entity_refs=entities,
                event_ids=[e.id for e in cluster_events],
                event_count=len(cluster_events),
                context_ref=context_ref,
                correlation_id=correlation_id,
            )
            insert_incident(conn, incident)
            emit_event(_incident_event(incident))
            incidents.append(incident)

    return incidents


def _incident_event(incident: Incident) -> Event:
    return Event(
        type="incident.correlated",
        severity=incident.severity,
        source="correlator",
        entity_ref=f"incident:{incident.incident_id}",
        occurred_at=utcnow(),
        payload={
            "summary": incident.summary,
            "root_cause": incident.root_cause,
            "event_count": incident.event_count,
        },
        correlation_id=incident.correlation_id,
    )
