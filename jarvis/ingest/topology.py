"""Topology builder — deterministic service-dependency graph from docker inspect.

No LLM: edges are derived from compose labels and network config. A derived store like
metrics — `build_topology` rewrites the current edge set; `edges_for` serves the correlator.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict

import psycopg

from jarvis import db
from jarvis.config import get_settings

Edge = tuple[str, str, str]  # (src_entity, dst_entity, relation)


def _inspect_all(context: str) -> list[dict]:
    names = subprocess.run(
        ["docker", "--context", context, "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    ).stdout.split()
    if not names:
        return []
    proc = subprocess.run(
        ["docker", "--context", context, "inspect", "--format", "{{json .}}", *names],
        capture_output=True, text=True, timeout=60,
    )
    out: list[dict] = []
    for line in proc.stdout.splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        labels = (raw.get("Config") or {}).get("Labels") or {}
        out.append({
            "name": (raw.get("Name") or "").lstrip("/"),
            "id": raw.get("Id") or "",
            "project": labels.get("com.docker.compose.project"),
            "service": labels.get("com.docker.compose.service"),
            "depends_on": labels.get("com.docker.compose.depends_on") or "",
            "network_mode": (raw.get("HostConfig") or {}).get("NetworkMode") or "",
        })
    return out


def _build_edges(inspections: list[dict]) -> list[Edge]:
    """Derive depends_on / network_mode / same_project edges (pure)."""
    by_id: dict[str, str] = {}
    by_proj_svc: dict[tuple[str, str], str] = {}
    by_project: dict[str, list[str]] = defaultdict(list)
    for c in inspections:
        if not c["name"]:
            continue
        if c["id"]:
            by_id[c["id"]] = c["name"]
            by_id[c["id"][:12]] = c["name"]
        if c["project"] and c["service"]:
            by_proj_svc[(c["project"], c["service"])] = c["name"]
        if c["project"]:
            by_project[c["project"]].append(c["name"])

    edges: set[Edge] = set()

    # same_project: one edge per unordered pair within a stack
    for members in by_project.values():
        uniq = sorted(set(members))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                edges.add((f"container:{uniq[i]}", f"container:{uniq[j]}", "same_project"))

    for c in inspections:
        if not c["name"]:
            continue
        src = f"container:{c['name']}"
        # depends_on: resolve compose service name -> container in the same project
        for token in (c["depends_on"] or "").split(","):
            svc = token.split(":", 1)[0].strip()
            if not svc:
                continue
            dst = by_proj_svc.get((c["project"], svc))
            if dst and dst != c["name"]:
                edges.add((src, f"container:{dst}", "depends_on"))
        # network_mode: container:<id> -> resolve to that container's name
        nm = c["network_mode"]
        if nm.startswith("container:"):
            ref = nm.split(":", 1)[1]
            dst = by_id.get(ref) or by_id.get(ref[:12])
            if dst and dst != c["name"]:
                edges.add((src, f"container:{dst}", "network_mode"))

    return sorted(edges)


def build_topology(*, context: str | None = None) -> int:
    """Inspect containers, derive edges, and rewrite the topology table atomically."""
    context = context or get_settings().docker_context
    edges = _build_edges(_inspect_all(context))
    with db.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM topology")
        if edges:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO topology (src_entity, dst_entity, relation) VALUES (%s, %s, %s)",
                    edges,
                )
    return len(edges)


def edges_for(conn: psycopg.Connection, entities: list[str]) -> list[Edge]:
    """Edges touching any of the given entities (for correlation context)."""
    if not entities:
        return []
    rows = conn.execute(
        "SELECT src_entity, dst_entity, relation FROM topology "
        "WHERE src_entity = ANY(%s) OR dst_entity = ANY(%s)",
        (entities, entities),
    ).fetchall()
    return [(r["src_entity"], r["dst_entity"], r["relation"]) for r in rows]


def all_edges(conn: psycopg.Connection) -> list[Edge]:
    rows = conn.execute(
        "SELECT src_entity, dst_entity, relation FROM topology "
        "ORDER BY relation, src_entity, dst_entity"
    ).fetchall()
    return [(r["src_entity"], r["dst_entity"], r["relation"]) for r in rows]
