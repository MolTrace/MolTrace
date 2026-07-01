"""Repho R10: reaction warm-start priors — fitted transfer-learning prior + snapshot lineage

Revision ID: 0030_reaction_warm_start_priors
Revises: 0029_reaction_feedback
Create Date: 2026-06-24

Additive + idempotent. Adds ``reaction_warm_start_priors`` (a fitted warm-start prior for a target
reaction project: the content-hashed, gold-excluded, verified-only snapshot lineage it was fit
from, plus the prior weights). Frozen weights live in the DB, not git. No changes to existing
tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0030_reaction_warm_start_priors"
down_revision = "0029_reaction_feedback"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_warm_start_priors"):
        op.create_table(
            "reaction_warm_start_priors",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("snapshot_hash", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("objective_target", sa.Float(), nullable=True),
            sa.Column("global_mean", sa.Float(), nullable=False, server_default="0"),
            sa.Column("trained_n", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("excluded_gold_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "excluded_unverified_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("source_project_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("lineage_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("prior_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_warm_start_priors_reaction_project_id",
            "reaction_warm_start_priors",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_warm_start_priors_project_created",
            "reaction_warm_start_priors",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_warm_start_priors"):
        op.drop_table("reaction_warm_start_priors")
