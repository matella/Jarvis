"""research_runs: the deep-research harness log (plan → search → synthesize)

Revision ID: 0026
Revises: 0022
Create Date: 2026-06-02

A bounded deterministic harness over one-shot inferences (Hard Rule #2 — never an agent loop). This
row is the harness LOG (not a user document); the report becomes a Document (or Note). Personal-OS
module #5. `status` walks planning→searching→synthesizing→done (or partial/failed).
"""

from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE research_runs (
            id              text PRIMARY KEY,
            query           text NOT NULL,
            status          text NOT NULL DEFAULT 'planning',
            depth           text NOT NULL DEFAULT 'standard',
            plan_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
            sources_json    jsonb NOT NULL DEFAULT '[]'::jsonb,
            report_md       text NOT NULL DEFAULT '',
            document_id     text,
            cost_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
            schema_version  integer NOT NULL DEFAULT 1,
            correlation_id  text NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            completed_at    timestamptz
        );
        CREATE INDEX research_runs_recent_idx ON research_runs (created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS research_runs;")
