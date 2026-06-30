"""Repho R9: reaction feedback — chemist accept/edit/reject + reason, with model version

Revision ID: 0029_reaction_feedback
Revises: 0028_alcoa_reason_soft_delete
Create Date: 2026-06-23

Additive + idempotent. Adds ``reaction_feedback`` (a chemist's structured judgment on a reaction
proposal, retained with the model version that produced it so the preference re-ranker and the
A/B promotion gate can be reproduced). No changes to existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0029_reaction_feedback"
down_revision = "0028_alcoa_reason_soft_delete"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_feedback"):
        op.create_table(
            "reaction_feedback",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("proposal_ref", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("decision", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("reason", sa.String(length=40), nullable=True),
            sa.Column("free_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("model_version", sa.String(length=120), nullable=True),
            sa.Column("features_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "is_safety_signal", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "is_preference_learnable", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_feedback_reaction_project_id",
            "reaction_feedback",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_feedback_project_created",
            "reaction_feedback",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_feedback"):
        op.drop_table("reaction_feedback")
