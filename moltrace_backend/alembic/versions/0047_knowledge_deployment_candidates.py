"""Close the conveyor: dataset version -> deployment candidate -> gate -> canary

Revision ID: 0047_knowledge_deployment_candidates
Revises: 0046_dataset_version_approvals
Create Date: 2026-08-08

Additive. New ``knowledge_deployment_candidates`` table.

The gap this closes: the chain ran candidates -> dataset version -> **nothing**.
There was no object representing "this dataset version, trained, proposed for
deployment", no canary state, and no promotion gate, so "approved for training"
and "serving traffic" were the same word for two unrelated states.

This is a *different* conveyor from the Repho benchmark gate (``reaction_eval.gate``)
and from the ``/ml/deployment-candidates`` registry flow; neither covered the
knowledge corpus. It does not duplicate their dominance rule -- the gate calls
``reaction_feedback.evaluate_ab_promotion``, the same fail-closed rule, so a
missing or non-finite measure blocks rather than being skipped.

``blocking_metric_name`` is stored because the hard dimension differs by model:
the underlying rule names it safety-flag recall, and for an extraction model it may
be citation-support recall. Recording which measure played the role keeps the audit
honest without inventing a second rule to apply to it.

Each step is gated on the one before: a candidate requires a dataset version two
people approved, a canary requires a passed gate, and promotion requires a canary.
A canary with no gate behind it would be a deployment mechanism wearing a
governance label.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0047_knowledge_deployment_candidates"
down_revision = "0046_dataset_version_approvals"
branch_labels = None
depends_on = None

_TABLE = "knowledge_deployment_candidates"
_PARENT = "dataset_versions"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if _PARENT not in tables or _TABLE in tables:
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_version_id",
            sa.Integer(),
            sa.ForeignKey(f"{_PARENT}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_artifact_id", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("incumbent_metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metric_directions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("blocking_metric_name", sa.String(length=120), nullable=True),
        sa.Column("blocking_metric_value", sa.Float(), nullable=True),
        sa.Column("incumbent_blocking_metric_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("gate_verdict_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("canary_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index(f"ix_{_TABLE}_dataset_version_id", _TABLE, ["dataset_version_id"])
    op.create_index(f"ix_{_TABLE}_status", _TABLE, ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    op.drop_index(f"ix_{_TABLE}_status", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_dataset_version_id", table_name=_TABLE)
    op.drop_table(_TABLE)
