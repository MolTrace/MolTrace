"""Repho team ownership: reaction_projects.organization_id

Revision ID: 0034_reaction_project_team_ownership
Revises: 0033_reaction_structure_schemes
Create Date: 2026-07-31

Additive + idempotent, and the exact counterpart of 0032 for regulatory dossiers. A
process-chemistry campaign is run by a group — someone designs the plate, someone runs it,
someone reads the results — but ownership was creator-only (``owner_id``), so a five-chemist
team had to share one login.

NULL is the existing behaviour: a campaign with no organization stays creator-only, so every
existing row is unchanged and no backfill is required or performed. New campaigns are stamped
with the creator's organization when they have exactly one active membership; ambiguity
deliberately falls back to creator-only rather than over-sharing.

Access widens only, and the path gate, the body-id checks and the campaign list all consult the
same predicate, so a list can never show a campaign that 404s when opened.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0034_reaction_project_team_ownership"
down_revision = "0033_reaction_structure_schemes"
branch_labels = None
depends_on = None

_TABLE = "reaction_projects"
_COLUMN = "organization_id"
_INDEX = "ix_reaction_projects_organization_id"


def _has_column(bind, table: str, column: str) -> bool:
    return column in {col["name"] for col in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, index: str) -> bool:
    return index in {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, _TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))
        # SQLite cannot add a foreign key to an existing table; the constraint is expressed in the
        # ORM either way, and dev SQLite databases are built by create_all rather than by alembic.
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_reaction_projects_organization_id",
                _TABLE,
                "organizations",
                [_COLUMN],
                ["id"],
                ondelete="SET NULL",
            )
    if not _has_index(bind, _TABLE, _INDEX):
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, _TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _has_column(bind, _TABLE, _COLUMN):
        if bind.dialect.name != "sqlite":
            op.drop_constraint("fk_reaction_projects_organization_id", _TABLE, type_="foreignkey")
        op.drop_column(_TABLE, _COLUMN)
