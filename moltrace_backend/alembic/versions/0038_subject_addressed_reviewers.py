"""Subject-addressed reviewer nominations: session_reviewers.subject_type / subject_id

Revision ID: 0038_subject_addressed_reviewers
Revises: 0037_subject_addressed_approvals
Create Date: 2026-08-01

Additive, and the fourth table to take the subject pair after review tasks (0035), comments
(0036) and approvals (0037).

A nomination on a filing or a campaign is informational: it records who is expected to look, and
does not grant access — access comes from the owning team. That is a deliberate difference from
the SpectraCheck session behaviour, where a reviewer row does confer a session role.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0038_subject_addressed_reviewers"
down_revision = "0037_subject_addressed_approvals"
branch_labels = None
depends_on = None

_TABLE = "session_reviewers"
_INDEX = "ix_session_reviewers_subject"


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
        op.execute(sa.text("DELETE FROM session_reviewers WHERE session_id IS NULL"))
        op.alter_column(_TABLE, "session_id", existing_type=sa.Integer(), nullable=False)
