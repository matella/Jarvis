"""initial schema: events, intents, executions, state, snapshots, memory

Revision ID: 0001
Revises:
Create Date: 2026-05-29

All boundary tables carry schema_version + correlation_id/causation_id. Constrained
string sets are TEXT + CHECK (Pydantic StrEnum is the boundary gate). IDs are prefixed
text. The embedding column is vector(768) (nomic-embed-text); changing the dimension is
a future migration + re-embed, by design.
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE events (
            id              text PRIMARY KEY,
            schema_version  integer NOT NULL DEFAULT 1,
            type            text NOT NULL,
            severity        text NOT NULL
                            CHECK (severity IN ('debug','info','warning','error','critical')),
            source          text NOT NULL,
            entity_ref      text,
            occurred_at     timestamptz NOT NULL,
            recorded_at     timestamptz NOT NULL DEFAULT now(),
            payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
            correlation_id  text NOT NULL,
            causation_id    text,
            CONSTRAINT events_type_format
                CHECK (type ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')
        );
        CREATE INDEX events_correlation_id_idx ON events (correlation_id);
        CREATE INDEX events_type_idx           ON events (type);
        CREATE INDEX events_occurred_at_idx     ON events (occurred_at);
        CREATE INDEX events_entity_ref_idx      ON events (entity_ref);

        CREATE TABLE intents (
            intent_id         text PRIMARY KEY,
            schema_version    integer NOT NULL DEFAULT 1,
            type              text NOT NULL,
            target            jsonb NOT NULL DEFAULT '{}'::jsonb,
            reasoning         jsonb NOT NULL,
            requested_by      text NOT NULL,
            context_ref       text,
            requires_approval boolean NOT NULL DEFAULT true,
            status            text NOT NULL DEFAULT 'proposed'
                              CHECK (status IN ('proposed','approved','rejected',
                                                'executing','executed','failed','cancelled')),
            created_at        timestamptz NOT NULL DEFAULT now(),
            correlation_id    text NOT NULL,
            causation_id      text
        );
        CREATE INDEX intents_correlation_id_idx ON intents (correlation_id);
        CREATE INDEX intents_status_idx          ON intents (status);

        CREATE TABLE executions (
            exec_id         text PRIMARY KEY,
            schema_version  integer NOT NULL DEFAULT 1,
            intent_id       text NOT NULL REFERENCES intents (intent_id),
            attempt         integer NOT NULL DEFAULT 1,
            outcome         text NOT NULL DEFAULT 'pending'
                            CHECK (outcome IN ('pending','success','failure','skipped')),
            before_state    jsonb,
            after_state     jsonb,
            error           text,
            failure_class   text
                            CHECK (failure_class IS NULL OR failure_class IN (
                                'permission_denied','timeout','network_failure',
                                'resource_exhaustion','validation_failure',
                                'tool_unavailable','unknown')),
            created_at      timestamptz NOT NULL DEFAULT now(),
            correlation_id  text NOT NULL,
            causation_id    text
        );
        CREATE INDEX executions_intent_id_idx      ON executions (intent_id);
        CREATE INDEX executions_correlation_id_idx ON executions (correlation_id);

        CREATE TABLE state (
            entity        text NOT NULL,
            kind          text NOT NULL,
            status        text,
            attrs         jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_at    timestamptz NOT NULL DEFAULT now(),
            last_event_id text,
            PRIMARY KEY (entity, kind)
        );

        CREATE TABLE snapshots (
            id            text PRIMARY KEY,
            ts            timestamptz NOT NULL DEFAULT now(),
            kind          text NOT NULL,
            blob          jsonb NOT NULL,
            last_event_id text
        );

        CREATE TABLE memory (
            id        text PRIMARY KEY,
            kind      text NOT NULL,
            content   text NOT NULL,
            embedding vector(768) NOT NULL,
            metadata  jsonb NOT NULL DEFAULT '{}'::jsonb,
            ts        timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX memory_embedding_idx ON memory USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX memory_kind_idx       ON memory (kind);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS memory;
        DROP TABLE IF EXISTS snapshots;
        DROP TABLE IF EXISTS state;
        DROP TABLE IF EXISTS executions;
        DROP TABLE IF EXISTS intents;
        DROP TABLE IF EXISTS events;
        """
    )
