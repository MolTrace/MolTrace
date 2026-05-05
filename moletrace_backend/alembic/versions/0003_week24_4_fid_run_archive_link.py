"""week24.4 fid run archive link and recipe fields

Revision ID: 0003_week24_4_fid_run_archive_link
Revises: 0002_week24_4_raw_archives
Create Date: 2026-04-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_week24_4_fid_run_archive_link"
down_revision = "0002_week24_4_raw_archives"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    if not _table_exists("fid_runs"):
        return
    bind = op.get_bind()
    columns = _column_names("fid_runs")
    if "raw_archive_id" not in columns:
        op.add_column("fid_runs", sa.Column("raw_archive_id", sa.Integer(), nullable=True))
        op.create_index("ix_fid_runs_raw_archive_id", "fid_runs", ["raw_archive_id"], unique=False)
        if bind.dialect.name != "sqlite" and _table_exists("raw_archives"):
            op.create_foreign_key(
                "fk_fid_runs_raw_archive_id_raw_archives",
                "fid_runs",
                "raw_archives",
                ["raw_archive_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if "raw_sha256" not in columns:
        op.add_column("fid_runs", sa.Column("raw_sha256", sa.String(length=64), nullable=True))
        op.create_index("ix_fid_runs_raw_sha256", "fid_runs", ["raw_sha256"], unique=False)
    if "processing_recipe_json" not in columns:
        op.add_column("fid_runs", sa.Column("processing_recipe_json", sa.Text(), nullable=True))
    if "derived_spectrum_metadata_json" not in columns:
        op.add_column("fid_runs", sa.Column("derived_spectrum_metadata_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _table_exists("fid_runs"):
        return
    bind = op.get_bind()
    columns = _column_names("fid_runs")
    if "derived_spectrum_metadata_json" in columns:
        op.drop_column("fid_runs", "derived_spectrum_metadata_json")
    if "processing_recipe_json" in columns:
        op.drop_column("fid_runs", "processing_recipe_json")
    if "raw_sha256" in columns:
        op.drop_index("ix_fid_runs_raw_sha256", table_name="fid_runs")
        op.drop_column("fid_runs", "raw_sha256")
    if "raw_archive_id" in columns:
        if bind.dialect.name != "sqlite":
            try:
                op.drop_constraint("fk_fid_runs_raw_archive_id_raw_archives", "fid_runs", type_="foreignkey")
            except Exception:
                pass
        op.drop_index("ix_fid_runs_raw_archive_id", table_name="fid_runs")
        op.drop_column("fid_runs", "raw_archive_id")
