"""calendar_events: local editable events (truth) + Google/ICS read-mirror

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-02

`source='local'` rows are the source of truth (operator/Jarvis author them); `source='google'|'ics'`
rows are a re-syncable MIRROR (deduped by external_uid, read-only — no write-back to Google in v1).
Personal-OS module #8. (Accounts stay config/secret-driven for v1; a `calendar_accounts` table is
deferred until the UI needs it.)
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE calendar_events (
            id                 text PRIMARY KEY,
            source             text NOT NULL DEFAULT 'local',
            external_uid       text,
            title              text NOT NULL,
            location           text NOT NULL DEFAULT '',
            description        text NOT NULL DEFAULT '',
            starts_at          timestamptz NOT NULL,
            ends_at            timestamptz,
            all_day            boolean NOT NULL DEFAULT false,
            rrule              text,
            status             text NOT NULL DEFAULT 'confirmed',
            source_entity_ref  text,
            schema_version     integer NOT NULL DEFAULT 1,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),
            synced_at          timestamptz,
            UNIQUE (source, external_uid)
        );
        CREATE INDEX calendar_events_window_idx ON calendar_events (starts_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS calendar_events;")
