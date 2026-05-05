"""phase60 product orchestration

Revision ID: 0008_phase60_product_orchestration
Revises: 0007_phase59_controlled_ai_inference
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_phase60_product_orchestration"
down_revision = "0007_phase59_controlled_ai_inference"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _table_exists("product_program_registry"):
        op.create_table(
            "product_program_registry",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("program_key", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("program_key", name="uq_product_program_registry_key"),
        )
        op.create_index(
            "ix_product_program_registry_program_key", "product_program_registry", ["program_key"]
        )
        op.create_index(
            "ix_product_program_registry_order", "product_program_registry", ["display_order"]
        )
        op.create_index(
            "ix_product_program_registry_status", "product_program_registry", ["status"]
        )

    if not _table_exists("module_priority_maps"):
        op.create_table(
            "module_priority_maps",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("context", sa.String(length=32), nullable=False),
            sa.Column("program_order_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("context", name="uq_module_priority_maps_context"),
        )
        op.create_index("ix_module_priority_maps_context", "module_priority_maps", ["context"])

    if not _table_exists("cross_module_workflow_templates"):
        op.create_table(
            "cross_module_workflow_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_key", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=240), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("program_sequence_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "trigger_type", sa.String(length=64), nullable=False, server_default="manual"
            ),
            sa.Column("required_inputs_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("optional_inputs_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("template_key", name="uq_cross_module_workflow_templates_key"),
        )
        op.create_index(
            "ix_cross_module_workflow_templates_template_key",
            "cross_module_workflow_templates",
            ["template_key"],
        )
        op.create_index(
            "ix_cross_module_workflow_templates_status",
            "cross_module_workflow_templates",
            ["status"],
        )
        op.create_index(
            "ix_cross_module_workflow_templates_trigger",
            "cross_module_workflow_templates",
            ["trigger_type"],
        )

    if not _table_exists("spectroscopy_to_regulatory_bridges"):
        op.create_table(
            "spectroscopy_to_regulatory_bridges",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("spectracheck_session_id", sa.Integer(), nullable=True),
            sa.Column("evidence_item_id", sa.Integer(), nullable=True),
            sa.Column("report_id", sa.Integer(), nullable=True),
            sa.Column("dossier_id", sa.Integer(), nullable=True),
            sa.Column("compound_id", sa.Integer(), nullable=True),
            sa.Column("batch_id", sa.Integer(), nullable=True),
            sa.Column(
                "bridge_status", sa.String(length=32), nullable=False, server_default="draft"
            ),
            sa.Column(
                "extracted_regulatory_signals_json", sa.Text(), nullable=False, server_default="{}"
            ),
            sa.Column(
                "created_requirement_ids_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "created_action_item_ids_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["spectracheck_session_id"], ["spectracheck_sessions.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["evidence_item_id"], ["spectracheck_evidence_records.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["report_id"], ["spectracheck_report_records.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["dossier_id"], ["regulatory_dossiers.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["compound_id"], ["compound_entities.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["batch_id"], ["compound_batches.id"], ondelete="SET NULL"),
        )
        op.create_index(
            "ix_s2r_bridges_session",
            "spectroscopy_to_regulatory_bridges",
            ["spectracheck_session_id"],
        )
        op.create_index(
            "ix_s2r_bridges_dossier_status",
            "spectroscopy_to_regulatory_bridges",
            ["dossier_id", "bridge_status"],
        )

    if not _table_exists("regulatory_to_reaction_bridges"):
        op.create_table(
            "regulatory_to_reaction_bridges",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("dossier_id", sa.Integer(), nullable=True),
            sa.Column("regulatory_action_item_id", sa.Integer(), nullable=True),
            sa.Column("reaction_project_id", sa.Integer(), nullable=True),
            sa.Column("compound_id", sa.Integer(), nullable=True),
            sa.Column("batch_id", sa.Integer(), nullable=True),
            sa.Column(
                "bridge_status", sa.String(length=32), nullable=False, server_default="draft"
            ),
            sa.Column(
                "regulatory_constraints_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "optimization_objectives_json", sa.Text(), nullable=False, server_default="{}"
            ),
            sa.Column(
                "created_constraint_ids_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["dossier_id"], ["regulatory_dossiers.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["regulatory_action_item_id"],
                ["regulatory_action_items.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["reaction_project_id"], ["reaction_projects.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["compound_id"], ["compound_entities.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["batch_id"], ["compound_batches.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_r2r_bridges_dossier", "regulatory_to_reaction_bridges", ["dossier_id"])
        op.create_index(
            "ix_r2r_bridges_project_status",
            "regulatory_to_reaction_bridges",
            ["reaction_project_id", "bridge_status"],
        )

    if not _table_exists("regulatory_constraint_sets"):
        op.create_table(
            "regulatory_constraint_sets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("reaction_project_id", sa.Integer(), nullable=False),
            sa.Column("dossier_id", sa.Integer(), nullable=True),
            sa.Column(
                "source_action_item_ids_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "constraint_type", sa.String(length=64), nullable=False, server_default="other"
            ),
            sa.Column("constraint_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="warning"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["reaction_project_id"], ["reaction_projects.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["dossier_id"], ["regulatory_dossiers.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_regulatory_constraints_project_status",
            "regulatory_constraint_sets",
            ["reaction_project_id", "status"],
        )
        op.create_index(
            "ix_regulatory_constraints_type_severity",
            "regulatory_constraint_sets",
            ["constraint_type", "severity"],
        )

    if not _table_exists("compliance_driven_optimization_objectives"):
        op.create_table(
            "compliance_driven_optimization_objectives",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("reaction_project_id", sa.Integer(), nullable=False),
            sa.Column("regulatory_constraint_set_id", sa.Integer(), nullable=True),
            sa.Column("objective_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("scalarization_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("hard_constraints_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("soft_constraints_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["reaction_project_id"], ["reaction_projects.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["regulatory_constraint_set_id"],
                ["regulatory_constraint_sets.id"],
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "ix_compliance_objectives_project_status",
            "compliance_driven_optimization_objectives",
            ["reaction_project_id", "status"],
        )

    if not _table_exists("ctd_module3_report_bundles"):
        op.create_table(
            "ctd_module3_report_bundles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("dossier_id", sa.Integer(), nullable=False),
            sa.Column("spectracheck_report_id", sa.Integer(), nullable=True),
            sa.Column("regulatory_readiness_report_id", sa.Integer(), nullable=True),
            sa.Column("batch_assessment_id", sa.Integer(), nullable=True),
            sa.Column("qnmr_compliance_id", sa.Integer(), nullable=True),
            sa.Column("impurity_register_id", sa.Integer(), nullable=True),
            sa.Column("ai_governance_record_id", sa.Integer(), nullable=True),
            sa.Column("report_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("report_html", sa.Text(), nullable=True),
            sa.Column("report_sha256", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(["dossier_id"], ["regulatory_dossiers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["spectracheck_report_id"], ["spectracheck_report_records.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["regulatory_readiness_report_id"],
                ["regulatory_readiness_reports.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["batch_assessment_id"], ["batch_regulatory_assessments.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["qnmr_compliance_id"], ["qnmr_compliance_profiles.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["impurity_register_id"], ["impurity_risk_register.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["ai_governance_record_id"], ["ai_governance_records.id"], ondelete="SET NULL"
            ),
        )
        op.create_index(
            "ix_ctd_module3_bundles_dossier_created",
            "ctd_module3_report_bundles",
            ["dossier_id", "created_at"],
        )
        op.create_index("ix_ctd_module3_bundles_status", "ctd_module3_report_bundles", ["status"])

    if not _table_exists("cross_module_action_items"):
        op.create_table(
            "cross_module_action_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_program", sa.String(length=64), nullable=False),
            sa.Column("target_program", sa.String(length=64), nullable=False),
            sa.Column("source_resource_type", sa.String(length=120), nullable=False),
            sa.Column("source_resource_id", sa.Integer(), nullable=False),
            sa.Column("target_resource_type", sa.String(length=120), nullable=True),
            sa.Column("target_resource_id", sa.Integer(), nullable=True),
            sa.Column("action_type", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="warning"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_cross_module_actions_source",
            "cross_module_action_items",
            ["source_program", "source_resource_type"],
        )
        op.create_index(
            "ix_cross_module_actions_target",
            "cross_module_action_items",
            ["target_program", "target_resource_type"],
        )
        op.create_index(
            "ix_cross_module_actions_status_severity",
            "cross_module_action_items",
            ["status", "severity"],
        )

    if not _table_exists("cross_module_command_center_summaries"):
        op.create_table(
            "cross_module_command_center_summaries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("scope_id", sa.Integer(), nullable=True),
            sa.Column("spectracheck_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("regulatory_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("reaction_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "open_cross_module_actions_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_command_center_summaries_scope",
            "cross_module_command_center_summaries",
            ["scope", "scope_id"],
        )
        op.create_index(
            "ix_command_center_summaries_created",
            "cross_module_command_center_summaries",
            ["created_at"],
        )


def downgrade() -> None:
    for table_name in (
        "cross_module_command_center_summaries",
        "cross_module_action_items",
        "ctd_module3_report_bundles",
        "compliance_driven_optimization_objectives",
        "regulatory_constraint_sets",
        "regulatory_to_reaction_bridges",
        "spectroscopy_to_regulatory_bridges",
        "cross_module_workflow_templates",
        "module_priority_maps",
        "product_program_registry",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
