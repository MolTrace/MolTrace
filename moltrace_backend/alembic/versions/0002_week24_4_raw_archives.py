"""week24.4 raw archive vault records

Revision ID: 0002_week24_4_raw_archives
Revises: 0001_week8_baseline
Create Date: 2026-04-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_week24_4_raw_archives"
down_revision = "0001_week8_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_archives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("vendor_detected", sa.String(length=100), nullable=False),
        sa.Column("dataset_root", sa.String(length=500), nullable=True),
        sa.Column("required_files_present", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("files_found_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("acquisition_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("sha256", name="uq_raw_archives_sha256"),
    )
    op.create_index("ix_raw_archives_sha256", "raw_archives", ["sha256"], unique=False)
    op.create_index("ix_raw_archives_user_id", "raw_archives", ["user_id"], unique=False)
    op.create_index("ix_raw_archives_vendor_detected", "raw_archives", ["vendor_detected"], unique=False)
    op.create_index("ix_raw_archives_user_created", "raw_archives", ["user_id", "created_at"], unique=False)
    op.create_index(
        "ix_raw_archives_vendor_created",
        "raw_archives",
        ["vendor_detected", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_raw_archives_vendor_created", table_name="raw_archives")
    op.drop_index("ix_raw_archives_user_created", table_name="raw_archives")
    op.drop_index("ix_raw_archives_vendor_detected", table_name="raw_archives")
    op.drop_index("ix_raw_archives_user_id", table_name="raw_archives")
    op.drop_index("ix_raw_archives_sha256", table_name="raw_archives")
    op.drop_table("raw_archives")
