"""Structure & reaction scheme service: captured drawings attached to a reaction project

Revision ID: 0033_reaction_structure_schemes
Revises: 0032_regulatory_dossier_team_ownership
Create Date: 2026-08-01

Additive + idempotent. Adds ``reaction_structure_schemes``: a structure or reaction scheme
drawn in Reaction Studio, retained as BOTH the block the chemist drew (the audit record) and
RDKit's normalized reading of it (what downstream chemistry computes on), together with the
plain-language warnings shown at capture time. Carries the ALCOA+ reversible-by-record
soft-delete columns from 0028. No changes to existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0033_reaction_structure_schemes"
down_revision = "0032_regulatory_dossier_team_ownership"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_structure_schemes"):
        op.create_table(
            "reaction_structure_schemes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("format", sa.String(length=8), nullable=False, server_default="mol"),
            sa.Column("source_block", sa.Text(), nullable=False, server_default=""),
            sa.Column("normalized_block", sa.Text(), nullable=False, server_default=""),
            sa.Column("canonical_smiles", sa.Text(), nullable=False, server_default=""),
            sa.Column("inchikey", sa.String(length=27), nullable=False, server_default=""),
            sa.Column("atom_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bond_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "component_counts_json", sa.Text(), nullable=False, server_default="{}"
            ),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason_for_change", sa.String(length=2000), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", sa.String(length=200), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_structure_schemes_reaction_project_id",
            "reaction_structure_schemes",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_structure_schemes_inchikey",
            "reaction_structure_schemes",
            ["inchikey"],
        )
        op.create_index(
            "ix_reaction_structure_schemes_deleted_at",
            "reaction_structure_schemes",
            ["deleted_at"],
        )
        op.create_index(
            "ix_reaction_structure_schemes_project_created",
            "reaction_structure_schemes",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_structure_schemes"):
        op.drop_table("reaction_structure_schemes")
