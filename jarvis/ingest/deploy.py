"""Deployment detection — emit a `container.deployed` event when an image changes.

Deterministic builder (like topology/metrics): inspect each container's image + digest, diff
against the stored baseline, and emit a deploy event on change. First sighting just seeds the
baseline (no event flood on first run).
"""

from __future__ import annotations

import subprocess

import psycopg

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

# (entity, image tag, image digest)
ImageState = tuple[str, str, str]


def _inspect_images(context: str) -> list[ImageState]:
    proc = subprocess.run(
        ["docker", "--context", context, "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    )
    names = proc.stdout.split()
    if not names:
        return []
    inspected = subprocess.run(
        ["docker", "--context", context, "inspect",
         "--format", "{{.Name}}|{{.Config.Image}}|{{.Image}}", *names],
        capture_output=True, text=True, timeout=60,
    )
    out: list[ImageState] = []
    for line in inspected.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3 or not parts[0]:
            continue
        name = parts[0].lstrip("/")
        out.append((f"container:{name}", parts[1], parts[2]))
    return out


def _diff(
    current: list[ImageState], baseline: dict[str, tuple[str, str]]
) -> list[tuple[str, str, str, str, str]]:
    """Return deploy changes: (entity, image, digest, prev_image, prev_digest).

    A digest change for a known container is a redeploy. A first-seen container is NOT a
    deploy — it only seeds the baseline.
    """
    changes: list[tuple[str, str, str, str, str]] = []
    for entity, image, digest in current:
        prev = baseline.get(entity)
        if prev is None:
            continue  # first sighting → baseline seed, not a deploy
        if prev[1] != digest:
            changes.append((entity, image, digest, prev[0], prev[1]))
    return changes


def get_baseline(conn: psycopg.Connection) -> dict[str, tuple[str, str]]:
    rows = conn.execute("SELECT entity, image, digest FROM container_images").fetchall()
    return {r["entity"]: (r["image"], r["digest"]) for r in rows}


def upsert_images(conn: psycopg.Connection, current: list[ImageState]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO container_images (entity, image, digest, updated_at) "
            "VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (entity) DO UPDATE SET "
            "image = EXCLUDED.image, digest = EXCLUDED.digest, updated_at = now()",
            [(entity, image, digest) for entity, image, digest in current],
        )


def _deploy_event(entity: str, image: str, digest: str, prev_image: str, prev_digest: str) -> Event:
    return Event(
        type="container.deployed",
        severity=Severity.info,
        source="deploy",
        entity_ref=entity,
        occurred_at=utcnow(),
        payload={
            "image": image,
            "digest": digest,
            "previous_image": prev_image,
            "previous_digest": prev_digest,
        },
        correlation_id=ids.new_id(ids.CORRELATION),
    )


def detect_deployments(*, context: str | None = None) -> int:
    """Detect image changes since the last run; emit container.deployed events. Returns count."""
    context = context or get_settings().docker_context
    current = _inspect_images(context)
    with db.connect() as conn:
        baseline = get_baseline(conn)
        changes = _diff(current, baseline)
        if current:
            upsert_images(conn, current)
    for entity, image, digest, prev_image, prev_digest in changes:
        emit_event(_deploy_event(entity, image, digest, prev_image, prev_digest))
    return len(changes)
