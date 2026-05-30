"""feedback: operator ratings on proposals/incidents (adaptive-attention signal)

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-30

A 👍/👎 on a proposal or incident, recorded both as a row (queryable) and a `feedback.recorded`
event. This is the supervision signal adaptive attention needs — tune notifier/reactor thresholds by
entity/type from approve/reject/execute + outcome history later. Rating is +1 / -1.
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE feedback (
            id          bigserial PRIMARY KEY,
            target_type text NOT NULL,
            target_id   text NOT NULL,
            rating      integer NOT NULL CHECK (rating IN (-1, 1)),
            note        text,
            actor       text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX feedback_target_idx ON feedback (target_type, target_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback;")
