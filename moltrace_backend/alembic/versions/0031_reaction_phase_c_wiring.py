"""Repho Phase C wiring: yield-prediction runs, proposed-route scores, forward checks

Revision ID: 0031_reaction_phase_c_wiring
Revises: 0030_reaction_warm_start_priors
Create Date: 2026-07-23

Additive + idempotent. Adds the three persistence tables for the Phase-C HTTP surfaces that are
usable with no heavy dependency installed: ``reaction_yield_prediction_runs`` (R12 — lightweight
surrogate fit on the project's own completed experiments, backend decision recorded verbatim),
``reaction_proposed_route_scores`` (R13 — chemist-supplied routes scored by the frozen safety +
green engines), and ``reaction_forward_checks`` (R14 — supplied forward predictions cross-checked
against the frozen engines). The generative heavy paths stay unwired. No changes to existing
tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_reaction_phase_c_wiring"
down_revision = "0030_reaction_warm_start_priors"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("reaction_yield_prediction_runs"):
        op.create_table(
            "reaction_yield_prediction_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("backend", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("trained_n", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "require_verified", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("predictions_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "capability_provenance_json", sa.Text(), nullable=False, server_default="{}"
            ),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_yield_prediction_runs_reaction_project_id",
            "reaction_yield_prediction_runs",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_yield_prediction_runs_project_created",
            "reaction_yield_prediction_runs",
            ["reaction_project_id", "created_at"],
        )

    if not _table_exists("reaction_proposed_route_scores"):
        op.create_table(
            "reaction_proposed_route_scores",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("route_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("score_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("mermaid_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_proposed_route_scores_reaction_project_id",
            "reaction_proposed_route_scores",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_proposed_route_scores_project_created",
            "reaction_proposed_route_scores",
            ["reaction_project_id", "created_at"],
        )

    if not _table_exists("reaction_forward_checks"):
        op.create_table(
            "reaction_forward_checks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "reaction_project_id",
                sa.Integer(),
                sa.ForeignKey("reaction_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_reaction_forward_checks_reaction_project_id",
            "reaction_forward_checks",
            ["reaction_project_id"],
        )
        op.create_index(
            "ix_reaction_forward_checks_project_created",
            "reaction_forward_checks",
            ["reaction_project_id", "created_at"],
        )


def downgrade() -> None:
    if _table_exists("reaction_forward_checks"):
        op.drop_table("reaction_forward_checks")
    if _table_exists("reaction_proposed_route_scores"):
        op.drop_table("reaction_proposed_route_scores")
    if _table_exists("reaction_yield_prediction_runs"):
        op.drop_table("reaction_yield_prediction_runs")
