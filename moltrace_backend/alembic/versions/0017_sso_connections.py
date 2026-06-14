"""SSO: per-organization OIDC connections + ephemeral login flows (Prompt 1)

Revision ID: 0017_sso_connections
Revises: 0016_regulatory_ai_decisions
Create Date: 2026-06-13

Two new tables, additive and idempotent (guarded by table existence):
- ``sso_connections`` — a per-organization OIDC IdP config; the client secret is stored
  AES-256-GCM encrypted (``client_secret_encrypted``).
- ``sso_login_flows`` — short-lived PKCE/nonce state for one login, then a one-time
  exchange code; no bearer token is persisted.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017_sso_connections"
down_revision = "0016_regulatory_ai_decisions"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("sso_connections"):
        op.create_table(
            "sso_connections",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("protocol", sa.String(length=16), nullable=False, server_default="oidc"),
            sa.Column("issuer", sa.String(length=500), nullable=False),
            sa.Column("client_id", sa.String(length=500), nullable=False),
            sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
            sa.Column("email_domains_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("enforce_sso", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index("ix_sso_connections_org", "sso_connections", ["organization_id"])
        op.create_index("ix_sso_connections_slug", "sso_connections", ["slug"], unique=True)

    if not _table_exists("sso_login_flows"):
        op.create_table(
            "sso_login_flows",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("sso_connections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("state", sa.String(length=128), nullable=False),
            sa.Column("nonce", sa.String(length=128), nullable=False),
            sa.Column("code_verifier", sa.String(length=128), nullable=False),
            sa.Column("redirect_uri", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("exchange_code", sa.String(length=128), nullable=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_sso_login_flows_connection", "sso_login_flows", ["connection_id"])
        op.create_index("ix_sso_login_flows_state", "sso_login_flows", ["state"], unique=True)
        op.create_index("ix_sso_login_flows_exchange", "sso_login_flows", ["exchange_code"])
        op.create_index("ix_sso_login_flows_expires", "sso_login_flows", ["expires_at"])


def downgrade() -> None:
    if _table_exists("sso_login_flows"):
        op.drop_table("sso_login_flows")
    if _table_exists("sso_connections"):
        op.drop_table("sso_connections")
