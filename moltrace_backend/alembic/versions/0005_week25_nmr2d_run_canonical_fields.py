"""week25 nmr2d canonical run fields

Revision ID: 0005_week25_nmr2d_run_canonical_fields
Revises: 0004_week25_nmr2d_runs
Create Date: 2026-04-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_week25_nmr2d_run_canonical_fields"
down_revision = "0004_week25_nmr2d_runs"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    if not _table_exists("nmr2d_runs"):
        return
    columns = _column_names("nmr2d_runs")
    indexes = _index_names("nmr2d_runs")
    if "sample_pk" not in columns:
        op.add_column("nmr2d_runs", sa.Column("sample_pk", sa.Integer(), nullable=True))
    if "filename" not in columns:
        op.add_column("nmr2d_runs", sa.Column("filename", sa.String(length=255), nullable=True))
    if "experiment_detected" not in columns:
        op.add_column("nmr2d_runs", sa.Column("experiment_detected", sa.String(length=32), nullable=True))
    if "evidence_score" not in columns:
        op.add_column("nmr2d_runs", sa.Column("evidence_score", sa.Float(), nullable=True))
    if "suspicious_peak_count" not in columns:
        op.add_column("nmr2d_runs", sa.Column("suspicious_peak_count", sa.Integer(), nullable=True))
    if "preview_json" not in columns:
        op.add_column("nmr2d_runs", sa.Column("preview_json", sa.Text(), nullable=True))
    if "result_json" not in columns:
        op.add_column("nmr2d_runs", sa.Column("result_json", sa.Text(), nullable=True))
    if "ix_nmr2d_runs_sample_pk_created" not in indexes:
        op.create_index(
            "ix_nmr2d_runs_sample_pk_created",
            "nmr2d_runs",
            ["sample_pk", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if not _table_exists("nmr2d_runs"):
        return
    columns = _column_names("nmr2d_runs")
    indexes = _index_names("nmr2d_runs")
    if "ix_nmr2d_runs_sample_pk_created" in indexes:
        op.drop_index("ix_nmr2d_runs_sample_pk_created", table_name="nmr2d_runs")
    for column in (
        "result_json",
        "preview_json",
        "suspicious_peak_count",
        "evidence_score",
        "experiment_detected",
        "filename",
        "sample_pk",
    ):
        if column in columns:
            op.drop_column("nmr2d_runs", column)
