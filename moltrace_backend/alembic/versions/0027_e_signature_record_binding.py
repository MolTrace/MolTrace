"""Security Prompt 11: e-signature record binding (21 CFR Part 11 §11.70 / §11.100)

Revision ID: 0027_e_signature_record_binding
Revises: 0026_reaction_safety_screenings
Create Date: 2026-06-18

Additive + idempotent. Adds three nullable columns to the existing ``electronic_signature_records``
table so a signature binds (a) the authenticated server principal — ``signer_user_id`` (§11.100
attribution, never client-supplied), and (b) a SHA-256 of the exact signed record snapshot —
``record_content_hash`` + the content-bound ``signature_digest`` (§11.70 record linking, making a
signature non-transferable to a different record/version).

Legacy rows keep their existing ``signature_hash`` and verify as "unbound" (honest — they predate
content binding), never as tampered. No backfill: the original record content at signing time is
unknown, so binding cannot be reconstructed. The FK is added only on PostgreSQL; SQLite cannot
ALTER-ADD a column with an inline/added FK cleanly, and the application layer enforces the
relationship there.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_e_signature_record_binding"
down_revision = "0026_reaction_safety_screenings"
branch_labels = None
depends_on = None

_TABLE = "electronic_signature_records"


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return any(col["name"] == column for col in sa.inspect(op.get_bind()).get_columns(table))


def _index_exists(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _table_exists(_TABLE):
        # The table is created by an earlier migration; nothing to bind on a DB without it.
        return

    if not _column_exists(_TABLE, "signer_user_id"):
        op.add_column(_TABLE, sa.Column("signer_user_id", sa.Integer(), nullable=True))
    if not _column_exists(_TABLE, "record_content_hash"):
        op.add_column(_TABLE, sa.Column("record_content_hash", sa.String(length=71), nullable=True))
    if not _column_exists(_TABLE, "signature_digest"):
        op.add_column(_TABLE, sa.Column("signature_digest", sa.String(length=71), nullable=True))

    # FK only where ALTER-ADD constraint is supported cleanly (Postgres). SQLite skips it.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        existing_fks = {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys(_TABLE)}
        if "fk_esign_signer_user" not in existing_fks:
            op.create_foreign_key(
                "fk_esign_signer_user",
                _TABLE,
                "users",
                ["signer_user_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if not _index_exists(_TABLE, "ix_esignatures_signer_user"):
        op.create_index("ix_esignatures_signer_user", _TABLE, ["signer_user_id"])
    if not _index_exists(_TABLE, "ix_esignatures_record_content"):
        op.create_index(
            "ix_esignatures_record_content",
            _TABLE,
            ["target_type", "target_id", "record_content_hash"],
        )


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if _index_exists(_TABLE, "ix_esignatures_record_content"):
        op.drop_index("ix_esignatures_record_content", table_name=_TABLE)
    if _index_exists(_TABLE, "ix_esignatures_signer_user"):
        op.drop_index("ix_esignatures_signer_user", table_name=_TABLE)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        existing_fks = {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys(_TABLE)}
        if "fk_esign_signer_user" in existing_fks:
            op.drop_constraint("fk_esign_signer_user", _TABLE, type_="foreignkey")
    for column in ("signature_digest", "record_content_hash", "signer_user_id"):
        if _column_exists(_TABLE, column):
            op.drop_column(_TABLE, column)
