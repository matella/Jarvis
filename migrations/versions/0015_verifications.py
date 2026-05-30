"""verifications: did the action actually work? (outcome verification, closing the loop)

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-30

After an execution settles, a deterministic check asks whether the intended effect held (container
healthy, no fresh failures). The result is a queryable row + a `verification.completed` event,
linked by correlation_id to the intent it judges. This is the missing piece for trustworthy
autonomy: confidence and learning feed off whether past actions actually worked.
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE verifications (
            id             text PRIMARY KEY,
            subject_type   text NOT NULL,
            subject_id     text NOT NULL,
            check_kind     text NOT NULL,
            status         text NOT NULL
                           CHECK (status IN ('verified', 'unverified', 'inconclusive')),
            detail         text,
            correlation_id text NOT NULL,
            created_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (subject_type, subject_id)
        );
        CREATE INDEX verifications_subject_idx ON verifications (subject_type, subject_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS verifications;")
