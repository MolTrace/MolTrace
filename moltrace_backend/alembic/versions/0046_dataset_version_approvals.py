"""Two separate people promote a dataset version

Revision ID: 0046_dataset_version_approvals
Revises: 0045_knowledge_source_revisions
Create Date: 2026-08-08

Additive. New ``dataset_version_approvals`` table.

The gap this closes: promoting a dataset version to ``approved`` is the point where
curated records start training something, and one actor could do it alone by
setting a status field. ``approve_record``/``reject_record`` take a single actor
and nothing required a second.

Scoped to promotion on purpose. Two-person control on every extracted record would
not survive contact with a 10,000-record corpus; on the one transition where the
corpus starts influencing a model, it is cheap and defensible.

The unique constraint on ``(dataset_version_id, approver_user_id)`` is what makes
the rule unbypassable rather than conventional: one human with two sessions still
has one user id, so a second approval is refused by the database rather than by a
check a future caller could forget. ``approver_user_id`` is nullable only because
the column has to exist before any row does -- the store refuses an approval that
has no signed-in person behind it, since a machine credential is not a person and
two calls carrying it are the same principal.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0046_dataset_version_approvals"
down_revision = "0045_knowledge_source_revisions"
branch_labels = None
depends_on = None

_TABLE = "dataset_version_approvals"
_PARENT = "dataset_versions"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if _PARENT not in tables or _TABLE in tables:
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_version_id",
            sa.Integer(),
            sa.ForeignKey(f"{_PARENT}.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("approver_user_id", sa.Integer(), nullable=True),
        sa.Column("approver_email", sa.String(length=200), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "approver_user_id", name="uq_dataset_version_approver"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    op.drop_table(_TABLE)
