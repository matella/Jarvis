"""model_prefs: per-action / per-routine backend choice (the model cookbook)

Revision ID: 0027
Revises: 0025
Create Date: 2026-06-02

Operator-editable, persisted backend choice per action key (`postmortem`, `document.ai_edit`,
`research.synthesize`, …) or routine. Feeds the router's existing resolution as the explicit
`backend` value the caller passes — the algorithm + hard overrides (breaker/budget/schema→local)
are unchanged. Named presets (Quality/Frugal/Balanced) write a batch of rows. Module #9.
"""

from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_prefs (
            id             text PRIMARY KEY,
            scope          text NOT NULL,            -- action | routine | global
            scope_key      text NOT NULL,            -- the action name / routine id ('' for global)
            backend        text NOT NULL,            -- local | claude
            model          text NOT NULL DEFAULT '', -- reserved for a future model_hint map
            params_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
            preset_name    text,
            schema_version integer NOT NULL DEFAULT 1,
            created_at     timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (scope, scope_key)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_prefs;")
