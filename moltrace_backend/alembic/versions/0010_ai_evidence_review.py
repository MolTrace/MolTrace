"""minimal ai evidence review queue

Revision ID: 0010_ai_evidence_review
Revises: 0009_phase61_mobile_pwa
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_ai_evidence_review"
down_revision = "0009_phase61_mobile_pwa"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if _table_exists("ai_evidence_items"):
        return
    op.create_table(
        "ai_evidence_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_evidence_items_tenant_id", "ai_evidence_items", ["tenant_id"])
    op.create_index("ix_ai_evidence_items_module", "ai_evidence_items", ["module"])
    op.create_index("ix_ai_evidence_items_status", "ai_evidence_items", ["status"])
    op.create_index("ix_ai_evidence_items_entity_id", "ai_evidence_items", ["entity_id"])
    op.create_index("ix_ai_evidence_items_reviewer_id", "ai_evidence_items", ["reviewer_id"])
    op.create_index(
        "ix_ai_evidence_items_module_status",
        "ai_evidence_items",
        ["module", "status"],
    )
    op.create_index(
        "ix_ai_evidence_items_entity",
        "ai_evidence_items",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_ai_evidence_items_tenant_status",
        "ai_evidence_items",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    if _table_exists("ai_evidence_items"):
        op.drop_table("ai_evidence_items")
