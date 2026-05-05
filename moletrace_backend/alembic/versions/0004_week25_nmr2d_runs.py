"""week25 guarded 2d nmr run records

Revision ID: 0004_week25_nmr2d_runs
Revises: 0003_week24_4_fid_run_archive_link
Create Date: 2026-04-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_week25_nmr2d_runs"
down_revision = "0003_week24_4_fid_run_archive_link"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if _table_exists("nmr2d_runs"):
        return
    op.create_table(
        "nmr2d_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_id", sa.String(length=100), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("experiment_types_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("peak_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("peaks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_nmr2d_runs_user_id", "nmr2d_runs", ["user_id"], unique=False)
    op.create_index("ix_nmr2d_runs_analysis_id", "nmr2d_runs", ["analysis_id"], unique=False)
    op.create_index("ix_nmr2d_runs_user_created", "nmr2d_runs", ["user_id", "created_at"], unique=False)
    op.create_index("ix_nmr2d_runs_analysis_created", "nmr2d_runs", ["analysis_id", "created_at"], unique=False)
    op.create_index(
        "ix_nmr2d_runs_review_status_created",
        "nmr2d_runs",
        ["review_status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    if not _table_exists("nmr2d_runs"):
        return
    op.drop_index("ix_nmr2d_runs_review_status_created", table_name="nmr2d_runs")
    op.drop_index("ix_nmr2d_runs_analysis_created", table_name="nmr2d_runs")
    op.drop_index("ix_nmr2d_runs_user_created", table_name="nmr2d_runs")
    op.drop_index("ix_nmr2d_runs_analysis_id", table_name="nmr2d_runs")
    op.drop_index("ix_nmr2d_runs_user_id", table_name="nmr2d_runs")
    op.drop_table("nmr2d_runs")
