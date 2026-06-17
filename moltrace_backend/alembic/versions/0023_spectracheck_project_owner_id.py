"""spectracheck_projects.owner_id owner column + indexes (SpectraCheck per-user access)

Revision ID: 0023_spectracheck_project_owner_id
Revises: 0022_reaction_project_owner_id
Create Date: 2026-06-16

Backs SpectraCheck's per-user owner-scoping. ``SpectraCheckProjectORM`` declares a nullable
``owner_id`` (FK ``users.id``), its single + composite owner indexes, and a
``uq_spectracheck_projects_owner_name`` unique constraint — and ``spectracheck_store`` reads
are owner-scoped on it (``_project_visible`` / ``WHERE owner_id = …``). But like the reaction
tables, ``spectracheck_projects`` is built from ORM metadata via ``Base.metadata.create_all``
(database.py), which creates MISSING TABLES but never adds a column to an existing one. So any
deployment whose ``spectracheck_projects`` was created before ``owner_id`` entered the ORM is
missing the column, and the owner-scoped reads would fail in prod. This adds it for those
deployments — the SpectraCheck analogue of 0022 (reaction) and 0015 (dossiers).

``spectracheck_projects`` is created by ``create_all`` (which runs at app startup, AFTER
``alembic upgrade head`` in the deploy command), so on a brand-new database the table does not
yet exist when this runs — we no-op, and ``create_all`` then builds it with ``owner_id``, both
indexes, and the unique constraint already present. Every step is guarded, so the migration is
safe on fresh, partially-migrated, and already-current databases alike.

No backfill: SpectraCheck records only SESSION-scoped audit events (``spectracheck.session.*``
etc.), never a project-creation event capturing the creator, so there is no attributable owner
for pre-existing rows. They keep ``owner_id = NULL``, which the read-scoping rule treats as
visible only to a system api key / admin. (This is also why the unique constraint adds cleanly
on existing data — all-NULL ``owner_id`` never collides under SQL NULL semantics.) New projects
are owner-stamped on create going forward. Additive + idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023_spectracheck_project_owner_id"
down_revision = "0022_reaction_project_owner_id"
branch_labels = None
depends_on = None

_TABLE = "spectracheck_projects"
_OWNER_IX = "ix_spectracheck_projects_owner_id"
_OWNER_UPDATED_IX = "ix_spectracheck_projects_owner_updated"
_OWNER_NAME_UQ = "uq_spectracheck_projects_owner_name"


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


def _unique_constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(uc["name"] == constraint_name for uc in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    # Fresh database: spectracheck_projects is built later by create_all (with owner_id, both
    # indexes, and the unique constraint), so there is nothing to alter here.
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
    # index (from __table_args__) — both match what create_all produces.
    if not _index_exists(_TABLE, _OWNER_IX):
        op.create_index(_OWNER_IX, _TABLE, ["owner_id"])
    if not _index_exists(_TABLE, _OWNER_UPDATED_IX):
        op.create_index(_OWNER_UPDATED_IX, _TABLE, ["owner_id", "updated_at"])
    # Unique (owner_id, name): a user can't have two projects with the same name. Safe to add
    # against existing data because every pre-existing row's owner_id is NULL (no backfill) and
    # NULLs do not collide under SQL NULL semantics.
    if not _unique_constraint_exists(_TABLE, _OWNER_NAME_UQ):
        op.create_unique_constraint(_OWNER_NAME_UQ, _TABLE, ["owner_id", "name"])


def downgrade() -> None:
    if _unique_constraint_exists(_TABLE, _OWNER_NAME_UQ):
        op.drop_constraint(_OWNER_NAME_UQ, _TABLE, type_="unique")
    if _index_exists(_TABLE, _OWNER_UPDATED_IX):
        op.drop_index(_OWNER_UPDATED_IX, table_name=_TABLE)
    if _index_exists(_TABLE, _OWNER_IX):
        op.drop_index(_OWNER_IX, table_name=_TABLE)
    if _column_exists(_TABLE, "owner_id"):
        op.drop_column(_TABLE, "owner_id")
