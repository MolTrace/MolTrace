"""Subject-addressed review tasks: review_tasks.subject_type / subject_id

Revision ID: 0035_subject_addressed_review_tasks
Revises: 0034_reaction_project_team_ownership
Create Date: 2026-07-31

Additive. A review task was a SpectraCheck-session task by construction — ``session_id`` was
required — so Regentry could not say "someone look at this filing" and Repho could not say
"someone check this campaign". This adds the polymorphic subject pair the compliance floor
already uses elsewhere (``electronic_signature_records.target_type/target_id``), and relaxes
``session_id`` so a task can be addressed the new way instead.

Existing rows keep their ``session_id`` and are untouched; the SpectraCheck session-scoped
surface still writes it. Exactly one addressing mode is populated per row, enforced in the store
rather than by a database constraint, because SQLite cannot add one to an existing table.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0035_subject_addressed_review_tasks"
down_revision = "0034_reaction_project_team_ownership"
branch_labels = None
depends_on = None

_TABLE = "review_tasks"
_INDEX = "ix_review_tasks_subject"


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
    # SQLite cannot alter a column's nullability in place; dev SQLite databases are built by
    # create_all from the ORM, which already has it nullable.
    if bind.dialect.name != "sqlite":
        op.alter_column(_TABLE, "session_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    for column in ("subject_id", "subject_type"):
        if column in _columns(bind):
            op.drop_column(_TABLE, column)
    # Rows addressed by subject have no session; they must go before session_id is required again.
    if bind.dialect.name != "sqlite":
        op.execute(sa.text("DELETE FROM review_tasks WHERE session_id IS NULL"))
        op.alter_column(_TABLE, "session_id", existing_type=sa.Integer(), nullable=False)
