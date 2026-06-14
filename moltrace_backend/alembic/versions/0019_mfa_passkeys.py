"""MFA & passkeys: TOTP + WebAuthn credentials, recovery codes, per-org policy, step-up (Prompt 3)

Revision ID: 0019_mfa_passkeys
Revises: 0018_scim_provisioning
Create Date: 2026-06-14

Additive and idempotent. Adds six tables and five columns on ``session_tokens`` (MFA/step-up
state). Column adds are guarded by column existence; table creates by table existence.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019_mfa_passkeys"
down_revision = "0018_scim_provisioning"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # --- session_tokens: MFA + step-up columns ---
    for col in (
        sa.Column("amr", sa.String(length=64), nullable=True),
        sa.Column("mfa_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stepped_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("step_up_factor", sa.String(length=16), nullable=True),
        sa.Column("step_up_aal", sa.String(length=8), nullable=True),
    ):
        if not _column_exists("session_tokens", col.name):
            op.add_column("session_tokens", col)

    if not _table_exists("mfa_totp_credentials"):
        op.create_table(
            "mfa_totp_credentials",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("secret_encrypted", sa.Text(), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_step", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_mfa_totp_credentials_user_id", "mfa_totp_credentials", ["user_id"])
        op.create_index(
            "ix_mfa_totp_confirmed",
            "mfa_totp_credentials",
            ["user_id"],
            unique=True,
            postgresql_where=sa.text("confirmed_at IS NOT NULL"),
            sqlite_where=sa.text("confirmed_at IS NOT NULL"),
        )

    if not _table_exists("mfa_webauthn_credentials"):
        op.create_table(
            "mfa_webauthn_credentials",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("credential_id", sa.LargeBinary(), nullable=False),
            sa.Column("public_key", sa.LargeBinary(), nullable=False),
            sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("transports_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("aaguid", sa.String(length=36), nullable=True),
            sa.Column("device_type", sa.String(length=16), nullable=True),
            sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("nickname", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_mfa_webauthn_cred_user", "mfa_webauthn_credentials", ["user_id"])
        op.create_index(
            "ix_mfa_webauthn_credentials_credential_id",
            "mfa_webauthn_credentials",
            ["credential_id"],
            unique=True,
        )

    if not _table_exists("mfa_webauthn_challenges"):
        op.create_table(
            "mfa_webauthn_challenges",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("purpose", sa.String(length=24), nullable=False),
            sa.Column("challenge", sa.LargeBinary(), nullable=False),
            sa.Column("rp_id", sa.String(length=255), nullable=False),
            sa.Column("webauthn_user_handle", sa.LargeBinary(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_mfa_webauthn_chal_user", "mfa_webauthn_challenges", ["user_id"])
        op.create_index("ix_mfa_webauthn_chal_expires", "mfa_webauthn_challenges", ["expires_at"])

    if not _table_exists("mfa_recovery_codes"):
        op.create_table(
            "mfa_recovery_codes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_mfa_recovery_user_used", "mfa_recovery_codes", ["user_id", "used_at"])

    if not _table_exists("mfa_login_challenges"):
        op.create_table(
            "mfa_login_challenges",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("organization_id", sa.Integer(), nullable=True),
            sa.Column("purpose", sa.String(length=24), nullable=False, server_default="login"),
            sa.Column("factors_offered_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("webauthn_challenge", sa.LargeBinary(), nullable=True),
            sa.Column("sso_flow_id", sa.String(length=128), nullable=True),
            sa.Column("amr_from_sso", sa.String(length=64), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_mfa_login_chal_token", "mfa_login_challenges", ["token_hash"], unique=True
        )
        op.create_index("ix_mfa_login_chal_user", "mfa_login_challenges", ["user_id"])
        op.create_index("ix_mfa_login_chal_expires", "mfa_login_challenges", ["expires_at"])

    if not _table_exists("mfa_policies"):
        op.create_table(
            "mfa_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("mfa_required_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "allowed_factors_json",
                sa.Text(),
                nullable=False,
                server_default='["webauthn", "totp"]',
            ),
            sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("enforce_for_sso", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "require_step_up_for_signing",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "updated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", name="uq_mfa_policies_org"),
        )
        op.create_index("ix_mfa_policies_organization_id", "mfa_policies", ["organization_id"])


def downgrade() -> None:
    for table in (
        "mfa_policies",
        "mfa_login_challenges",
        "mfa_recovery_codes",
        "mfa_webauthn_challenges",
        "mfa_webauthn_credentials",
        "mfa_totp_credentials",
    ):
        if _table_exists(table):
            op.drop_table(table)
    for col in ("step_up_aal", "step_up_factor", "stepped_up_at", "mfa_at", "amr"):
        if _column_exists("session_tokens", col):
            op.drop_column("session_tokens", col)
