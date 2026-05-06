"""phase58 ml model factory

Revision ID: 0006_phase58_ml_model_factory
Revises: 0005_week25_nmr2d_run_canonical_fields
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_phase58_ml_model_factory"
down_revision = "0005_week25_nmr2d_run_canonical_fields"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _table_exists("ml_task_definitions"):
        op.create_table(
            "ml_task_definitions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("domain", sa.String(length=32), nullable=False),
            sa.Column("task_type", sa.String(length=32), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "default_metric",
                sa.String(length=120),
                nullable=False,
                server_default="review_required",
            ),
            sa.Column("required_dataset_type", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("task_key", name="uq_ml_task_definitions_task_key"),
        )
        op.create_index("ix_ml_task_definitions_task_key", "ml_task_definitions", ["task_key"])
        op.create_index(
            "ix_ml_task_definitions_domain_status", "ml_task_definitions", ["domain", "status"]
        )

    if not _table_exists("feature_pipelines"):
        op.create_table(
            "feature_pipelines",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("version", sa.String(length=80), nullable=False),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("input_schema_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("output_schema_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("feature_steps_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="experimental"
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint(
                "task_key", "name", "version", name="uq_feature_pipelines_task_name_version"
            ),
        )
        op.create_index("ix_feature_pipelines_task_key", "feature_pipelines", ["task_key"])
        op.create_index(
            "ix_feature_pipelines_task_status", "feature_pipelines", ["task_key", "status"]
        )

    if not _table_exists("ml_training_runs"):
        op.create_table(
            "ml_training_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("dataset_version_id", sa.Integer(), nullable=False),
            sa.Column("feature_pipeline_id", sa.Integer(), nullable=True),
            sa.Column("model_family", sa.String(length=64), nullable=False),
            sa.Column("model_name", sa.String(length=200), nullable=False),
            sa.Column("model_version", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("parameters_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("training_metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["feature_pipeline_id"], ["feature_pipelines.id"], ondelete="SET NULL"
            ),
        )
        op.create_index("ix_ml_training_runs_task_key", "ml_training_runs", ["task_key"])
        op.create_index("ix_ml_training_runs_dataset", "ml_training_runs", ["dataset_version_id"])
        op.create_index("ix_ml_training_runs_family", "ml_training_runs", ["model_family"])
        op.create_index(
            "ix_ml_training_runs_task_status", "ml_training_runs", ["task_key", "status"]
        )

    if not _table_exists("model_artifacts"):
        op.create_table(
            "model_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("training_run_id", sa.Integer(), nullable=False),
            sa.Column("model_name", sa.String(length=200), nullable=False),
            sa.Column("model_version", sa.String(length=80), nullable=False),
            sa.Column("model_family", sa.String(length=64), nullable=False),
            sa.Column("artifact_uri", sa.Text(), nullable=True),
            sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
            sa.Column("model_hash", sa.String(length=64), nullable=True),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="trained"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["training_run_id"], ["ml_training_runs.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_model_artifacts_training_run_id", "model_artifacts", ["training_run_id"]
        )
        op.create_index("ix_model_artifacts_model_family", "model_artifacts", ["model_family"])
        op.create_index("ix_model_artifacts_model_hash", "model_artifacts", ["model_hash"])
        op.create_index("ix_model_artifacts_task_key", "model_artifacts", ["task_key"])
        op.create_index("ix_model_artifacts_status", "model_artifacts", ["status"])
        op.create_index("ix_model_artifacts_task_status", "model_artifacts", ["task_key", "status"])
        op.create_index(
            "ix_model_artifacts_name_version", "model_artifacts", ["model_name", "model_version"]
        )

    if not _table_exists("ml_evaluation_runs"):
        op.create_table(
            "ml_evaluation_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("training_run_id", sa.Integer(), nullable=True),
            sa.Column("model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("benchmark_dataset_id", sa.Integer(), nullable=True),
            sa.Column("dataset_version_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("slice_metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confusion_summary_json", sa.Text(), nullable=True),
            sa.Column("calibration_summary_json", sa.Text(), nullable=True),
            sa.Column("error_examples_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["training_run_id"], ["ml_training_runs.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["benchmark_dataset_id"], ["benchmark_datasets.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_ml_evaluation_runs_training_run_id", "ml_evaluation_runs", ["training_run_id"]
        )
        op.create_index(
            "ix_ml_evaluation_runs_model_artifact_id", "ml_evaluation_runs", ["model_artifact_id"]
        )
        op.create_index(
            "ix_ml_evaluation_runs_benchmark_dataset_id",
            "ml_evaluation_runs",
            ["benchmark_dataset_id"],
        )
        op.create_index(
            "ix_ml_evaluation_runs_dataset_version_id", "ml_evaluation_runs", ["dataset_version_id"]
        )
        op.create_index("ix_ml_evaluation_runs_status", "ml_evaluation_runs", ["status"])
        op.create_index(
            "ix_ml_evaluation_runs_status_created", "ml_evaluation_runs", ["status", "created_at"]
        )
        op.create_index(
            "ix_ml_evaluation_runs_artifact", "ml_evaluation_runs", ["model_artifact_id"]
        )
        op.create_index(
            "ix_ml_evaluation_runs_dataset", "ml_evaluation_runs", ["dataset_version_id"]
        )

    if not _table_exists("model_metrics"):
        op.create_table(
            "model_metrics",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("evaluation_run_id", sa.Integer(), nullable=False),
            sa.Column("metric_name", sa.String(length=120), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=False),
            sa.Column("metric_unit", sa.String(length=64), nullable=True),
            sa.Column("split", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("passed", sa.Boolean(), nullable=True),
            sa.Column("threshold", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["evaluation_run_id"], ["ml_evaluation_runs.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_model_metrics_evaluation_run_id", "model_metrics", ["evaluation_run_id"]
        )
        op.create_index("ix_model_metrics_metric_name", "model_metrics", ["metric_name"])
        op.create_index(
            "ix_ml_model_metrics_evaluation_metric",
            "model_metrics",
            ["evaluation_run_id", "metric_name"],
        )
        op.create_index("ix_ml_model_metrics_split", "model_metrics", ["split"])

    if not _table_exists("calibration_assessments"):
        op.create_table(
            "calibration_assessments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("evaluation_run_id", sa.Integer(), nullable=True),
            sa.Column(
                "calibration_method",
                sa.String(length=64),
                nullable=False,
                server_default="not_assessed",
            ),
            sa.Column("calibration_metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="not_assessed"
            ),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["evaluation_run_id"], ["ml_evaluation_runs.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_calibration_assessments_model_artifact_id",
            "calibration_assessments",
            ["model_artifact_id"],
        )
        op.create_index(
            "ix_calibration_assessments_evaluation_run_id",
            "calibration_assessments",
            ["evaluation_run_id"],
        )
        op.create_index(
            "ix_calibration_assessments_calibration_method",
            "calibration_assessments",
            ["calibration_method"],
        )
        op.create_index("ix_calibration_assessments_status", "calibration_assessments", ["status"])
        op.create_index(
            "ix_calibration_assessments_artifact_status",
            "calibration_assessments",
            ["model_artifact_id", "status"],
        )
        op.create_index(
            "ix_calibration_assessments_evaluation",
            "calibration_assessments",
            ["evaluation_run_id"],
        )

    if not _table_exists("error_analysis_slices"):
        op.create_table(
            "error_analysis_slices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("evaluation_run_id", sa.Integer(), nullable=False),
            sa.Column("slice_name", sa.String(length=200), nullable=False),
            sa.Column("slice_type", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("representative_errors_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["evaluation_run_id"], ["ml_evaluation_runs.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_error_analysis_slices_evaluation_run_id",
            "error_analysis_slices",
            ["evaluation_run_id"],
        )
        op.create_index(
            "ix_error_analysis_slices_slice_type", "error_analysis_slices", ["slice_type"]
        )
        op.create_index("ix_error_analysis_slices_severity", "error_analysis_slices", ["severity"])
        op.create_index(
            "ix_error_analysis_slices_evaluation_severity",
            "error_analysis_slices",
            ["evaluation_run_id", "severity"],
        )
        op.create_index("ix_error_analysis_slices_type", "error_analysis_slices", ["slice_type"])

    if not _table_exists("out_of_domain_assessments"):
        op.create_table(
            "out_of_domain_assessments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("dataset_version_id", sa.Integer(), nullable=True),
            sa.Column("method", sa.String(length=64), nullable=False, server_default="rule_based"),
            sa.Column("ood_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("high_risk_regions_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="requires_review"
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_out_of_domain_assessments_model_artifact_id",
            "out_of_domain_assessments",
            ["model_artifact_id"],
        )
        op.create_index(
            "ix_out_of_domain_assessments_dataset_version_id",
            "out_of_domain_assessments",
            ["dataset_version_id"],
        )
        op.create_index(
            "ix_out_of_domain_assessments_method", "out_of_domain_assessments", ["method"]
        )
        op.create_index(
            "ix_out_of_domain_assessments_status", "out_of_domain_assessments", ["status"]
        )
        op.create_index(
            "ix_ood_assessments_artifact_status",
            "out_of_domain_assessments",
            ["model_artifact_id", "status"],
        )
        op.create_index(
            "ix_ood_assessments_dataset", "out_of_domain_assessments", ["dataset_version_id"]
        )

    if not _table_exists("model_cards"):
        op.create_table(
            "model_cards",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("task_key", sa.String(length=120), nullable=False),
            sa.Column("intended_use", sa.Text(), nullable=False),
            sa.Column("limitations", sa.Text(), nullable=False),
            sa.Column("training_data_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("evaluation_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("bias_risk_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("out_of_domain_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("calibration_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("human_review_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "approval_status", sa.String(length=32), nullable=False, server_default="draft"
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="CASCADE"
            ),
        )
        op.create_index("ix_model_cards_model_artifact_id", "model_cards", ["model_artifact_id"])
        op.create_index("ix_model_cards_task_key", "model_cards", ["task_key"])
        op.create_index("ix_model_cards_approval_status", "model_cards", ["approval_status"])
        op.create_index("ix_model_cards_artifact", "model_cards", ["model_artifact_id"])
        op.create_index(
            "ix_model_cards_task_status", "model_cards", ["task_key", "approval_status"]
        )

    if not _table_exists("deployment_candidates"):
        op.create_table(
            "deployment_candidates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("model_card_id", sa.Integer(), nullable=True),
            sa.Column("target_module", sa.String(length=64), nullable=False),
            sa.Column("target_endpoint", sa.String(length=300), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
            sa.Column("reviewer_name", sa.String(length=200), nullable=True),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["model_card_id"], ["model_cards.id"], ondelete="SET NULL"),
        )
        op.create_index(
            "ix_deployment_candidates_model_artifact_id",
            "deployment_candidates",
            ["model_artifact_id"],
        )
        op.create_index(
            "ix_deployment_candidates_model_card_id", "deployment_candidates", ["model_card_id"]
        )
        op.create_index(
            "ix_deployment_candidates_target_module", "deployment_candidates", ["target_module"]
        )
        op.create_index("ix_deployment_candidates_status", "deployment_candidates", ["status"])
        op.create_index(
            "ix_deployment_candidates_artifact_status",
            "deployment_candidates",
            ["model_artifact_id", "status"],
        )
        op.create_index(
            "ix_deployment_candidates_target_status",
            "deployment_candidates",
            ["target_module", "status"],
        )

    if not _table_exists("prediction_service_configs"):
        op.create_table(
            "prediction_service_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("target_module", sa.String(length=64), nullable=False),
            sa.Column("active_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("fallback_model_artifact_id", sa.Integer(), nullable=True),
            sa.Column("routing_rules_json", sa.Text(), nullable=False, server_default="{}"),
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
        )
        op.create_index(
            "ix_prediction_service_configs_target_module",
            "prediction_service_configs",
            ["target_module"],
        )
        op.create_index(
            "ix_prediction_service_configs_active_model_artifact_id",
            "prediction_service_configs",
            ["active_model_artifact_id"],
        )
        op.create_index(
            "ix_prediction_service_configs_fallback_model_artifact_id",
            "prediction_service_configs",
            ["fallback_model_artifact_id"],
        )
        op.create_index(
            "ix_prediction_service_configs_status", "prediction_service_configs", ["status"]
        )
        op.create_index(
            "ix_prediction_service_configs_target_status",
            "prediction_service_configs",
            ["target_module", "status"],
        )


def downgrade() -> None:
    for table_name in (
        "prediction_service_configs",
        "deployment_candidates",
        "model_cards",
        "out_of_domain_assessments",
        "error_analysis_slices",
        "calibration_assessments",
        "model_metrics",
        "ml_evaluation_runs",
        "model_artifacts",
        "ml_training_runs",
        "feature_pipelines",
        "ml_task_definitions",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
