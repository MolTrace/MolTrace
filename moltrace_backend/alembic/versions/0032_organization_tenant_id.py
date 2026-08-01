"""organizations.tenant_id — bind an org to a SaaS tenant (module-entitlement enforcement)

Revision ID: 0032_organization_tenant_id
Revises: 0031_reaction_phase_c_wiring
Create Date: 2026-07-31

Adds the single edge that lets the server resolve a caller's tenant from their organization
membership, instead of trusting a self-asserted ``x-tenant-id`` header. ``OrganizationORM``
gained a nullable ``tenant_id`` (FK ``tenants.id``, ``ondelete=SET NULL``) plus its index.

No backfill: every existing organization stays ``tenant_id = NULL`` (unbound). An unbound org
resolves to no tenant, so no module entitlement applies and access stays open — allow-by-default.
Enforcement becomes live for a tenant only once an operator links its org(s) via the
``PUT /tenants/{tenant_id}/organizations/{organization_id}`` link endpoint and records an
explicit ``enabled=false`` entitlement. So this migration cannot lock out any existing tenant.

All steps are guarded (table-exists / column-exists / index-exists), so the migration is safe on
fresh, partially-migrated, and already-current databases alike — the same convention as 0022/0023.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0032_organization_tenant_id"
down_revision = "0031_reaction_phase_c_wiring"
branch_labels = None
depends_on = None

_TABLE = "organizations"
_TENANT_IX = "ix_organizations_tenant_id"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    # Fresh database: organizations is built later by create_all (with tenant_id and its index),
    # so there is nothing to alter here.
    if not _table_exists(_TABLE):
        return

    if not _column_exists(_TABLE, "tenant_id"):
        if op.get_bind().dialect.name == "sqlite":
            # SQLite cannot ALTER-ADD a column carrying a FK constraint. Dev SQLite is normally
            # built by create_all + _ensure_sqlite_schema (which adds a plain tenant_id) rather
            # than this migration, so add the bare column here to keep the migration runnable and
            # isolation-testable on SQLite. Postgres (the production target) gets the real FK below.
            op.add_column(_TABLE, sa.Column("tenant_id", sa.Integer(), nullable=True))
        else:
            op.add_column(
                _TABLE,
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
    if not _index_exists(_TABLE, _TENANT_IX):
        op.create_index(_TENANT_IX, _TABLE, ["tenant_id"])


def downgrade() -> None:
    if _index_exists(_TABLE, _TENANT_IX):
        op.drop_index(_TENANT_IX, table_name=_TABLE)
    if _column_exists(_TABLE, "tenant_id"):
        op.drop_column(_TABLE, "tenant_id")
