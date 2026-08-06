"""Regulatory action-item ownership: created_by_user_id / organization_id

Revision ID: 0040_action_item_ownership
Revises: 0039_registry_attributability
Create Date: 2026-08-06

Additive. An action item may legitimately hang off a batch, a compound, an evidence link, a
requirement — or nothing at all. But the list only ever reached items through an inner join on the
dossier, so any item without one was created successfully and then permanently invisible to the
person who created it: the API reported 201 and the work disappeared.

Stamping the raiser and their team makes those rows reachable, mirroring how a dossier is owned.
Existing rows have NULL for both and stay reachable exactly as before, through their dossier.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040_action_item_ownership"
down_revision = "0039_registry_attributability"
branch_labels = None
depends_on = None

_TABLE = "regulatory_action_items"
_COLUMNS = {"created_by_user_id": "users", "organization_id": "organizations"}


def _columns(bind) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(_TABLE)}


def _has_index(bind, index: str) -> bool:
    return index in {idx["name"] for idx in sa.inspect(bind).get_indexes(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)
    for column, target in _COLUMNS.items():
        if column not in existing:
            op.add_column(_TABLE, sa.Column(column, sa.Integer(), nullable=True))
            # SQLite cannot add a foreign key to an existing table; the ORM expresses it either
            # way, and dev SQLite databases are built by create_all rather than by alembic.
            if bind.dialect.name != "sqlite":
                op.create_foreign_key(
                    f"fk_{_TABLE}_{column}", _TABLE, target, [column], ["id"], ondelete="SET NULL"
                )
        index = f"ix_{_TABLE}_{column}"
        if not _has_index(bind, index):
            op.create_index(index, _TABLE, [column])


def downgrade() -> None:
    bind = op.get_bind()
    for column in _COLUMNS:
        index = f"ix_{_TABLE}_{column}"
        if _has_index(bind, index):
            op.drop_index(index, table_name=_TABLE)
        if column in _columns(bind):
            if bind.dialect.name != "sqlite":
                op.drop_constraint(f"fk_{_TABLE}_{column}", _TABLE, type_="foreignkey")
            op.drop_column(_TABLE, column)
