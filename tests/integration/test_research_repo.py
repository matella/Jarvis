"""Research-run persistence round-trip against a live DB."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.research import repository
from jarvis.research.models import ResearchRun, ResearchStatus, Source

pytestmark = pytest.mark.integration


def test_save_get_recent(db_conn: psycopg.Connection) -> None:
    db_conn.execute("DELETE FROM research_runs")
    run = ResearchRun(
        query="why is the sky blue?",
        status=ResearchStatus.done,
        search_terms=["rayleigh scattering"],
        sources=[Source(title="A", url="http://a", snippet="s")],
        report_md="# Answer [1]",
        cost={"inferences": 2, "sources": 1},
    )
    repository.save(db_conn, run)

    got = repository.get(db_conn, run.id)
    assert got is not None
    assert got.report_md == "# Answer [1]" and got.search_terms == ["rayleigh scattering"]
    assert [s.url for s in got.sources] == ["http://a"]
    assert got.cost == {"inferences": 2, "sources": 1}

    # upsert: re-save with a document_id
    repository.save(db_conn, run.model_copy(update={"document_id": "document:x"}))
    assert repository.get(db_conn, run.id).document_id == "document:x"
    assert [r.id for r in repository.recent(db_conn)] == [run.id]
