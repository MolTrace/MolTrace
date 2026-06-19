"""Repho R6: reaction safety screenings — persisted structural screens + review verdict

Revision ID: 0026_reaction_safety_screenings
Revises: 0025_reaction_plate_designs
Create Date: 2026-06-18

Additive + idempotent. Adds ``reaction_safety_screenings`` (a deterministic RDKit-SMARTS
energetic/reactive-group screen retained with its human-in-the-loop review state, per
reaction project). No changes to existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026_reaction_safety_screenings"
down_revision = "0025_reaction_plate_designs"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_safety_screenings"):
        op.create_table(
            "reaction_safety_screenings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "overall_risk", sa.String(length=16), nullable=False, server_default="unknown"
            ),
            sa.Column(
                "requires_expert_review",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "review_status", sa.String(length=16), nullable=False, server_default="pending"
            ),
            sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_safety_screenings_reaction_project_id",
            "reaction_safety_screenings",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_safety_screenings_project_created",
            "reaction_safety_screenings",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_safety_screenings"):
        op.drop_table("reaction_safety_screenings")
