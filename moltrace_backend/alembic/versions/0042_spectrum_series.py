"""Spectrum series: the ordered set of spectra a rate constant is fitted over

Revision ID: 0042_spectrum_series
Revises: 0041_spectral_impurity_observations
Create Date: 2026-08-06

Additive + idempotent. Adds ``spectrum_series`` and ``spectrum_series_points``: an ordered set of
spectra of one reaction, and the timed observations read from them.

Scoped by ``user_id``, matching ``spectral_impurity_observations``. Points reference analyses, and
``analyses`` carries no organization column, so a series must not be reachable through a wider
lattice than the spectra it is assembled from.

``observed_value`` is recorded rather than derived from the stored report on purpose: re-picking
the tracked signal out of every spectrum would inherit the open peak-integration accuracy work
invisibly, and a rate constant is only as good as the integrals under it. ``analysis_id`` is
SET NULL so a point stays evidence of what was observed even if its analysis is removed, while the
series parent is CASCADE. No changes to existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0042_spectrum_series"
down_revision = "0041_spectral_impurity_observations"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("spectrum_series"):
        op.create_table(
            "spectrum_series",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
            sa.Column(
                "tracked_quantity", sa.String(length=200), nullable=False, server_default=""
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_spectrum_series_user_created", "spectrum_series", ["user_id", "created_at"]
        )

    if not _table_exists("spectrum_series_points"):
        op.create_table(
            "spectrum_series_points",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "series_id",
                sa.Integer(),
                sa.ForeignKey("spectrum_series.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "analysis_id",
                sa.Integer(),
                sa.ForeignKey("analyses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "elapsed_seconds", sa.Float(), nullable=False, server_default="0.0"
            ),
            sa.Column("observed_value", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_spectrum_series_points_series_elapsed",
            "spectrum_series_points",
            ["series_id", "elapsed_seconds"],
        )
        op.create_index(
            "ix_spectrum_series_points_series_id", "spectrum_series_points", ["series_id"]
        )
        op.create_index(
            "ix_spectrum_series_points_analysis_id", "spectrum_series_points", ["analysis_id"]
        )


def downgrade() -> None:
    if _table_exists("spectrum_series_points"):
        op.drop_index(
            "ix_spectrum_series_points_analysis_id", table_name="spectrum_series_points"
        )
        op.drop_index(
            "ix_spectrum_series_points_series_id", table_name="spectrum_series_points"
        )
        op.drop_index(
            "ix_spectrum_series_points_series_elapsed", table_name="spectrum_series_points"
        )
        op.drop_table("spectrum_series_points")
    if _table_exists("spectrum_series"):
        op.drop_index("ix_spectrum_series_user_created", table_name="spectrum_series")
        op.drop_table("spectrum_series")
