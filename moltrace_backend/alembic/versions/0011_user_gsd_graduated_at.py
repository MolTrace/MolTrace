"""user gsd_graduated_at column for per-tenant graduation

Revision ID: 0011_user_gsd_graduated_at
Revises: 0010_ai_evidence_review
Create Date: 2026-05-28

Adds a nullable ``gsd_graduated_at`` timestamp column to the ``users``
table.  ``None`` (default) means the tenant still sees
``experimental: true`` on the opt-in ``/spectrum/analyze/gsd`` backend;
a timestamp means the admin graduated this tenant out of experimental
at that moment.  Backed by the v0.6.6 readiness verdict + scoping
endpoint: admins read the per-tenant rollup, see ``clear``, and POST
to ``/admin/users/{id}/gsd-graduation`` which sets this column.

Self-documenting choice (timestamp vs bool): the timestamp tells
operational dashboards exactly when each tenant graduated without a
separate audit query.  Clearing the flag (``ungraduate``) sets it back
to NULL; the audit event preserves the un-graduation history.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_user_gsd_graduated_at"
down_revision = "0010_ai_evidence_review"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if _column_exists("users", "gsd_graduated_at"):
        return
    op.add_column(
        "users",
        sa.Column("gsd_graduated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    if _column_exists("users", "gsd_graduated_at"):
        op.drop_column("users", "gsd_graduated_at")
