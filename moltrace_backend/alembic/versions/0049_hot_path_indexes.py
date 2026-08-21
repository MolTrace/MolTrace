"""Composite indexes for two hot lookups that had none.

``audit_events`` indexed ``entity_id`` alone and ``entity_type`` not at all, so
every "what happened to this entity?" query — the project dashboard, the sample
timeline, the evidence panels — matched on the id and then filtered the type row
by row. ``analyses.sample_id`` carried no index at all, so sample detail,
timeline and reports scanned a tenant's whole analysis history.

Both are pure additions: no column, constraint or data change.

GUARDED, following 0024's pattern and for the same reason: neither
``audit_events`` nor ``analyses`` is created by any migration — like ~197 of the
271 mapped tables, they come from the ORM via ``create_all`` (see
deploy/README.md, which records the same hazard for ``dataset_versions`` in
0007). Against a genuinely empty database ``alembic upgrade head`` therefore
reaches this revision before those tables exist, and an unguarded
``create_index`` would abort the migrate job. On that path the indexes are
created by ``create_all`` anyway, since they are declared in ``orm.py``.

Revision ID: 0049_hot_path_indexes
Revises: 0048_raw_fid_report_cache
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0049_hot_path_indexes"
down_revision = "0048_raw_fid_report_cache"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"]),
    ("ix_analyses_user_sample", "analyses", ["user_id", "sample_id"]),
)


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(ix["name"] == index_name for ix in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    for index_name, table_name, columns in _INDEXES:
        # Absent table: create_all builds it WITH these indexes (they are on the
        # ORM model), so there is nothing to do here.
        if not _table_exists(table_name):
            continue
        if _index_exists(table_name, index_name):
            continue
        op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    for index_name, table_name, _columns in reversed(_INDEXES):
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
