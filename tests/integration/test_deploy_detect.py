"""P3 deploy integration: detection runs and the baseline stabilizes."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.ingest.deploy import detect_deployments, get_baseline

pytestmark = pytest.mark.integration


def test_detect_seeds_then_stabilizes(db_conn: psycopg.Connection) -> None:
    try:
        detect_deployments()  # first run seeds baseline for running containers
    except Exception as exc:  # noqa: BLE001
        if "connect" in str(exc).lower() or "docker" in str(exc).lower():
            pytest.skip(f"docker unavailable — {exc}")
        raise

    baseline = get_baseline(db_conn)
    assert baseline  # at least jarvis-postgres/redis are running
    for entity, (image, digest) in baseline.items():
        assert entity.startswith("container:")
        assert image and digest

    # immediate second run: nothing changed → 0 deploys
    assert detect_deployments() == 0
