"""code_sessions: OpenCode runs in an isolated worktree → reviewable diff (gated apply)

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-02

OpenCode runs headless inside a throwaway git worktree (its autonomy confined to a disposable copy);
its `git diff` is the artifact. Applying the diff to a real repo is a separate GATED step. This row
is the harness log. Personal-OS module #10 (heaviest Hard-Rule-#1 reconciliation). The live headless
OpenCode command is ON HOLD pending the spike.
"""

from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE code_sessions (
            id              text PRIMARY KEY,
            repo_path       text NOT NULL,
            base_ref        text NOT NULL DEFAULT 'HEAD',
            worktree_path   text NOT NULL DEFAULT '',
            task            text NOT NULL,
            status          text NOT NULL DEFAULT 'running',
            diff_text       text NOT NULL DEFAULT '',
            files_changed   text[] NOT NULL DEFAULT '{}',
            log_text        text NOT NULL DEFAULT '',
            applied         boolean NOT NULL DEFAULT false,
            applied_commit  text,
            cost_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
            schema_version  integer NOT NULL DEFAULT 1,
            correlation_id  text NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            completed_at    timestamptz
        );
        CREATE INDEX code_sessions_recent_idx ON code_sessions (created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS code_sessions;")
