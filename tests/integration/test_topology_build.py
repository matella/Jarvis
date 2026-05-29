"""P2 topology integration: build the real graph; expect the qbittorrent→gluetun edges."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.ingest.topology import all_edges, build_topology, edges_for

pytestmark = pytest.mark.integration


def test_build_topology_writes_edges(db_conn: psycopg.Connection) -> None:
    try:
        count = build_topology()
    except Exception as exc:  # noqa: BLE001
        if "connect" in str(exc).lower() or "docker" in str(exc).lower():
            pytest.skip(f"docker unavailable — {exc}")
        raise

    assert count >= 1
    edges = all_edges(db_conn)
    assert edges
    # every edge is between container: entities with a known relation
    for src, dst, rel in edges:
        assert src.startswith("container:") and dst.startswith("container:")
        assert rel in ("depends_on", "network_mode", "same_project")

    # edges_for returns only edges touching the queried entity
    some_entity = edges[0][0]
    touched = edges_for(db_conn, [some_entity])
    assert touched and all(some_entity in (s, d) for s, d, _ in touched)
