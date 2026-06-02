"""mail_cache: the inbox read-mirror (re-syncable cache, NOT the source of truth)

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-02

Extends the existing mail connector (IMAP read → events; gated mail.send) into a full inbox: a
re-syncable cache of the operator's own mail + per-message triage. Purge + re-sync rebuilds it — the
server is the truth, this is a mirror. Personal-OS module #7. (Accounts stay config-driven for v1;
a `mail_accounts` table is deferred until the UI needs it.)
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mail_cache (
            id             text PRIMARY KEY,
            account        text NOT NULL,
            uid            text NOT NULL,
            message_id     text,
            from_addr      text NOT NULL DEFAULT '',
            to_addrs       text[] NOT NULL DEFAULT '{}',
            subject        text NOT NULL DEFAULT '',
            snippet        text NOT NULL DEFAULT '',
            body_text      text NOT NULL DEFAULT '',
            folder         text NOT NULL DEFAULT 'INBOX',
            flags          text[] NOT NULL DEFAULT '{}',
            received_at    timestamptz,
            triage_json    jsonb,
            schema_version integer NOT NULL DEFAULT 1,
            synced_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (account, uid)
        );
        CREATE INDEX mail_cache_recent_idx ON mail_cache (account, received_at DESC);
        CREATE INDEX mail_cache_triage_idx
            ON mail_cache ((triage_json->>'importance'), received_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mail_cache;")
