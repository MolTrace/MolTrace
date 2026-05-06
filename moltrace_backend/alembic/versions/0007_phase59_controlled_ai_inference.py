"""phase59 controlled ai inference

Revision ID: 0007_phase59_controlled_ai_inference
Revises: 0006_phase58_ml_model_factory
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_phase59_controlled_ai_inference"
down_revision = "0006_phase58_ml_model_factory"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return column_name in {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _table_exists(table_name) and not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing(
        "prediction_service_configs",
        sa.Column("service_key", sa.String(length=120), nullable=True),
    )
    _add_column_if_missing(
        "prediction_service_configs",
        sa.Column("confidence_thresholds_json", sa.Text(), nullable=False, server_default="{}"),
    )
    _add_column_if_missing(
        "prediction_service_configs",
        sa.Column("ood_rules_json", sa.Text(), nullable=False, server_default="{}"),
    )
    _add_column_if_missing(
        "prediction_service_configs",
        sa.Column("fallback_rules_json", sa.Text(), nullable=False, server_default="{}"),
    )
    _add_column_if_missing(
        "prediction_service_configs",
        sa.Column("human_review_rules_json", sa.Text(), nullable=False, server_default="{}"),
    )
    _add_column_if_missing(
        "prediction_service_configs",
        sa.Column("max_batch_size", sa.Integer(), nullable=True),
    )
    if _table_exists("prediction_service_configs"):
        op.create_index(
            "ix_prediction_service_configs_service_key",
            "prediction_service_configs",
            ["service_key"],
            if_not_exists=True,
        )

    if not _table_exists("ai_service_registry"):
        op.create_table(
            "ai_service_registry",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("target_module", sa.String(length=64), nullable=False),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("active_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("fallback_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("prediction_service_config_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["active_model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["fallback_model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["prediction_service_config_id"],
                ["prediction_service_configs.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint("service_key", name="uq_ai_service_registry_service_key"),
        )
        op.create_index(
            "ix_ai_service_registry_service_key", "ai_service_registry", ["service_key"]
        )
        op.create_index("ix_ai_service_registry_task_key", "ai_service_registry", ["task_key"])
        op.create_index(
            "ix_ai_service_registry_target_module", "ai_service_registry", ["target_module"]
        )
        op.create_index(
            "ix_ai_service_registry_module_status",
            "ai_service_registry",
            ["target_module", "status"],
        )

    if not _table_exists("prediction_runs"):
        op.create_table(
            "prediction_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("target_module", sa.String(length=64), nullable=False),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("deployment_candidate_id", sa.Integer(), nullable=True),
            sa.Column("dataset_version_id", sa.Integer(), nullable=True),
            sa.Column("request_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("input_hash", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("prediction_result_id", sa.Integer(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("uncertainty_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "ood_status",
                sa.String(length=32),
                nullable=False,
                server_default="not_assessed",
            ),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["deployment_candidate_id"], ["deployment_candidates.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index("ix_prediction_runs_service_key", "prediction_runs", ["service_key"])
        op.create_index("ix_prediction_runs_target_module", "prediction_runs", ["target_module"])
        op.create_index("ix_prediction_runs_task_key", "prediction_runs", ["task_key"])
        op.create_index(
            "ix_prediction_runs_model_artifact_id", "prediction_runs", ["model_artifact_id"]
        )
        op.create_index(
            "ix_prediction_runs_dataset_version_id", "prediction_runs", ["dataset_version_id"]
        )
        op.create_index("ix_prediction_runs_input_hash", "prediction_runs", ["input_hash"])
        op.create_index("ix_prediction_runs_status", "prediction_runs", ["status"])
        op.create_index("ix_prediction_runs_ood_status", "prediction_runs", ["ood_status"])
        op.create_index(
            "ix_prediction_runs_service_status", "prediction_runs", ["service_key", "status"]
        )
        op.create_index(
            "ix_prediction_runs_model_created",
            "prediction_runs",
            ["model_artifact_id", "created_at"],
        )

    if not _table_exists("prediction_results"):
        op.create_table(
            "prediction_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("prediction_run_id", sa.Integer(), nullable=False),
            sa.Column("result_type", sa.String(length=64), nullable=False),
            sa.Column("output_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("uncertainty_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("explanation_id", sa.Integer(), nullable=True),
            sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["prediction_run_id"], ["prediction_runs.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_prediction_results_prediction_run_id", "prediction_results", ["prediction_run_id"]
        )
        op.create_index("ix_prediction_results_result_type", "prediction_results", ["result_type"])
        op.create_index(
            "ix_prediction_results_explanation_id", "prediction_results", ["explanation_id"]
        )
        op.create_index("ix_prediction_results_run", "prediction_results", ["prediction_run_id"])
        op.create_index(
            "ix_prediction_results_type_created",
            "prediction_results",
            ["result_type", "created_at"],
        )

    if not _table_exists("model_routing_decisions"):
        op.create_table(
            "model_routing_decisions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("target_module", sa.String(length=64), nullable=False),
            sa.Column("selected_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("fallback_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("routing_metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["selected_model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["fallback_model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_model_routing_decisions_service_key", "model_routing_decisions", ["service_key"]
        )
        op.create_index(
            "ix_model_routing_decisions_target", "model_routing_decisions", ["target_module"]
        )
        op.create_index(
            "ix_model_routing_decisions_service_created",
            "model_routing_decisions",
            ["service_key", "created_at"],
        )

    if not _table_exists("inference_explanations"):
        op.create_table(
            "inference_explanations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("prediction_run_id", sa.Integer(), nullable=True),
            sa.Column(
                "explanation_type",
                sa.String(length=64),
                nullable=False,
                server_default="unavailable",
            ),
            sa.Column("explanation_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["prediction_run_id"], ["prediction_runs.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_inference_explanations_prediction_run_id",
            "inference_explanations",
            ["prediction_run_id"],
        )
        op.create_index(
            "ix_inference_explanations_type", "inference_explanations", ["explanation_type"]
        )
        op.create_index(
            "ix_inference_explanations_run", "inference_explanations", ["prediction_run_id"]
        )

    if not _table_exists("prediction_feedback"):
        op.create_table(
            "prediction_feedback",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("prediction_run_id", sa.Integer(), nullable=False),
            sa.Column("feedback_type", sa.String(length=32), nullable=False),
            sa.Column("reviewer_name", sa.String(length=200), nullable=True),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("corrected_output_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["prediction_run_id"], ["prediction_runs.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_prediction_feedback_prediction_run_id", "prediction_feedback", ["prediction_run_id"]
        )
        op.create_index(
            "ix_prediction_feedback_feedback_type", "prediction_feedback", ["feedback_type"]
        )
        op.create_index("ix_prediction_feedback_created", "prediction_feedback", ["created_at"])
        op.create_index(
            "ix_prediction_feedback_run_type",
            "prediction_feedback",
            ["prediction_run_id", "feedback_type"],
        )

    if not _table_exists("active_learning_candidates"):
        op.create_table(
            "active_learning_candidates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("prediction_run_id", sa.Integer(), nullable=True),
            sa.Column("source_module", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.String(length=64), nullable=False),
            sa.Column("priority", sa.String(length=32), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
            sa.Column("linked_model_improvement_item_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["prediction_run_id"], ["prediction_runs.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["linked_model_improvement_item_id"],
                ["model_improvement_queue_items.id"],
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "ix_active_learning_candidates_prediction_run_id",
            "active_learning_candidates",
            ["prediction_run_id"],
        )
        op.create_index(
            "ix_active_learning_candidates_source_module",
            "active_learning_candidates",
            ["source_module"],
        )
        op.create_index(
            "ix_active_learning_candidates_reason", "active_learning_candidates", ["reason"]
        )
        op.create_index(
            "ix_active_learning_candidates_priority", "active_learning_candidates", ["priority"]
        )
        op.create_index(
            "ix_active_learning_candidates_status", "active_learning_candidates", ["status"]
        )
        op.create_index(
            "ix_active_learning_candidates_run", "active_learning_candidates", ["prediction_run_id"]
        )
        op.create_index(
            "ix_active_learning_candidates_status_priority",
            "active_learning_candidates",
            ["status", "priority"],
        )

    if not _table_exists("shadow_evaluation_runs"):
        op.create_table(
            "shadow_evaluation_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("production_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("candidate_model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("dataset_version_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("comparison_metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("disagreement_examples_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["production_model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["candidate_model_artifact_id"], ["model_artifacts.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_shadow_evaluation_runs_service_key", "shadow_evaluation_runs", ["service_key"]
        )
        op.create_index("ix_shadow_evaluation_runs_status", "shadow_evaluation_runs", ["status"])
        op.create_index(
            "ix_shadow_evaluation_runs_candidate",
            "shadow_evaluation_runs",
            ["candidate_model_artifact_id"],
        )
        op.create_index(
            "ix_shadow_evaluation_runs_service_status",
            "shadow_evaluation_runs",
            ["service_key", "status"],
        )

    if not _table_exists("canary_deployment_records"):
        op.create_table(
            "canary_deployment_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("candidate_model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("target_module", sa.String(length=64), nullable=False),
            sa.Column("traffic_percent", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
            sa.Column("monitoring_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("reviewer_name", sa.String(length=200), nullable=True),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["candidate_model_artifact_id"], ["model_artifacts.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_canary_deployment_records_service_key", "canary_deployment_records", ["service_key"]
        )
        op.create_index(
            "ix_canary_deployment_records_candidate_model_artifact_id",
            "canary_deployment_records",
            ["candidate_model_artifact_id"],
        )
        op.create_index(
            "ix_canary_deployment_records_target_module",
            "canary_deployment_records",
            ["target_module"],
        )
        op.create_index(
            "ix_canary_deployment_records_status", "canary_deployment_records", ["status"]
        )
        op.create_index(
            "ix_canary_deployments_candidate",
            "canary_deployment_records",
            ["candidate_model_artifact_id"],
        )
        op.create_index(
            "ix_canary_deployments_service_status",
            "canary_deployment_records",
            ["service_key", "status"],
        )

    if not _table_exists("model_monitoring_events"):
        op.create_table(
            "model_monitoring_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_model_monitoring_events_service_key", "model_monitoring_events", ["service_key"]
        )
        op.create_index(
            "ix_model_monitoring_events_model_artifact_id",
            "model_monitoring_events",
            ["model_artifact_id"],
        )
        op.create_index(
            "ix_model_monitoring_events_event_type", "model_monitoring_events", ["event_type"]
        )
        op.create_index(
            "ix_model_monitoring_events_severity", "model_monitoring_events", ["severity"]
        )
        op.create_index(
            "ix_model_monitoring_events_service_created",
            "model_monitoring_events",
            ["service_key", "created_at"],
        )
        op.create_index(
            "ix_model_monitoring_events_type_severity",
            "model_monitoring_events",
            ["event_type", "severity"],
        )


def downgrade() -> None:
    for table_name in (
        "model_monitoring_events",
        "canary_deployment_records",
        "shadow_evaluation_runs",
        "active_learning_candidates",
        "prediction_feedback",
        "inference_explanations",
        "model_routing_decisions",
        "prediction_results",
        "prediction_runs",
        "ai_service_registry",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
