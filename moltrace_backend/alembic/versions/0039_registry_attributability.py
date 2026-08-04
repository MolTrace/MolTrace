"""Registry attributability: created_by_user_id on the three unattributed tables

Revision ID: 0039_registry_attributability
Revises: 0038_subject_addressed_reviewers
Create Date: 2026-08-04

Additive. ``compound_entities``, ``compound_batches`` and ``controlled_records``
recorded no creator at all -- not created_by_user_id, not tenant_id, nothing.

Two separate problems follow from that, and the column is required for the first
regardless of what is decided about the second:

1. ALCOA+ attributability. The "A" in ALCOA+ is Attributable. A GxP-facing
   compound registry that cannot say who registered a record does not meet that
   bar whatever its sharing model is. ``controlled_records`` already recorded
   ``deleted_by``, so it could say who removed a record but not who created one.

2. Authorization. With no owner column there was nothing to compare a caller
   against, so ``PATCH /compound-registry/compounds/{id}`` accepted an edit from
   anyone -- verified against a running server with auth enforced: a
   second user renamed another user's compound and received 200.

Nullable on purpose. Rows created before this migration have no recorded creator,
and inventing one would be worse than admitting the gap: a backfill to an
arbitrary user would assert an attribution that never happened, in exactly the
records where attribution is the point. NULL therefore means "created before
attribution existed" and is handled explicitly by the read and write paths
(legacy rows stay readable; they are not editable by a non-admin, because there
is no owner to check against).

Deliberately NOT tenant-scoped. There is no server-derived tenant on a request
today -- AccessContext carries none, ``organizations`` has no link to ``tenants``,
and ``tenants`` is empty -- so a tenant column here would be an unenforceable
claim. Per-user is the only axis that can actually be checked. Widening this to
an organisation later is a read-model change on top of this column; the reverse,
recovering who created a row that was never attributed, is impossible.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0039_registry_attributability"
down_revision = "0038_subject_addressed_reviewers"
branch_labels = None
depends_on = None

_TABLES = ("compound_entities", "compound_batches", "controlled_records")
_COLUMN = "created_by_user_id"


def _index_name(table: str) -> str:
    return f"ix_{table}_created_by"


def _columns(bind, table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, index: str) -> bool:
    return index in {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    present = _tables(bind)
    for table in _TABLES:
        if table not in present:
            continue
        if _COLUMN not in _columns(bind, table):
            op.add_column(table, sa.Column(_COLUMN, sa.Integer(), nullable=True))
        index = _index_name(table)
        if not _has_index(bind, table, index):
            op.create_index(index, table, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    present = _tables(bind)
    for table in _TABLES:
        if table not in present:
            continue
        index = _index_name(table)
        if _has_index(bind, table, index):
            op.drop_index(index, table_name=table)
        if _COLUMN in _columns(bind, table):
            op.drop_column(table, _COLUMN)
