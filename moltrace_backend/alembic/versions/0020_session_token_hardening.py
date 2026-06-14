"""Session & token hardening: refresh-token families + rotation (Security Prompt 4)

Revision ID: 0020_session_token_hardening
Revises: 0019_mfa_passkeys
Create Date: 2026-06-14

Additive + idempotent. Adds ``session_families`` and ``refresh_tokens`` (rotating single-use
refresh tokens with reuse detection) and two nullable columns on ``session_tokens`` linking an
access row to its family/refresh. Legacy access rows keep ``family_id IS NULL`` so the new
family-revocation predicate no-ops for them.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0020_session_token_hardening"
down_revision = "0019_mfa_passkeys"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _table_exists("session_families"):
        op.create_table(
            "session_families",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("idle_ttl_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_reason", sa.String(length=32), nullable=True),
            sa.Column("device_fingerprint_hash", sa.String(length=128), nullable=True),
            sa.Column("amr", sa.String(length=64), nullable=True),
            sa.Column("mfa_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_session_families_user_id", "session_families", ["user_id"])
        op.create_index("ix_session_families_absolute", "session_families", ["absolute_expires_at"])

    if not _table_exists("refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "family_id",
                sa.Integer(),
                sa.ForeignKey("session_families.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("prev_id", sa.Integer(), nullable=True),
            sa.Column("next_id", sa.Integer(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
        op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
        op.create_index("ix_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)
        op.create_index("ix_refresh_tokens_expires", "refresh_tokens", ["expires_at"])
        op.create_index(
            "ix_refresh_tokens_family_rotated", "refresh_tokens", ["family_id", "rotated_at"]
        )

    if _table_exists("session_tokens"):
        if not _column_exists("session_tokens", "family_id"):
            op.add_column(
                "session_tokens",
                sa.Column(
                    "family_id",
                    sa.Integer(),
                    sa.ForeignKey("session_families.id", ondelete="CASCADE"),
                    nullable=True,
                ),
            )
            op.create_index("ix_session_tokens_family_id", "session_tokens", ["family_id"])
        if not _column_exists("session_tokens", "refresh_id"):
            op.add_column("session_tokens", sa.Column("refresh_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _table_exists("session_tokens"):
        if _column_exists("session_tokens", "refresh_id"):
            op.drop_column("session_tokens", "refresh_id")
        if _column_exists("session_tokens", "family_id"):
            op.drop_column("session_tokens", "family_id")
    if _table_exists("refresh_tokens"):
        op.drop_table("refresh_tokens")
    if _table_exists("session_families"):
        op.drop_table("session_families")
