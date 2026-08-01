"""reaction_design_spaces.exploration_states_json (per-variable free/fixed/excluded)

Revision ID: 0032_reaction_design_space_exploration_states
Revises: 0031_reaction_phase_c_wiring
Create Date: 2026-07-31

Backs the reaction design-space per-variable exploration-state editor. The editor marks each
reaction variable ``free`` / ``fixed`` / ``excluded``; the FE round-trips this as a list of
``{reaction_variable_id, exploration_state}`` entries. ``ReactionDesignSpaceORM`` gained a
``exploration_states_json`` Text column (default ``'[]'``) to persist it — but reaction tables
are built from ORM metadata via ``Base.metadata.create_all``, which creates MISSING TABLES but
never adds a column to an existing one. So any deployment whose ``reaction_design_spaces`` was
created before this column existed is missing it, and the round-trip read/write would fail.
This migration adds it for those deployments (the analogue of 0022 for reaction_projects).

On a brand-new database ``reaction_design_spaces`` does not yet exist when this runs (it is
created later by ``create_all`` at app startup, with the column already present) — so we no-op.
All steps are guarded; the migration is safe on fresh, partially-migrated, and already-current
databases alike. Additive + idempotent; existing rows default to ``'[]'`` (all variables free),
which reproduces the prior behavior exactly.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0032_reaction_design_space_exploration_states"
down_revision = "0031_reaction_phase_c_wiring"
branch_labels = None
depends_on = None

_TABLE = "reaction_design_spaces"
_COLUMN = "exploration_states_json"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    # Fresh database: reaction_design_spaces is built later by create_all (with the column
    # already present), so there is nothing to alter here.
    if not _table_exists(_TABLE):
        return
    if not _column_exists(_TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    if _column_exists(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
