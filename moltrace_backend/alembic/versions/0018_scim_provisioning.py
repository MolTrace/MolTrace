"""SCIM 2.0 provisioning: per-connection bearer tokens + per-connection user mappings (Prompt 2)

Revision ID: 0018_scim_provisioning
Revises: 0017_sso_connections
Create Date: 2026-06-13

Two new tables, additive and idempotent (guarded by table existence):
- ``scim_tokens`` — a long-lived SCIM bearer per SSO connection, stored as a SHA-256 digest only;
  a Postgres partial-unique index enforces at most one *live* (un-revoked) token per connection.
- ``scim_users`` — the per-connection SCIM resource for a provisioned user; its ``id`` is the SCIM
  resource id (the tenant-isolation boundary), mapping to the global ``users.id``.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018_scim_provisioning"
down_revision = "0017_sso_connections"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("scim_tokens"):
        op.create_table(
            "scim_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("sso_connections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_prefix", sa.String(length=16), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_scim_tokens_connection_id", "scim_tokens", ["connection_id"])
        op.create_index("ix_scim_tokens_token_prefix", "scim_tokens", ["token_prefix"])
        op.create_index("ix_scim_tokens_token_hash", "scim_tokens", ["token_hash"], unique=True)
        # At most one live token per connection (Postgres partial-unique; also enforced in code).
        op.create_index(
            "ix_scim_tokens_live",
            "scim_tokens",
            ["connection_id"],
            unique=True,
            postgresql_where=sa.text("revoked_at IS NULL"),
            sqlite_where=sa.text("revoked_at IS NULL"),
        )

    if not _table_exists("scim_users"):
        op.create_table(
            "scim_users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("sso_connections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("external_id", sa.String(length=255), nullable=True),
            sa.Column("scim_user_name", sa.String(length=255), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("raw_attributes_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deprovisioned_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("connection_id", "external_id", name="uq_scim_users_conn_external"),
            sa.UniqueConstraint(
                "connection_id", "scim_user_name", name="uq_scim_users_conn_username"
            ),
            sa.UniqueConstraint("connection_id", "user_id", name="uq_scim_users_conn_user"),
        )
        op.create_index("ix_scim_users_connection_id", "scim_users", ["connection_id"])
        op.create_index("ix_scim_users_user", "scim_users", ["user_id"])


def downgrade() -> None:
    if _table_exists("scim_users"):
        op.drop_table("scim_users")
    if _table_exists("scim_tokens"):
        op.drop_table("scim_tokens")
