"""Backups + DR — pg_dump the source-of-truth DB, keep an off-box copy, and verify restores.

The DB runs in a container on the remote box; `pg_dump`/`psql` run via the SSH docker context
(no local client needed). A backup is written off-box (this machine) AND copied to the remote, and
a `verify_restore` drill proves the dump actually restores — a backup is only as good as a tested
restore.
"""

from __future__ import annotations

import gzip
import os
import subprocess

import psycopg

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event

_SCRATCH_DB = "jarvis_restore_check"


def _files_to_prune(names: list[str], keep: int) -> list[str]:
    """Given backup filenames (timestamped, lexically sortable), return the ones to delete."""
    ordered = sorted(names, reverse=True)  # newest first (UTC timestamp in the name)
    return ordered[keep:]


def _docker(*args: str) -> list[str]:
    s = get_settings()
    return ["docker", "--context", s.docker_context, *args]


def run_backup() -> dict:
    """Dump the DB → gzip → off-box file (+ a remote copy); prune to retention. Returns info."""
    s = get_settings()
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    name = f"jarvis-{stamp}.sql.gz"
    try:
        dump = subprocess.run(
            _docker("exec", s.postgres_container, "pg_dump", "-U", s.postgres_user, s.postgres_db),
            capture_output=True, timeout=300, check=True,
        ).stdout
        blob = gzip.compress(dump)

        os.makedirs(s.backup_offbox_dir, exist_ok=True)
        offbox = os.path.join(s.backup_offbox_dir, name)
        with open(offbox, "wb") as fh:
            fh.write(blob)

        # copy to the remote box too
        remote_cmd = f"mkdir -p {s.backup_remote_dir} && cat > {s.backup_remote_dir}/{name}"
        subprocess.run(
            ["ssh", s.remote_ssh, remote_cmd],
            input=blob, capture_output=True, timeout=120, check=True,
        )
        _prune(s)
        emit_event(_event("backup.completed", Severity.info, file=name, bytes=len(blob)))
        return {"file": name, "bytes": len(blob), "offbox": offbox}
    except Exception as exc:  # noqa: BLE001
        emit_event(_event("backup.failed", Severity.error, error=str(exc)[:300]))
        raise


def _prune(s) -> None:
    offbox = [f for f in os.listdir(s.backup_offbox_dir) if f.endswith(".sql.gz")] \
        if os.path.isdir(s.backup_offbox_dir) else []
    for old in _files_to_prune(offbox, s.backup_retention_count):
        os.remove(os.path.join(s.backup_offbox_dir, old))
    # remote: keep newest N
    subprocess.run(
        ["ssh", s.remote_ssh,
         f"ls -1t {s.backup_remote_dir}/jarvis-*.sql.gz 2>/dev/null | "
         f"tail -n +{s.backup_retention_count + 1} | xargs -r rm -f"],
        capture_output=True, timeout=30,
    )


def latest_backup() -> str | None:
    s = get_settings()
    if not os.path.isdir(s.backup_offbox_dir):
        return None
    names = [f for f in os.listdir(s.backup_offbox_dir) if f.endswith(".sql.gz")]
    files = sorted(names, reverse=True)
    return os.path.join(s.backup_offbox_dir, files[0]) if files else None


def verify_restore(path: str | None = None) -> dict:
    """Restore a dump into a scratch DB and sanity-check it (the DR drill). Returns a report."""
    s = get_settings()
    path = path or latest_backup()
    if not path:
        raise FileNotFoundError("no backup found to verify")
    with open(path, "rb") as fh:
        sql = gzip.decompress(fh.read())

    subprocess.run(_docker("exec", s.postgres_container,
                           "dropdb", "-U", s.postgres_user, "--if-exists", _SCRATCH_DB),
                   capture_output=True, timeout=60)
    subprocess.run(_docker("exec", s.postgres_container,
                           "createdb", "-U", s.postgres_user, _SCRATCH_DB),
                   capture_output=True, timeout=60, check=True)
    try:
        subprocess.run(
            _docker("exec", "-i", s.postgres_container, "psql", "-U", s.postgres_user,
                    "-d", _SCRATCH_DB, "-v", "ON_ERROR_STOP=1", "-q"),
            input=sql, capture_output=True, timeout=300, check=True,
        )
        dsn = (f"postgresql://{s.postgres_user}:{s.postgres_password}"
               f"@{s.postgres_host}:{s.postgres_port}/{_SCRATCH_DB}")
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            events = conn.execute("SELECT count(*) FROM events").fetchone()[0]
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            has_core = all(
                conn.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{t}",)).fetchone()[0]
                for t in ("events", "intents", "executions", "state")
            )
        report = {"path": path, "ok": has_core, "events": events, "alembic_version": version}
    finally:
        subprocess.run(_docker("exec", s.postgres_container,
                               "dropdb", "-U", s.postgres_user, "--if-exists", _SCRATCH_DB),
                       capture_output=True, timeout=60)
    if not report["ok"]:
        raise RuntimeError(f"restore verification failed: {report}")
    return report


def _event(event_type: str, severity: Severity, **payload: object) -> Event:
    return Event(
        type=event_type, severity=severity, source="backup", entity_ref="system:backup",
        occurred_at=utcnow(), payload=payload, correlation_id=ids.new_id(ids.CORRELATION),
    )
