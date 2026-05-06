"""week8 baseline

Revision ID: 0001_week8_baseline
Revises: 
Create Date: 2026-04-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_week8_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_is_verified", "users", ["is_verified"], unique=False)
    op.create_index("ix_users_email_verified", "users", ["email", "is_verified"], unique=False)

    op.create_table(
        "session_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_session_tokens_token_hash"),
    )
    op.create_index("ix_session_tokens_user_id", "session_tokens", ["user_id"], unique=False)
    op.create_index("ix_session_tokens_token_hash", "session_tokens", ["token_hash"], unique=False)
    op.create_index("ix_session_tokens_expires_at", "session_tokens", ["expires_at"], unique=False)

    op.create_table(
        "user_action_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_user_action_tokens_token_hash"),
    )
    op.create_index("ix_user_action_tokens_user_id", "user_action_tokens", ["user_id"], unique=False)
    op.create_index("ix_user_action_tokens_purpose", "user_action_tokens", ["purpose"], unique=False)
    op.create_index("ix_user_action_tokens_expires", "user_action_tokens", ["expires_at"], unique=False)
    op.create_index("ix_user_action_tokens_user_purpose", "user_action_tokens", ["user_id", "purpose"], unique=False)

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_email_outbox_created_at", "email_outbox", ["created_at"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_name", sa.String(length=255), nullable=True),
        sa.Column("uploaded_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("completed_items", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("backend_job_id", sa.String(length=64), nullable=True),
        sa.Column("queue_name", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_backend_job_id", "jobs", ["backend_job_id"], unique=False)
    op.create_index("ix_jobs_user_status_created", "jobs", ["user_id", "status", "created_at"], unique=False)
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"], unique=False)

    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_id", sa.String(length=100), nullable=True),
        sa.Column("solvent", sa.String(length=50), nullable=True),
        sa.Column("smiles", sa.Text(), nullable=False),
        sa.Column("nmr_text", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("expected_total_h", sa.Integer(), nullable=False),
        sa.Column("observed_total_h", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("notes_json", sa.Text(), nullable=False),
        sa.Column("parsed_peak_count", sa.Integer(), nullable=False),
        sa.Column("delta_total_h", sa.Integer(), nullable=False),
        sa.Column("full_report_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"], unique=False)
    op.create_index("ix_analyses_job_id", "analyses", ["job_id"], unique=False)
    op.create_index("ix_analyses_label", "analyses", ["label"], unique=False)
    op.create_index("ix_analyses_user_created", "analyses", ["user_id", "created_at"], unique=False)
    op.create_index("ix_analyses_job_created", "analyses", ["job_id", "created_at"], unique=False)
    op.create_index("ix_analyses_label_created", "analyses", ["label", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_analyses_label_created", table_name="analyses")
    op.drop_index("ix_analyses_job_created", table_name="analyses")
    op.drop_index("ix_analyses_user_created", table_name="analyses")
    op.drop_index("ix_analyses_label", table_name="analyses")
    op.drop_index("ix_analyses_job_id", table_name="analyses")
    op.drop_index("ix_analyses_user_id", table_name="analyses")
    op.drop_table("analyses")

    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_index("ix_jobs_user_status_created", table_name="jobs")
    op.drop_index("ix_jobs_backend_job_id", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_email_outbox_created_at", table_name="email_outbox")
    op.drop_table("email_outbox")

    op.drop_index("ix_user_action_tokens_user_purpose", table_name="user_action_tokens")
    op.drop_index("ix_user_action_tokens_expires", table_name="user_action_tokens")
    op.drop_index("ix_user_action_tokens_purpose", table_name="user_action_tokens")
    op.drop_index("ix_user_action_tokens_user_id", table_name="user_action_tokens")
    op.drop_table("user_action_tokens")

    op.drop_index("ix_session_tokens_expires_at", table_name="session_tokens")
    op.drop_index("ix_session_tokens_token_hash", table_name="session_tokens")
    op.drop_index("ix_session_tokens_user_id", table_name="session_tokens")
    op.drop_table("session_tokens")

    op.drop_index("ix_users_email_verified", table_name="users")
    op.drop_index("ix_users_is_verified", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
