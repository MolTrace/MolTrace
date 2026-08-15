"""Persist the raw-FID derived-report cache across instances and restarts

Revision ID: 0048_raw_fid_report_cache
Revises: 0047_knowledge_deployment_candidates
Create Date: 2026-08-14

Additive. New ``raw_fid_report_cache`` table.

The in-process report cache (``fid.py:_RAW_FID_PROCESS_CACHE``) turned a
measured 6.8 s cold FID processing run into 0.017 s — but it dies on every
Cloud Run scale-to-zero and misses across autoscaled instances, so in
production the 400x speedup was a process accident, not a property of the
system. This table is the L2: the derived ``FIDPreviewReport`` JSON keyed by
the same content-addressed processing identity the in-process cache uses
(archive sha256 + settings + nucleus + solvent + reference text + expected H
+ compound class, hashed). Rows are pure derived data — the immutable archive
lives in the raw vault — so deleting them only ever costs recompute time.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0048_raw_fid_report_cache"
down_revision = "0047_knowledge_deployment_candidates"
branch_labels = None
depends_on = None

_TABLE = "raw_fid_report_cache"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in set(inspector.get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("cache_version", sa.String(length=64), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=True),
        sa.Column("report_json", sa.Text(), nullable=False),
    )
    op.create_index(f"ix_{_TABLE}_cache_key", _TABLE, ["cache_key"], unique=True)
    op.create_index(f"ix_{_TABLE}_cache_version", _TABLE, ["cache_version"])
    op.create_index(f"ix_{_TABLE}_raw_sha256", _TABLE, ["raw_sha256"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    op.drop_index(f"ix_{_TABLE}_raw_sha256", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_cache_version", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_cache_key", table_name=_TABLE)
    op.drop_table(_TABLE)
