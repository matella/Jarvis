"""Playbook persistence — store + cosine retrieval. Pure SQL (the model layer embeds)."""

from __future__ import annotations

import numpy as np
import psycopg

from jarvis.playbooks.models import Playbook


def add_playbook(conn: psycopg.Connection, playbook: Playbook, embedding: list[float]) -> None:
    conn.execute(
        "INSERT INTO playbooks (id, title, when_to_use, procedure, embedding, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            playbook.id, playbook.title, playbook.when_to_use, playbook.procedure,
            np.asarray(embedding, dtype=np.float32), playbook.created_at,
        ),
    )


def list_playbooks(conn: psycopg.Connection, limit: int = 50) -> list[Playbook]:
    rows = conn.execute(
        "SELECT id, title, when_to_use, procedure, created_at FROM playbooks "
        "ORDER BY id DESC LIMIT %s",
        (limit,),
    ).fetchall()
    return [Playbook(**row) for row in rows]


def search_playbooks(
    conn: psycopg.Connection, query_vec: list[float], k: int = 2
) -> list[tuple[Playbook, float]]:
    q = np.asarray(query_vec, dtype=np.float32)
    rows = conn.execute(
        "SELECT id, title, when_to_use, procedure, created_at, embedding <=> %s AS distance "
        "FROM playbooks ORDER BY distance ASC LIMIT %s",
        (q, k),
    ).fetchall()
    out: list[tuple[Playbook, float]] = []
    for row in rows:
        distance = float(row.pop("distance"))
        out.append((Playbook(**row), distance))
    return out
