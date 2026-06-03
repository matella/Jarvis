"""app_sessions: single-operator session login for the personal-OS shell

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-02

Graduates the app from a localStorage bearer token to a real server-side session: a passphrase
(hash in `.env`, never DB) mints an opaque token; we store only its sha256 **hash** here. The cookie
is HttpOnly/SameSite=Strict. A row is revocable + expirable; `last_seen_at` slides on use. Local /
Tailscale-only, never publicly exposed (DECISIONS unchanged).
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app_sessions (
            token_hash     text PRIMARY KEY,
            created_at     timestamptz NOT NULL DEFAULT now(),
            last_seen_at   timestamptz NOT NULL DEFAULT now(),
            expires_at     timestamptz NOT NULL,
            user_agent     text,
            revoked        boolean NOT NULL DEFAULT false,
            schema_version integer NOT NULL DEFAULT 1
        );
        CREATE INDEX app_sessions_live_idx ON app_sessions (revoked, expires_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_sessions;")
