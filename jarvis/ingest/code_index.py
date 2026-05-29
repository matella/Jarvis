"""Code indexer — read a remote repo over SSH, chunk, embed, store (secret-safe).

Secret safety is non-negotiable (CLAUDE.md Hard Rule 1): secret files are excluded, only an
allowlist of code/config types is indexed, and secret-looking assignments are redacted before
anything reaches the DB or the model.
"""

from __future__ import annotations

import re
import shlex
import subprocess

import numpy as np
import psycopg

from jarvis import db, ids
from jarvis.config import get_settings
from jarvis.models import router

# Focus on operational config: compose files + Dockerfiles + small config/scripts. Generic
# *.yml is excluded — a homelab has hundreds of app-config yaml that aren't compose stacks.
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
INDEXABLE_NAMES = ("dockerfile", *_COMPOSE_NAMES)
INDEXABLE_SUFFIXES = (".conf", ".toml", ".sh")
_SECRET_SUFFIXES = (".key", ".pem", ".crt", ".p12", ".pfx")
_SECRET_NAME_PARTS = ("secret", "credential", "id_rsa")
# Skip runtime-data / vendored / VCS dirs — they hold no config worth indexing and would
# bloat the index with noise.
_EXCLUDE_DIR_PARTS = (
    "/.git/", "/node_modules/", "/.cache/", "/cache/", "/logs/", "/tmp/",
    "/data/", "/backup/", "/backups/", "/vendor/", "/.venv/",
)


def _is_excluded_dir(path: str) -> bool:
    return any(part in path for part in _EXCLUDE_DIR_PARTS)
# Redact a line whose key contains a secret word (as a substring, so it also catches
# WIREGUARD_PRIVATE_KEY / POSTGRES_PASSWORD), keeping the key, dropping the value.
# Over-redaction is the safe failure mode.
_SECRET_LINE = re.compile(
    r"(?im)^(.*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|auth|credential)[^\n:=]*[:=]\s*)\S.*$"
)

Chunk = tuple[str, int, int, str]  # (path, start_line, end_line, content)


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1].lower()


def _is_secret_path(path: str) -> bool:
    base = _basename(path)
    if base == ".env" or base.startswith(".env"):
        return True
    if base.endswith(_SECRET_SUFFIXES):
        return True
    return any(part in base for part in _SECRET_NAME_PARTS)


def _is_indexable(path: str) -> bool:
    base = _basename(path)
    return base in INDEXABLE_NAMES or base.endswith(INDEXABLE_SUFFIXES)


def _redact(text: str) -> str:
    return _SECRET_LINE.sub(r"\1<redacted>", text)


def _chunk(text: str, chunk_lines: int) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    out: list[tuple[int, int, str]] = []
    for i in range(0, len(lines), chunk_lines):
        window = lines[i : i + chunk_lines]
        content = "\n".join(window).strip()
        if content:
            out.append((i + 1, i + len(window), content))
    return out


def _list_files(remote_ssh: str, root: str) -> list[str]:
    proc = subprocess.run(
        ["ssh", remote_ssh, f"find {shlex.quote(root)} -type f"],
        capture_output=True, text=True, timeout=60,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _read_file(remote_ssh: str, path: str, max_bytes: int) -> str:
    proc = subprocess.run(
        ["ssh", remote_ssh, f"head -c {max_bytes} {shlex.quote(path)}"],
        capture_output=True, text=True, timeout=30,
    )
    return proc.stdout


# --- store -----------------------------------------------------------------

def delete_repo(conn: psycopg.Connection, repo: str) -> None:
    conn.execute("DELETE FROM code_chunks WHERE repo = %s", (repo,))


def insert_chunks(
    conn: psycopg.Connection, repo: str, rows: list[tuple[Chunk, list[float]]]
) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO code_chunks (id, repo, path, start_line, end_line, content, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (ids.new_id(ids.CHUNK), repo, path, start, end, content,
                 np.asarray(vec, dtype=np.float32))
                for (path, start, end, content), vec in rows
            ],
        )


def search_chunks(
    conn: psycopg.Connection, query_vec: list[float], k: int = 6, repo: str | None = None
) -> list[tuple[str, int, int, str, float]]:
    q = np.asarray(query_vec, dtype=np.float32)
    sql = (
        "SELECT path, start_line, end_line, content, embedding <=> %s AS distance "
        "FROM code_chunks"
    )
    params: list[object] = [q]
    if repo is not None:
        sql += " WHERE repo = %s"
        params.append(repo)
    sql += " ORDER BY distance ASC LIMIT %s"
    params.append(k)
    rows = conn.execute(sql, params).fetchall()
    return [
        (r["path"], r["start_line"], r["end_line"], r["content"], float(r["distance"]))
        for r in rows
    ]


# --- indexing --------------------------------------------------------------

def index_repo(*, repo: str | None = None, root: str | None = None) -> int:
    """Index a remote repo into code_chunks (secrets excluded/redacted). Returns chunk count."""
    settings = get_settings()
    repo = repo or settings.code_repo_name
    root = root or settings.code_repo_path
    remote_ssh = settings.remote_ssh

    files = [
        f for f in _list_files(remote_ssh, root)
        if _is_indexable(f) and not _is_secret_path(f) and not _is_excluded_dir(f)
    ]
    chunks: list[Chunk] = []
    for path in files:
        text = _redact(_read_file(remote_ssh, path, settings.code_max_file_bytes))
        for start, end, content in _chunk(text, settings.code_chunk_lines):
            chunks.append((path, start, end, content))

    if not chunks:
        return 0

    vectors = router.embed_many([c[3] for c in chunks])
    rows = list(zip(chunks, vectors, strict=True))
    with db.connect() as conn, conn.transaction():
        delete_repo(conn, repo)
        insert_chunks(conn, repo, rows)
    return len(rows)
