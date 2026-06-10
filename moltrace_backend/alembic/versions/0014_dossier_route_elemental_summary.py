"""dossier administration route + batch elemental_summary_json (ICH Q3D)

Revision ID: 0014_dossier_route_elemental_summary
Revises: 0013_dossier_max_daily_dose
Create Date: 2026-06-09

Two additive columns that complete the dossier's product context + the Q3D
elemental-impurity assessment:

- ``regulatory_dossiers.route`` (nullable) — the product administration route
  (``oral`` / ``parenteral`` / ``inhalation`` / ``cutaneous``). ICH Q3D PDEs and
  dose-scaled Q3C limits are route-dependent; sourcing the route from the dossier
  (alongside ``max_daily_dose_g`` / ``substance_type`` from 0013) keeps every
  assessment under the dossier consistent.
- ``batch_regulatory_assessments.elemental_summary_json`` (default ``{}``) — the
  storage slot for the new ``POST …/elemental-impurity-assessment`` (ICH Q3D),
  mirroring ``residual_solvent_summary_json`` / ``nitrosamine_summary_json``.

Both are backward-compatible (nullable route; server-default ``{}`` summary), so the
change auto-runs on deploy with no data backfill.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_dossier_route_elemental_summary"
down_revision = "0013_dossier_max_daily_dose"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("regulatory_dossiers", "route"):
        op.add_column(
            "regulatory_dossiers",
            sa.Column("route", sa.String(length=32), nullable=True),
        )
    if not _column_exists("batch_regulatory_assessments", "elemental_summary_json"):
        op.add_column(
            "batch_regulatory_assessments",
            sa.Column(
                "elemental_summary_json", sa.Text(), nullable=False, server_default="{}"
            ),
        )


def downgrade() -> None:
    if _column_exists("batch_regulatory_assessments", "elemental_summary_json"):
        op.drop_column("batch_regulatory_assessments", "elemental_summary_json")
    if _column_exists("regulatory_dossiers", "route"):
        op.drop_column("regulatory_dossiers", "route")
