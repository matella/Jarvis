"""Research-run persistence — the harness log (upsert + read accessors)."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

from jarvis.research.models import ResearchRun, Source

_COLS = (
    "id, query, status, depth, plan_json, sources_json, report_md, document_id, "
    "cost_json, schema_version, correlation_id, created_at, completed_at"
)


def _row_to_run(row: dict) -> ResearchRun:
    plan = row.pop("plan_json") or {}
    sources = row.pop("sources_json") or []
    cost = row.pop("cost_json") or {}
    return ResearchRun(
        sub_questions=plan.get("sub_questions", []),
        search_terms=plan.get("search_terms", []),
        sources=[Source(**s) for s in sources],
        cost=cost,
        **row,
    )


def save(conn: psycopg.Connection, run: ResearchRun) -> ResearchRun:
    """Upsert a run (the harness builds it whole, then persists once)."""
    conn.execute(
        f"INSERT INTO research_runs ({_COLS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, plan_json=EXCLUDED.plan_json, "
        "sources_json=EXCLUDED.sources_json, report_md=EXCLUDED.report_md, "
        "document_id=EXCLUDED.document_id, cost_json=EXCLUDED.cost_json, "
        "completed_at=EXCLUDED.completed_at",
        (
            run.id, run.query, run.status.value, run.depth.value,
            Json({"sub_questions": run.sub_questions, "search_terms": run.search_terms}),
            Json([s.model_dump() for s in run.sources]), run.report_md, run.document_id,
            Json(run.cost), run.schema_version, run.correlation_id, run.created_at,
            run.completed_at,
        ),
    )
    return run


def get(conn: psycopg.Connection, run_id: str) -> ResearchRun | None:
    row = conn.execute(f"SELECT {_COLS} FROM research_runs WHERE id = %s", (run_id,)).fetchone()
    return _row_to_run(row) if row else None


def recent(conn: psycopg.Connection, *, limit: int = 20) -> list[ResearchRun]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM research_runs ORDER BY created_at DESC LIMIT %s", (limit,)
    ).fetchall()
    return [_row_to_run(r) for r in rows]
