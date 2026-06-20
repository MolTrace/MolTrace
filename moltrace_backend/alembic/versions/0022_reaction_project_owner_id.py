"""reaction_projects.owner_id owner column + audit backfill (Repho per-user access)

Revision ID: 0022_reaction_project_owner_id
Revises: 0021_reaction_green_metrics
Create Date: 2026-06-16

Backs the Repho owner-scoping (per-user access control) on reaction endpoints. The
``ReactionProjectORM`` gained a nullable ``owner_id`` (FK ``users.id``) plus its indexes,
but reaction tables are built from ORM metadata via ``Base.metadata.create_all`` — which
creates MISSING TABLES but never adds a column to an existing one. So any deployment whose
``reaction_projects`` was created before ``owner_id`` existed is missing the column, and the
owner-scoped ``WHERE owner_id = …`` reads would fail. This migration adds it for those
deployments (the analogue of 0015 for dossiers).

Unlike a migrated table, ``reaction_projects`` is created by ``create_all`` (which runs at
app startup, AFTER ``alembic upgrade head`` in the deploy command). So on a brand-new
database the table does not yet exist when this runs — we no-op, and ``create_all`` then
builds it with ``owner_id`` and both indexes already present. All steps are guarded, so the
migration is safe on fresh, partially-migrated, and already-current databases alike.

Existing rows are backfilled from the creation audit event (``reaction.project.create`` on
``audit_events``, carrying the creator in ``actor_user_id``) so a project stays accessible to
the user who made it. Rows with no attributable creator stay NULL — visible only to a system
api key / admin under the read-scoping rule. Additive + idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_reaction_project_owner_id"
down_revision = "0021_reaction_green_metrics"
branch_labels = None
depends_on = None

_TABLE = "reaction_projects"
_OWNER_IX = "ix_reaction_projects_owner_id"
_OWNER_UPDATED_IX = "ix_reaction_projects_owner_updated"


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


# Backfill each project's owner from its creation audit event. Mirrors 0015's dossier
# backfill; kept in sync with the reaction.project.create event written by create_project.
_BACKFILL_SQL = f"""
UPDATE {_TABLE}
SET owner_id = (
    SELECT ae.actor_user_id
    FROM audit_events AS ae
    WHERE ae.entity_type = 'reaction_project'
      AND ae.entity_id = {_TABLE}.id
      AND ae.event_type = 'reaction.project.create'
      AND ae.actor_user_id IS NOT NULL
    ORDER BY ae.id DESC
    LIMIT 1
)
WHERE owner_id IS NULL
"""


def upgrade() -> None:
    # Fresh database: reaction_projects is built later by create_all (with owner_id and both
    # indexes), so there is nothing to alter here.
    if not _table_exists(_TABLE):
        return

    if not _column_exists(_TABLE, "owner_id"):
        op.add_column(
            _TABLE,
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    # Single-column index (from the column's index=True) and the composite owner/updated
    # index (from __table_args__) — both match what create_all produces, so the two
    # schema-creation paths converge.
    if not _index_exists(_TABLE, _OWNER_IX):
        op.create_index(_OWNER_IX, _TABLE, ["owner_id"])
    if not _index_exists(_TABLE, _OWNER_UPDATED_IX):
        op.create_index(_OWNER_UPDATED_IX, _TABLE, ["owner_id", "updated_at"])

    # Backfill legacy rows from the audit trail (only when the audit table is present).
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text
    # _BACKFILL_SQL is a module-level constant — a static correlated UPDATE with no
    # interpolation, no parameters, no user input. The Semgrep rule guards against
    # injection via dynamic text(); here the SQL string is fully literal and runs in
    # the alembic migration context (admin-only deploy step), so the injection vector
    # the rule warns about does not exist. Mirrors the 0015 dossier backfill pattern.
    bind = op.get_bind()
    if "audit_events" in sa.inspect(bind).get_table_names():
        bind.execute(sa.text(_BACKFILL_SQL))


def downgrade() -> None:
    if _index_exists(_TABLE, _OWNER_UPDATED_IX):
        op.drop_index(_OWNER_UPDATED_IX, table_name=_TABLE)
    if _index_exists(_TABLE, _OWNER_IX):
        op.drop_index(_OWNER_IX, table_name=_TABLE)
    if _column_exists(_TABLE, "owner_id"):
        op.drop_column(_TABLE, "owner_id")
