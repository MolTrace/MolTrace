"""Subject-addressed approvals: approval_records.subject_type / subject_id

Revision ID: 0037_subject_addressed_approvals
Revises: 0036_subject_addressed_comments
Create Date: 2026-08-01

Additive, and the third table to take the subject pair after review tasks (0035) and comments
(0036). An approval was a SpectraCheck-session approval by construction, so a regulatory or
process-chemistry team had no general sign-off record.

Existing rows keep their ``session_id`` and are untouched. Exactly one addressing mode is
populated per row, enforced in the store rather than by a database constraint, because SQLite
cannot add one to an existing table.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037_subject_addressed_approvals"
down_revision = "0036_subject_addressed_comments"
branch_labels = None
depends_on = None

_TABLE = "approval_records"
_INDEX = "ix_approval_records_subject"


def _columns(bind) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(_TABLE)}


def _has_index(bind, index: str) -> bool:
    return index in {idx["name"] for idx in sa.inspect(bind).get_indexes(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)
    if "subject_type" not in existing:
        op.add_column(_TABLE, sa.Column("subject_type", sa.String(length=48), nullable=True))
    if "subject_id" not in existing:
        op.add_column(_TABLE, sa.Column("subject_id", sa.Integer(), nullable=True))
    if not _has_index(bind, _INDEX):
        op.create_index(_INDEX, _TABLE, ["subject_type", "subject_id"])
    if bind.dialect.name != "sqlite":
        op.alter_column(_TABLE, "session_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    for column in ("subject_id", "subject_type"):
        if column in _columns(bind):
            op.drop_column(_TABLE, column)
    if bind.dialect.name != "sqlite":
        op.execute(sa.text("DELETE FROM approval_records WHERE session_id IS NULL"))
        op.alter_column(_TABLE, "session_id", existing_type=sa.Integer(), nullable=False)
