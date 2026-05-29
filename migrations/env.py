"""Alembic environment — URL sourced from jarvis settings; no ORM metadata.

Migrations are hand-written raw SQL (`op.execute`), so `target_metadata` stays None.
The psycopg3 driver is selected explicitly (`postgresql+psycopg://`).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from jarvis.config import get_settings

config = context.config


def _url() -> str:
    return get_settings().postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)


config.set_main_option("sqlalchemy.url", _url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
