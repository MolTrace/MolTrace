"""regulatory_ai_decisions table (EU GMP Draft Annex 22 AI-decision records)

Revision ID: 0016_regulatory_ai_decisions
Revises: 0015_dossier_created_by_user_id
Create Date: 2026-06-12

Adds the append-only, hash-chained AI-decision log per dossier (Prompt 12 wiring). Backs
``moltrace.regulatory.compliance.AIDecisionRecord``, surfaced via
``/regulatory/dossiers/{id}/ai-decisions``. Additive + idempotent (creates the table only
when absent), so it auto-runs on deploy.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_regulatory_ai_decisions"
down_revision = "0015_dossier_created_by_user_id"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if _table_exists("regulatory_ai_decisions"):
        return
    op.create_table(
        "regulatory_ai_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dossier_id",
            sa.Integer(),
            sa.ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_hash", sa.String(length=96), nullable=False),
        sa.Column("previous_entry_hash", sa.String(length=96), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("decision_type", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=240), nullable=False),
        sa.Column("model_version", sa.String(length=512), nullable=False),
        sa.Column("input_smiles", sa.Text(), nullable=True),
        sa.Column("input_data_hash", sa.String(length=96), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "feature_attribution_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("regulatory_basis", sa.String(length=512), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column(
            "hitl_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("hitl_reviewer_id", sa.String(length=128), nullable=True),
        sa.Column("hitl_review_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hitl_approved", sa.Boolean(), nullable=True),
        sa.Column("reviews_entry_hash", sa.String(length=96), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_regulatory_ai_decisions_dossier", "regulatory_ai_decisions", ["dossier_id", "id"]
    )
    op.create_index(
        "ix_regulatory_ai_decisions_entry_hash", "regulatory_ai_decisions", ["entry_hash"]
    )
    op.create_index(
        "ix_regulatory_ai_decisions_reviews", "regulatory_ai_decisions", ["reviews_entry_hash"]
    )


def downgrade() -> None:
    if _table_exists("regulatory_ai_decisions"):
        op.drop_table("regulatory_ai_decisions")
