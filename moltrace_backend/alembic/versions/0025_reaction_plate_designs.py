"""Repho R3: HTE/DoE plate designs — persisted plate maps per reaction project

Revision ID: 0025_reaction_plate_designs
Revises: 0024_audit_hash_chain
Create Date: 2026-06-17

Additive + idempotent. Adds ``reaction_plate_designs`` (a generated HTE/DoE plate map —
Sobol/LHS/factorial/bo_init — stored as the full design JSON + inputs + warnings, per
reaction project). No changes to existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025_reaction_plate_designs"
down_revision = "0024_audit_hash_chain"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_plate_designs"):
        op.create_table(
            "reaction_plate_designs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("plate_format", sa.String(length=8), nullable=False, server_default="96"),
            sa.Column("strategy", sa.String(length=32), nullable=False, server_default="sobol"),
            sa.Column("well_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("design_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("inputs_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_plate_designs_reaction_project_id",
            "reaction_plate_designs",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_plate_designs_project_created",
            "reaction_plate_designs",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_plate_designs"):
        op.drop_table("reaction_plate_designs")
