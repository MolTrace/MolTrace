from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from nmrcheck.orm import Base
from nmrcheck.settings import get_settings

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _ensure_wide_version_table(connection) -> None:
    """Widen ``alembic_version.version_num`` before Alembic creates it at VARCHAR(32).

    Alembic's built-in version table caps ``version_num`` at 32 characters, but seven
    of our revision ids are 34-38 characters (e.g. ``0005_week25_nmr2d_run_canonical_fields``).
    On an EXISTING database this never surfaced -- the table was already stamped -- but a
    migration from base against a fresh Postgres fails at ``0003`` with
    ``StringDataRightTruncation``, which is exactly what a new Cloud SQL instance does.

    Pre-creating (or widening) the table lets Alembic adopt it instead of creating a
    narrow one. Idempotent, and a fast metadata-only change on databases that already
    have it, so it is safe to run against production. Postgres-only: SQLite ignores
    VARCHAR limits, and the test suite builds its schema with ``create_all`` anyway.
    """
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            " version_num VARCHAR(255) NOT NULL,"
            " CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(
        text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
    )


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Must be committed before Alembic opens its own migration transaction.
        _ensure_wide_version_table(connection)
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
