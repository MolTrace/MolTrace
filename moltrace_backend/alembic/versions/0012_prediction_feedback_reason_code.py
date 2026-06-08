"""prediction_feedback reason_code column for the structured feedback taxonomy

Revision ID: 0012_prediction_feedback_reason_code
Revises: 0011_user_gsd_graduated_at
Create Date: 2026-06-07

Adds a nullable ``reason_code`` column to the ``prediction_feedback`` table.
``None`` (default) means the reviewer left a thumbs verdict (and/or free-text)
without picking a structured reason; a value is one of the closed taxonomy
shared with ``moltrace.spectroscopy.feedback.capture.ReasonCode`` and the
``PredictionFeedbackReason`` API literal (wrong_shift, wrong_multiplicity,
wrong_structure, missed_impurity, wrong_integration, calibration_off, other).

The reason is orthogonal to ``feedback_type`` (the thumbs verdict): a reviewer
can reject *and* tag *why*, so override analytics can roll up exactly where the
model is weakest. Nullable + additive, so existing feedback rows are untouched.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_prediction_feedback_reason_code"
down_revision = "0011_user_gsd_graduated_at"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if _column_exists("prediction_feedback", "reason_code"):
        return
    op.add_column(
        "prediction_feedback",
        sa.Column("reason_code", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    if _column_exists("prediction_feedback", "reason_code"):
        op.drop_column("prediction_feedback", "reason_code")
