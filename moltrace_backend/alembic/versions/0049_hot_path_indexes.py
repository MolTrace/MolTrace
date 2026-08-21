"""Composite indexes for two hot lookups that had none.

``audit_events`` indexed ``entity_id`` alone and ``entity_type`` not at all, so
every "what happened to this entity?" query — the project dashboard, the sample
timeline, the evidence panels — matched on the id and then filtered the type row
by row. ``analyses.sample_id`` carried no index at all, so sample detail,
timeline and reports scanned a tenant's whole analysis history.

Both are pure additions: no column, constraint or data change, so there is
nothing to undo beyond dropping them.

Revision ID: 0049_hot_path_indexes
Revises: 0048_raw_fid_report_cache
"""

from __future__ import annotations

from alembic import op

revision = "0049_hot_path_indexes"
down_revision = "0048_raw_fid_report_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_analyses_user_sample",
        "analyses",
        ["user_id", "sample_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_user_sample", table_name="analyses")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
