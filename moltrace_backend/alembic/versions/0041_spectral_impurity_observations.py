"""Spectral impurity observations: the SpectraCheck -> Regentry audit record

Revision ID: 0041_spectral_impurity_observations
Revises: 0040_action_item_ownership
Create Date: 2026-08-06

Additive + idempotent. Adds ``spectral_impurity_observations``: one contaminant observed in a
spectrum, together with the ICH Q3C clause that applies to it, so a reviewer can walk from a
regulatory limit back to the exact peak in the exact analysis it came from.

Scoped by the ANALYSIS owner. ``user_id`` is denormalized from the source analysis at write time
and is the only authorizing column; ``reaction_project_id`` is provenance, never permission.
Reaction projects widen to active organization members while ``analyses`` has no organization
column at all, so scoping these rows by the project would expose a compound name and chemical
shift out of a spectrum the reader cannot open.

Every regulatory column is nullable on purpose: a refusal is a first-class outcome, and an
unresolved identity carries no class, no limit and no rule-set version. NOT NULL here would make
the three refusal branches unstorable.

``analysis_id`` is SET NULL rather than CASCADE — the observation is an audit record and must
outlive the analysis row. No changes to existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0041_spectral_impurity_observations"
down_revision = "0040_action_item_ownership"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("spectral_impurity_observations"):
        op.create_table(
            "spectral_impurity_observations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "analysis_id",
                sa.Integer(),
                sa.ForeignKey("analyses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "observed_shift_ppm", sa.Float(), nullable=False, server_default="0.0"
            ),
            sa.Column("solvent", sa.String(length=50), nullable=True),
            sa.Column("observed_label", sa.String(length=200), nullable=True),
            sa.Column("compound", sa.String(length=200), nullable=True),
            sa.Column("expected_ppm", sa.Float(), nullable=True),
            sa.Column("delta_ppm", sa.Float(), nullable=True),
            sa.Column("match_kind", sa.String(length=32), nullable=True),
            sa.Column(
                "identity_status",
                sa.String(length=32),
                nullable=False,
                server_default="unresolved",
            ),
            sa.Column("unresolved_reason", sa.String(length=64), nullable=True),
            sa.Column("unresolved_detail", sa.Text(), nullable=True),
            sa.Column("q3c_class_number", sa.Integer(), nullable=True),
            sa.Column("q3c_class_description", sa.String(length=200), nullable=True),
            sa.Column("concentration_limit_ppm", sa.Float(), nullable=True),
            sa.Column("pde_mg_per_day", sa.Float(), nullable=True),
            sa.Column("regulatory_basis", sa.Text(), nullable=True),
            sa.Column("table_reference", sa.String(length=120), nullable=True),
            sa.Column("rule_set_version", sa.String(length=80), nullable=True),
            sa.Column(
                "quantitation_available",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("observed_level_ppm", sa.Float(), nullable=True),
            sa.Column("compliance_note", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "human_review_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_spectral_impurity_observations_user_created",
            "spectral_impurity_observations",
            ["user_id", "created_at"],
        )
        op.create_index(
            "ix_spectral_impurity_observations_analysis_id",
            "spectral_impurity_observations",
            ["analysis_id"],
        )
        op.create_index(
            "ix_spectral_impurity_observations_reaction_project_id",
            "spectral_impurity_observations",
            ["reaction_project_id"],
        )


def downgrade() -> None:
    if _table_exists("spectral_impurity_observations"):
        op.drop_index(
            "ix_spectral_impurity_observations_reaction_project_id",
            table_name="spectral_impurity_observations",
        )
        op.drop_index(
            "ix_spectral_impurity_observations_analysis_id",
            table_name="spectral_impurity_observations",
        )
        op.drop_index(
            "ix_spectral_impurity_observations_user_created",
            table_name="spectral_impurity_observations",
        )
        op.drop_table("spectral_impurity_observations")
