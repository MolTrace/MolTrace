"""Tamper-evident audit hash chain — chain columns on audit_events + audit_checkpoints

Revision ID: 0024_audit_hash_chain
Revises: 0023_spectracheck_project_owner_id
Create Date: 2026-06-18

Adds the Prompt 10 hash-chain columns (chain_seq / prev_hash / entry_hash / chain_ts) to
``audit_events`` plus the ``audit_checkpoints`` signed-anchor table. Both tables are built from
ORM metadata by ``Base.metadata.create_all`` (database.py), which runs AFTER ``alembic upgrade
head`` in the deploy command — so on a brand-new database ``audit_events`` does not exist yet
when this runs; we no-op, and ``create_all`` then builds both tables with the chain columns and
``ux_audit_events_chain_seq`` already present. On a partially-migrated production DB (audit_events
exists, chain columns/checkpoints don't) this patches them in. Every step is guarded, so the
migration is safe on fresh, partially-migrated, and already-current databases alike.

No backfill: legacy rows keep ``chain_seq = NULL`` (pre-chain). The verifier starts at the first
hashed row linking to genesis — re-hashing historical rows under a key we did not hold when they
were written would be a false attestation. Additive + idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024_audit_hash_chain"
down_revision = "0023_spectracheck_project_owner_id"
branch_labels = None
depends_on = None

_TABLE = "audit_events"
_CHK = "audit_checkpoints"
_HEAD = "audit_chain_head"
_SEQ_IX = "ux_audit_events_chain_seq"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    # Fresh database: audit_events is built later by create_all (with the chain columns + the
    # unique index + audit_checkpoints), so there is nothing to alter here.
    if not _table_exists(_TABLE):
        return

    for column, type_ in (
        ("chain_seq", sa.Integer()),
        ("prev_hash", sa.String(71)),
        ("entry_hash", sa.String(71)),
        ("chain_ts", sa.DateTime(timezone=True)),
    ):
        if not _column_exists(_TABLE, column):
            op.add_column(_TABLE, sa.Column(column, type_, nullable=True))
    if not _index_exists(_TABLE, _SEQ_IX):
        op.create_index(_SEQ_IX, _TABLE, ["chain_seq"], unique=True)

    if not _table_exists(_CHK):
        op.create_table(
            _CHK,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("anchored_at", sa.DateTime(timezone=True)),
            sa.Column("from_seq", sa.Integer()),
            sa.Column("tip_seq", sa.Integer()),
            sa.Column("tip_hash", sa.String(71)),
            sa.Column("row_count", sa.Integer()),
            sa.Column("signature", sa.String(80)),
            sa.Column("key_id", sa.String(32)),
            sa.UniqueConstraint("tip_seq", name="uq_audit_checkpoints_tip_seq"),
        )
        op.create_index("ix_audit_checkpoints_created", _CHK, ["created_at"])

    if not _table_exists(_HEAD):
        op.create_table(
            _HEAD,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("max_seq", sa.Integer()),
            sa.Column("tip_hash", sa.String(71)),
            sa.Column("signature", sa.String(80)),
            sa.Column("key_id", sa.String(32)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )


def downgrade() -> None:
    if _table_exists(_HEAD):
        op.drop_table(_HEAD)
    if _table_exists(_CHK):
        op.drop_table(_CHK)
    if _index_exists(_TABLE, _SEQ_IX):
        op.drop_index(_SEQ_IX, table_name=_TABLE)
    for column in ("chain_ts", "entry_hash", "prev_hash", "chain_seq"):
        if _column_exists(_TABLE, column):
            op.drop_column(_TABLE, column)
