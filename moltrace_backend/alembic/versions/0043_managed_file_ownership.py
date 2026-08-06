"""Managed-file and artifact attributability: created_by_user_id

Revision ID: 0043_managed_file_ownership
Revises: 0042_spectrum_series
Create Date: 2026-08-06

Additive, and urgent. ``managed_file_records`` and ``artifact_records`` record
no owner at all, so there is nothing to compare a caller against. Probed against
a running server with auth enforced: a second, unrelated account read another
user's uploaded file record (200), **downloaded its bytes** (200), and saw it in
the file listing.

For a product whose users upload proprietary FIDs, that is one customer reading
another customer's raw spectral data -- the most confidential thing the system
holds.

This migration only adds the columns. Stamping on create and scoping on read
follow in the same change where the routes are wired; the column has to exist
first, and it is landed on its own because **attribution is one-directional**.
Every file uploaded before the column exists becomes a row whose owner can never
be recovered, so the cost of waiting is permanent and grows by the hour. The
same argument justified 0039 for the compound registry.

Nullable on purpose, and NOT backfilled. A row created before attribution
existed has no provable owner, and inventing one would assert something that
never happened in precisely the records where provenance is the point. NULL
means "predates attribution" and is refused to non-admins by the read path, on
the reasoning that "nobody is recorded as responsible" must not be read as
"anyone may download it".

Deliberately per-user, not per-tenant: there is no server-derived tenant on a
request today (``AccessContext`` carries none, ``organizations`` has no link to
``tenants``, ``tenants`` is empty), so a tenant column here would be an
unenforceable claim. See 0039 for the same reasoning.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0043_managed_file_ownership"
down_revision = "0042_spectrum_series"
branch_labels = None
depends_on = None

_TABLES = ("managed_file_records", "artifact_records")
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
