"""phase61 mobile pwa field review

Revision ID: 0009_phase61_mobile_pwa
Revises: 0008_phase60_product_orchestration
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_phase61_mobile_pwa"
down_revision = "0008_phase60_product_orchestration"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _table_exists("mobile_device_sessions"):
        op.create_table(
            "mobile_device_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_email", sa.String(length=255), nullable=True),
            sa.Column("device_label", sa.String(length=200), nullable=True),
            sa.Column("device_type", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("platform", sa.String(length=120), nullable=True),
            sa.Column("browser", sa.String(length=120), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_mobile_device_sessions_user_status",
            "mobile_device_sessions",
            ["user_email", "status"],
        )
        op.create_index(
            "ix_mobile_device_sessions_last_seen",
            "mobile_device_sessions",
            ["last_seen_at"],
        )

    if not _table_exists("mobile_view_preferences"):
        op.create_table(
            "mobile_view_preferences",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_email", sa.String(length=255), nullable=True),
            sa.Column("device_session_id", sa.Integer(), nullable=True),
            sa.Column("preferred_home", sa.String(length=40), nullable=False, server_default="dashboard"),
            sa.Column("compact_mode", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("bottom_nav_enabled", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("reduce_motion", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("high_contrast", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["device_session_id"], ["mobile_device_sessions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_mobile_view_preferences_user",
            "mobile_view_preferences",
            ["user_email"],
        )
        op.create_index(
            "ix_mobile_view_preferences_device",
            "mobile_view_preferences",
            ["device_session_id"],
        )

    if not _table_exists("mobile_action_drafts"):
        op.create_table(
            "mobile_action_drafts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_email", sa.String(length=255), nullable=True),
            sa.Column("device_session_id", sa.Integer(), nullable=True),
            sa.Column("action_type", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("target_type", sa.String(length=120), nullable=False),
            sa.Column("target_id", sa.String(length=120), nullable=False),
            sa.Column("draft_payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("validation_warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["device_session_id"], ["mobile_device_sessions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_mobile_action_drafts_user_status",
            "mobile_action_drafts",
            ["user_email", "status"],
        )
        op.create_index(
            "ix_mobile_action_drafts_device_status",
            "mobile_action_drafts",
            ["device_session_id", "status"],
        )
        op.create_index(
            "ix_mobile_action_drafts_target",
            "mobile_action_drafts",
            ["target_type", "target_id"],
        )

    if not _table_exists("mobile_sync_results"):
        op.create_table(
            "mobile_sync_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("device_session_id", sa.Integer(), nullable=True),
            sa.Column("synced_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["device_session_id"], ["mobile_device_sessions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_mobile_sync_results_device_created",
            "mobile_sync_results",
            ["device_session_id", "created_at"],
        )

    if not _table_exists("mobile_push_subscriptions"):
        op.create_table(
            "mobile_push_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_email", sa.String(length=255), nullable=True),
            sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
            sa.Column("subscription_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint(
                "endpoint_hash", name="uq_mobile_push_subscriptions_endpoint_hash"
            ),
        )
        op.create_index(
            "ix_mobile_push_subscriptions_user_status",
            "mobile_push_subscriptions",
            ["user_email", "status"],
        )

    if not _table_exists("mobile_notifications"):
        op.create_table(
            "mobile_notifications",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_email", sa.String(length=255), nullable=True),
            sa.Column("notification_type", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("target_type", sa.String(length=120), nullable=True),
            sa.Column("target_id", sa.String(length=120), nullable=True),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="unread"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_mobile_notifications_user_status",
            "mobile_notifications",
            ["user_email", "status"],
        )
        op.create_index(
            "ix_mobile_notifications_target",
            "mobile_notifications",
            ["target_type", "target_id"],
        )
        op.create_index(
            "ix_mobile_notifications_created",
            "mobile_notifications",
            ["created_at"],
        )

    if not _table_exists("compact_module_summaries"):
        op.create_table(
            "compact_module_summaries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("scope_id", sa.String(length=120), nullable=True),
            sa.Column("spectracheck_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("regulatory_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("reaction_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("action_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_compact_module_summaries_scope",
            "compact_module_summaries",
            ["scope", "scope_id"],
        )
        op.create_index(
            "ix_compact_module_summaries_generated",
            "compact_module_summaries",
            ["generated_at"],
        )


def downgrade() -> None:
    for table_name in (
        "compact_module_summaries",
        "mobile_notifications",
        "mobile_push_subscriptions",
        "mobile_sync_results",
        "mobile_action_drafts",
        "mobile_view_preferences",
        "mobile_device_sessions",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)

