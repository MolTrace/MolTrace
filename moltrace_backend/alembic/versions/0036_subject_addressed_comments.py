"""Subject-addressed comments: evidence_comments.subject_type / subject_id

Revision ID: 0036_subject_addressed_comments
Revises: 0035_subject_addressed_review_tasks
Create Date: 2026-08-01

Additive, and the exact counterpart of 0035 for comments. A comment was a SpectraCheck-session
comment by construction — ``session_id`` was required — so a regulatory or process-chemistry team
had nowhere to discuss a record they now jointly own.

Existing rows keep their ``session_id`` and are untouched; the session-scoped surface, which can
also anchor a note to a specific piece of evidence, still writes it. Exactly one addressing mode
is populated per row, enforced in the store rather than by a database constraint, because SQLite
cannot add one to an existing table.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0036_subject_addressed_comments"
down_revision = "0035_subject_addressed_review_tasks"
branch_labels = None
depends_on = None

_TABLE = "evidence_comments"
_INDEX = "ix_evidence_comments_subject"


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
    # Subject-addressed rows have no session; they must go before session_id is required again.
    if bind.dialect.name != "sqlite":
        op.execute(sa.text("DELETE FROM evidence_comments WHERE session_id IS NULL"))
        op.alter_column(_TABLE, "session_id", existing_type=sa.Integer(), nullable=False)
