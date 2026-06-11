"""regulatory_dossiers.created_by_user_id owner column + audit backfill

Revision ID: 0015_dossier_created_by_user_id
Revises: 0014_dossier_route_elemental_summary
Create Date: 2026-06-10

Adds a nullable owner column so regulatory dossier READS can be scoped to the
creating user (a system api key still sees all). The column is set going forward by
``create_dossier``; for EXISTING rows it is backfilled from the audit trail — every
dossier's creator is recorded on its ``regulatory.dossier.create`` audit event
(``audit_events.actor_user_id``). Rows with no attributable creator (system-key-created
or pre-audit) stay NULL, which the read-scoping rule treats as system-visible-only.

Additive + idempotent: nullable column, no NOT NULL, auto-runs on deploy. The backfill
is a correlated UPDATE portable across SQLite and PostgreSQL.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_dossier_created_by_user_id"
down_revision = "0014_dossier_route_elemental_summary"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


# Backfill each dossier's owner from its creation audit event. Kept in sync with the
# test in tests/test_regulatory_dossier_read_scoping_api.py.
_BACKFILL_SQL = """
UPDATE regulatory_dossiers
SET created_by_user_id = (
    SELECT ae.actor_user_id
    FROM audit_events AS ae
    WHERE ae.entity_type = 'regulatory_dossier'
      AND ae.entity_id = regulatory_dossiers.id
      AND ae.event_type = 'regulatory.dossier.create'
      AND ae.actor_user_id IS NOT NULL
    ORDER BY ae.id DESC
    LIMIT 1
)
WHERE created_by_user_id IS NULL
"""


def upgrade() -> None:
    if not _column_exists("regulatory_dossiers", "created_by_user_id"):
        op.add_column(
            "regulatory_dossiers",
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _index_exists("regulatory_dossiers", "ix_regulatory_dossiers_created_by_user"):
        op.create_index(
            "ix_regulatory_dossiers_created_by_user",
            "regulatory_dossiers",
            ["created_by_user_id"],
        )

    # Backfill legacy rows from the audit trail (only when the audit table is present).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "audit_events" in inspector.get_table_names():
        bind.execute(sa.text(_BACKFILL_SQL))


def downgrade() -> None:
    if _index_exists("regulatory_dossiers", "ix_regulatory_dossiers_created_by_user"):
        op.drop_index("ix_regulatory_dossiers_created_by_user", table_name="regulatory_dossiers")
    if _column_exists("regulatory_dossiers", "created_by_user_id"):
        op.drop_column("regulatory_dossiers", "created_by_user_id")
