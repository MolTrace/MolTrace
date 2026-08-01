"""Regentry team ownership: regulatory_dossiers.organization_id

Revision ID: 0032_regulatory_dossier_team_ownership
Revises: 0031_reaction_phase_c_wiring
Create Date: 2026-07-31

Additive + idempotent. Regulatory affairs is a team activity — a reviewer, a toxicologist and a
QA lead all touch one filing — but dossier ownership was creator-only (``created_by_user_id``), so
a colleague could not see a filing at all. This adds a nullable ``organization_id`` alongside it.

NULL is the existing behaviour: a dossier with no organization stays creator-only, so every
existing row is unchanged and no backfill is required or performed. New dossiers are stamped with
the creator's organization when they have exactly one active membership; ambiguity deliberately
falls back to creator-only rather than over-sharing.

Access widens only — the creator arm is untouched — and both the route gate and the dossier list
consult the same predicate, so a queue can never show a row that 404s when opened.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0032_regulatory_dossier_team_ownership"
down_revision = "0031_reaction_phase_c_wiring"
branch_labels = None
depends_on = None

_TABLE = "regulatory_dossiers"
_COLUMN = "organization_id"
_INDEX = "ix_regulatory_dossiers_organization_id"


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
                "fk_regulatory_dossiers_organization_id",
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
            op.drop_constraint(
                "fk_regulatory_dossiers_organization_id", _TABLE, type_="foreignkey"
            )
        op.drop_column(_TABLE, _COLUMN)
