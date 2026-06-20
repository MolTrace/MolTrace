"""Regulatory-compliance evaluation for the Repho reaction optimizer (R4 enforcement, read side).

Closes the Regentry→Repho loop where it can actually be enforced. The Bayesian optimizer predicts
a single scalarized acquisition score per candidate — NOT per-field outcomes — so an outcome limit
(an ICH impurity %, a purity floor) cannot be filtered at ranking time. It *can* be enforced against
the **actual measured outcomes** of completed experiments. This module evaluates a project's
experiments against its active injected regulatory constraints (via the pure
``reaction_regulatory_constraints`` engine) and reports which experiments breach a limit, with full
provenance back to the regulatory source — so a chemist sees the non-compliant results and the next
experiment is informed by them.

The response models are co-located here (rather than the large central ``models.py``) to keep the
change off the contended monolith; FastAPI/OpenAPI pick them up wherever they are defined.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .orm import ReactionExperimentORM, ReactionProjectORM, RegulatoryConstraintSetORM
from .reaction_regulatory_constraints import evaluate_candidate, parse_limits


class ReactionRegulatoryComplianceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: int
    experiment_code: str
    status: str
    feasible: bool
    hard_block: bool
    penalty: float
    violations: list[dict[str, Any]] = Field(default_factory=list)
    unmeasured: list[str] = Field(default_factory=list)


class ReactionRegulatoryComplianceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction_project_id: int
    enforced_constraint_count: int = 0
    active_constraint_ids: list[int] = Field(default_factory=list)
    constraint_bases: list[str] = Field(default_factory=list)
    experiments_evaluated: int = 0
    non_compliant_experiment_count: int = 0
    items: list[ReactionRegulatoryComplianceItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _constraint_dict(row: RegulatoryConstraintSetORM) -> dict[str, Any]:
    return {
        "id": row.id,
        "constraint_type": row.constraint_type,
        "severity": row.severity,
        "status": row.status,
        "constraint_json": _json_dict(row.constraint_json),
        "source_action_item_ids": _json_list(row.source_action_item_ids_json),
    }


def evaluate_project_compliance(
    session_factory: sessionmaker[Session], project_id: int
) -> ReactionRegulatoryComplianceReport:
    """Evaluate a project's recorded experiment outcomes against its active regulatory limits.

    Only constraints carrying a numeric limit (active/reviewed) are enforceable; the report is
    advisory when none exist. Experiments without a recorded outcome are skipped (nothing to
    measure). A hard violation (high/critical tier) marks the experiment non-compliant.
    """
    with session_scope(session_factory) as session:
        project = session.get(ReactionProjectORM, project_id)
        if project is None:
            raise KeyError("Reaction project not found.")

        constraint_rows = session.scalars(
            select(RegulatoryConstraintSetORM).where(
                RegulatoryConstraintSetORM.reaction_project_id == project_id
            )
        ).all()
        limits = parse_limits(_constraint_dict(r) for r in constraint_rows)

        exp_rows = session.scalars(
            select(ReactionExperimentORM)
            .where(ReactionExperimentORM.reaction_project_id == project_id)
            .order_by(ReactionExperimentORM.id)
        ).all()

        items: list[ReactionRegulatoryComplianceItem] = []
        non_compliant = 0
        evaluated = 0
        for exp in exp_rows:
            outcome = _json_dict(exp.outcome_json)
            if not outcome:
                continue  # no measured outcome yet — nothing to evaluate
            evaluated += 1
            verdict = evaluate_candidate(outcome, limits)
            summary = verdict.summary()
            if verdict.hard_block:
                non_compliant += 1
            items.append(
                ReactionRegulatoryComplianceItem(
                    experiment_id=exp.id,
                    experiment_code=exp.experiment_code,
                    status=exp.status,
                    feasible=verdict.feasible,
                    hard_block=verdict.hard_block,
                    penalty=summary["penalty"],
                    violations=summary["violations"],
                    unmeasured=summary["unmeasured"],
                )
            )

        notes: list[str] = []
        if not limits:
            notes.append(
                "No enforceable regulatory constraints with numeric limits are active on this "
                "project (constraints may exist but carry no quantitative limit yet); report is "
                "advisory."
            )
        if evaluated == 0:
            notes.append("No experiments with recorded outcomes were available to evaluate.")

        return ReactionRegulatoryComplianceReport(
            reaction_project_id=project_id,
            enforced_constraint_count=len(limits),
            active_constraint_ids=sorted(
                {lim.constraint_id for lim in limits if lim.constraint_id is not None}
            ),
            constraint_bases=sorted({lim.basis for lim in limits}),
            experiments_evaluated=evaluated,
            non_compliant_experiment_count=non_compliant,
            items=items,
            notes=notes,
        )
