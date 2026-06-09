"""dossier max_daily_dose_g + substance_type for dose-driven impurity limits

Revision ID: 0013_dossier_max_daily_dose
Revises: 0012_prediction_feedback_reason_code
Create Date: 2026-06-09

Adds two nullable product-context columns to ``regulatory_dossiers``:
``max_daily_dose_g`` (g/day) and ``substance_type`` (``drug_substance`` /
``drug_product``). A dossier is one drug product with one max daily dose, and
every impurity assessment under it is dose-driven (ICH Q3A/B reporting/
identification/qualification thresholds; dose-scaled Q3C/Q3D limits). Sourcing
the dose from the dossier — instead of re-supplying it on each assessment call —
keeps all of a dossier's impurity work dose-consistent. Both columns are nullable
(``None`` reproduces the prior, dose-unaware behaviour), so the change is
backward-compatible and auto-runs on deploy.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_dossier_max_daily_dose"
down_revision = "0012_prediction_feedback_reason_code"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("regulatory_dossiers", "max_daily_dose_g"):
        op.add_column(
            "regulatory_dossiers",
            sa.Column("max_daily_dose_g", sa.Float(), nullable=True),
        )
    if not _column_exists("regulatory_dossiers", "substance_type"):
        op.add_column(
            "regulatory_dossiers",
            sa.Column("substance_type", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("regulatory_dossiers", "substance_type"):
        op.drop_column("regulatory_dossiers", "substance_type")
    if _column_exists("regulatory_dossiers", "max_daily_dose_g"):
        op.drop_column("regulatory_dossiers", "max_daily_dose_g")
