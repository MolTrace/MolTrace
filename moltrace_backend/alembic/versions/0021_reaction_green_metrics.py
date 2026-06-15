"""Repho R1: green-chemistry metrics — green profiles + per-experiment assessments

Revision ID: 0021_reaction_green_metrics
Revises: 0020_session_token_hardening
Create Date: 2026-06-15

Additive + idempotent. Adds ``reaction_green_profiles`` (per-project solvent-greenness
overrides + assumptions) and ``reaction_green_assessments`` (per-experiment computed
green-chemistry metrics: E-factor, atom economy, PMI, RME, solvent green-score). No
changes to existing tables; green optimization objectives reuse the existing
``reaction_objective_profiles`` weights and the experiment ``outcome_json`` blob.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021_reaction_green_metrics"
down_revision = "0020_session_token_hardening"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_green_profiles"):
        op.create_table(
            "reaction_green_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("solvent_greenness_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("default_assumptions_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "solvent_table_version",
                sa.String(length=64),
                nullable=False,
                server_default="chem21-2016",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_green_profiles_reaction_project_id",
            "reaction_green_profiles",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_green_profiles_project_updated",
            "reaction_green_profiles",
            ["reaction_project_id", "updated_at"],
        )

    if not _table_exists("reaction_green_assessments"):
        op.create_table(
            "reaction_green_assessments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_experiment_id",
                sa.Integer(),
                sa.ForeignKey("reaction_experiments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("inputs_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_green_assessments_reaction_experiment_id",
            "reaction_green_assessments",
            ["reaction_experiment_id"],
        )
        op.create_index(
            "ix_reaction_green_assessments_reaction_project_id",
            "reaction_green_assessments",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_green_assessments_experiment_created",
            "reaction_green_assessments",
            ["reaction_experiment_id", "created_at"],
        )
        op.create_index(
            "ix_reaction_green_assessments_project_created",
            "reaction_green_assessments",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_green_assessments"):
        op.drop_table("reaction_green_assessments")
    if _table_exists("reaction_green_profiles"):
        op.drop_table("reaction_green_profiles")
