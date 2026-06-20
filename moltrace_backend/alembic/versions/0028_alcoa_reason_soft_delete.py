"""Security Prompt 12: ALCOA+ reason-for-change + reversible-by-record soft delete

Revision ID: 0028_alcoa_reason_soft_delete
Revises: 0027_e_signature_record_binding
Create Date: 2026-06-19

Additive + idempotent. Adds three nullable columns to the existing ``controlled_records`` table so a
regulated change records its *why* (``reason_for_change``, a queryable column rather than a JSON
blob) and a deletion is reversible-by-record (``deleted_at`` + ``deleted_by`` — soft delete, the row
is retained, never physically removed). No backfill: legacy archived rows keep their reason in
``metadata_json`` (honest — not reconstructed).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_alcoa_reason_soft_delete"
down_revision = "0027_e_signature_record_binding"
branch_labels = None
depends_on = None

_TABLE = "controlled_records"


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return any(col["name"] == column for col in sa.inspect(op.get_bind()).get_columns(table))


def _index_exists(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if not _column_exists(_TABLE, "reason_for_change"):
        op.add_column(_TABLE, sa.Column("reason_for_change", sa.String(length=2000), nullable=True))
    if not _column_exists(_TABLE, "deleted_at"):
        op.add_column(_TABLE, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(_TABLE, "deleted_by"):
        op.add_column(_TABLE, sa.Column("deleted_by", sa.String(length=200), nullable=True))
    if not _index_exists(_TABLE, "ix_controlled_records_deleted_at"):
        op.create_index("ix_controlled_records_deleted_at", _TABLE, ["deleted_at"])


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if _index_exists(_TABLE, "ix_controlled_records_deleted_at"):
        op.drop_index("ix_controlled_records_deleted_at", table_name=_TABLE)
    for column in ("deleted_by", "deleted_at", "reason_for_change"):
        if _column_exists(_TABLE, column):
            op.drop_column(_TABLE, column)
