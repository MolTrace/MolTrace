from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ReactionExperiment,
    ReactionExperimentCreate,
    ReactionExperimentEvidence,
    ReactionExperimentSpectraCheckLink,
    ReactionExperimentUpdate,
    ReactionOptimizationRun,
    ReactionOptimizationRunRequest,
    ReactionOutcome,
    ReactionProject,
    ReactionProjectCreate,
    ReactionProjectUpdate,
    ReactionRecommendation,
    ReactionRecommendationCreate,
    ReactionRecommendationReview,
    ReactionVariable,
    ReactionVariableCreate,
    ReactionVariableUpdate,
)
from .orm import (
    AuditEventORM,
    ReactionExperimentORM,
    ReactionOptimizationRunORM,
    ReactionProjectORM,
    ReactionRecommendationORM,
    ReactionVariableORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckSessionORM,
    utcnow,
)


class ReactionError(ValueError):
    pass


@dataclass(frozen=True)
class ReactionActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_SAFE_NOTE = (
    "Reaction recommendations are heuristic, review-oriented suggestions. They do not "
    "guarantee success or prove optimality; human approval is required before use."
)
_OBJECTIVE_LABELS = {
    "maximize_yield": "yield_percent",
    "maximize_selectivity": "selectivity_percent",
    "minimize_impurity": "impurity_percent",
    "maximize_conversion": "conversion_percent",
    "multi_objective": "weighted yield/selectivity/impurity score",
}
_OUTCOME_FIELDS = {
    "yield_percent",
    "conversion_percent",
    "selectivity_percent",
    "impurity_percent",
    "isolated_yield_percent",
    "lcms_area_percent",
    "nmr_purity_percent",
    "e_factor",
    "atom_economy_percent",
    "pmi",
    "rme_percent",
    "green_score",
    "notes",
}


def create_project(
    session_factory: sessionmaker[Session],
    payload: ReactionProjectCreate,
    *,
    actor: ReactionActor,
) -> ReactionProject:
    with session_scope(session_factory) as session:
        owner_id = payload.owner_id if payload.owner_id is not None else actor.user_id
        row = ReactionProjectORM(
            name=payload.name,
            description=payload.description,
            objective=payload.objective,
            status=payload.status,
            target_product_name=payload.target_product_name,
            target_product_smiles=payload.target_product_smiles,
            owner_id=owner_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.project.create",
            message="Reaction optimization project created.",
            entity_type="reaction_project",
            entity_id=row.id,
            metadata={"objective": row.objective, "status": row.status},
        )
        return _project_to_record(row)


def list_projects(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[ReactionProject]:
    with session_scope(session_factory) as session:
        stmt = select(ReactionProjectORM).order_by(ReactionProjectORM.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(ReactionProjectORM.status == status)
        return [_project_to_record(row) for row in session.scalars(stmt).all()]


def get_project(session_factory: sessionmaker[Session], project_id: int) -> ReactionProject | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionProjectORM, project_id)
        return _project_to_record(row) if row is not None else None


def update_project(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionProjectUpdate,
    *,
    actor: ReactionActor,
) -> ReactionProject | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionProjectORM, project_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in (
            "name",
            "description",
            "objective",
            "status",
            "target_product_name",
            "target_product_smiles",
        ):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.project.update",
            message="Reaction optimization project updated.",
            entity_type="reaction_project",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update)},
        )
        return _project_to_record(row)


def create_variable(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionVariableCreate,
    *,
    actor: ReactionActor,
) -> ReactionVariable:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        _validate_variable(payload.variable_type, payload.min_value, payload.max_value)
        row = ReactionVariableORM(
            reaction_project_id=project_id,
            name=payload.name,
            variable_type=payload.variable_type,
            unit=payload.unit,
            allowed_values_json=_optional_json_dump(payload.allowed_values_json),
            min_value=payload.min_value,
            max_value=payload.max_value,
            default_value=_optional_json_dump(payload.default_value),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(f"Reaction variable already exists: {payload.name}") from exc
        _audit(
            session,
            actor=actor,
            event_type="reaction.variable.create",
            message="Reaction variable created.",
            entity_type="reaction_variable",
            entity_id=row.id,
            metadata={"project_id": project_id, "variable_type": row.variable_type},
        )
        return _variable_to_record(row)


def list_variables(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionVariable]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionVariableORM)
            .where(ReactionVariableORM.reaction_project_id == project_id)
            .order_by(ReactionVariableORM.id.asc())
        ).all()
        return [_variable_to_record(row) for row in rows]


def update_variable(
    session_factory: sessionmaker[Session],
    variable_id: int,
    payload: ReactionVariableUpdate,
    *,
    actor: ReactionActor,
) -> ReactionVariable | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionVariableORM, variable_id)
        if row is None:
            return None
        variable_type = payload.variable_type or row.variable_type
        min_value = payload.min_value if "min_value" in payload.model_fields_set else row.min_value
        max_value = payload.max_value if "max_value" in payload.model_fields_set else row.max_value
        _validate_variable(variable_type, min_value, max_value)
        update = payload.model_dump(exclude_unset=True)
        for field in ("name", "variable_type", "unit", "min_value", "max_value"):
            if field in update:
                setattr(row, field, update[field])
        if "allowed_values_json" in update:
            row.allowed_values_json = _optional_json_dump(update["allowed_values_json"])
        if "default_value" in update:
            row.default_value = _optional_json_dump(update["default_value"])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        _audit(
            session,
            actor=actor,
            event_type="reaction.variable.update",
            message="Reaction variable updated.",
            entity_type="reaction_variable",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update)},
        )
        return _variable_to_record(row)


def create_experiment(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionExperimentCreate,
    *,
    actor: ReactionActor,
) -> ReactionExperiment:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        _validate_conditions_against_variables(session, project_id, payload.conditions_json)
        _validate_outcome(payload.outcome_json)
        _verify_spectracheck_session(session, payload.linked_spectracheck_session_id)
        row = ReactionExperimentORM(
            reaction_project_id=project_id,
            experiment_code=payload.experiment_code,
            status=payload.status,
            conditions_json=_json_dump(payload.conditions_json),
            outcome_json=_json_dump(payload.outcome_json),
            linked_spectracheck_session_id=payload.linked_spectracheck_session_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(
                f"Experiment code already exists: {payload.experiment_code}"
            ) from exc
        _audit(
            session,
            actor=actor,
            event_type="reaction.experiment.create",
            message="Reaction experiment created.",
            entity_type="reaction_experiment",
            entity_id=row.id,
            metadata={"project_id": project_id, "status": row.status},
        )
        return _experiment_to_record(row)


def list_experiments(
    session_factory: sessionmaker[Session],
    project_id: int,
    *,
    status: str | None = None,
) -> list[ReactionExperiment]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        stmt = (
            select(ReactionExperimentORM)
            .where(ReactionExperimentORM.reaction_project_id == project_id)
            .order_by(ReactionExperimentORM.id.asc())
        )
        if status is not None:
            stmt = stmt.where(ReactionExperimentORM.status == status)
        return [_experiment_to_record(row) for row in session.scalars(stmt).all()]


def get_experiment(
    session_factory: sessionmaker[Session],
    experiment_id: int,
) -> ReactionExperiment | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExperimentORM, experiment_id)
        return _experiment_to_record(row) if row is not None else None


def update_experiment(
    session_factory: sessionmaker[Session],
    experiment_id: int,
    payload: ReactionExperimentUpdate,
    *,
    actor: ReactionActor,
) -> ReactionExperiment | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExperimentORM, experiment_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        conditions = update.get("conditions_json")
        if conditions is not None:
            _validate_conditions_against_variables(session, row.reaction_project_id, conditions)
            row.conditions_json = _json_dump(conditions)
        outcome = update.get("outcome_json")
        if outcome is not None:
            _validate_outcome(outcome)
            row.outcome_json = _json_dump(outcome)
        if "linked_spectracheck_session_id" in update:
            _verify_spectracheck_session(session, update["linked_spectracheck_session_id"])
            row.linked_spectracheck_session_id = update["linked_spectracheck_session_id"]
        for field in ("experiment_code", "status"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.experiment.update",
            message="Reaction experiment updated.",
            entity_type="reaction_experiment",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _experiment_to_record(row)


def run_optimization(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionOptimizationRunRequest,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationRun:
    with session_scope(session_factory) as session:
        project = _project_or_raise(session, project_id)
        variables = _project_variables(session, project_id)
        experiments = _project_experiments(session, project_id)
        objective = payload.objective or project.objective
        warnings: list[str] = []
        notes = [_SAFE_NOTE]
        if payload.model_type != "rule_based":
            warnings.append(
                f"{payload.model_type} is a placeholder; this MVP used transparent "
                "rule-based scoring and proposal generation."
            )
        recommendations, metrics, rec_warnings = _build_recommendations(
            project=project,
            variables=variables,
            experiments=experiments,
            objective=objective,
            max_recommendations=payload.max_recommendations,
        )
        warnings.extend(rec_warnings)
        completed_count = metrics["completed_experiment_count"]
        status = "requires_review" if completed_count < 3 else "succeeded"
        run = ReactionOptimizationRunORM(
            reaction_project_id=project_id,
            status=status,
            model_type=payload.model_type,
            objective=objective,
            input_experiment_count=len(experiments),
            recommendations_json=_json_dump(recommendations),
            metrics_json=_json_dump(metrics),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            finished_at=utcnow(),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(run)
        session.flush()
        for index, rec in enumerate(recommendations, start=1):
            row = ReactionRecommendationORM(
                reaction_project_id=project_id,
                optimization_run_id=run.id,
                rank=index,
                conditions_json=_json_dump(rec["conditions_json"]),
                predicted_outcome_json=_json_dump(rec["predicted_outcome_json"]),
                uncertainty_json=_json_dump(rec["uncertainty_json"]),
                rationale=rec["rationale"],
                label=rec["label"],
                status="proposed",
                metadata_json=_json_dump(rec.get("metadata_json", {})),
            )
            session.add(row)
        _audit(
            session,
            actor=actor,
            event_type="reaction.optimization.run",
            message="Reaction optimization recommendation run completed.",
            entity_type="reaction_optimization_run",
            entity_id=run.id,
            metadata={
                "project_id": project_id,
                "model_type": payload.model_type,
                "recommendation_count": len(recommendations),
            },
        )
        return _run_to_record(run)


def list_optimization_runs(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionOptimizationRun]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionOptimizationRunORM)
            .where(ReactionOptimizationRunORM.reaction_project_id == project_id)
            .order_by(ReactionOptimizationRunORM.id.desc())
        ).all()
        return [_run_to_record(row) for row in rows]


def get_optimization_run(
    session_factory: sessionmaker[Session],
    run_id: int,
) -> ReactionOptimizationRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionOptimizationRunORM, run_id)
        return _run_to_record(row) if row is not None else None


def create_recommendation(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionRecommendationCreate,
    *,
    actor: ReactionActor,
) -> ReactionRecommendation:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        if payload.status == "scheduled":
            raise ReactionError("Recommendations must be approved before scheduling.")
        if payload.status == "approved" and not (payload.reviewer_comment or payload.rationale):
            raise ReactionError("Approved recommendations require reviewer_comment or rationale.")
        row = ReactionRecommendationORM(
            reaction_project_id=project_id,
            optimization_run_id=None,
            rank=payload.rank,
            conditions_json=_json_dump(payload.conditions_json),
            predicted_outcome_json=_json_dump(payload.predicted_outcome_json),
            uncertainty_json=_json_dump(payload.uncertainty_json),
            rationale=payload.rationale,
            label=payload.label,
            status=payload.status,
            reviewer_name=payload.reviewer_name,
            reviewer_comment=payload.reviewer_comment,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.recommendation.create",
            message="Reaction recommendation created.",
            entity_type="reaction_recommendation",
            entity_id=row.id,
            metadata={"project_id": project_id, "label": row.label, "status": row.status},
        )
        return _recommendation_to_record(row)


def list_recommendations(
    session_factory: sessionmaker[Session],
    project_id: int,
    *,
    status: str | None = None,
) -> list[ReactionRecommendation]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        stmt = (
            select(ReactionRecommendationORM)
            .where(ReactionRecommendationORM.reaction_project_id == project_id)
            .order_by(ReactionRecommendationORM.rank.asc(), ReactionRecommendationORM.id.asc())
        )
        if status is not None:
            stmt = stmt.where(ReactionRecommendationORM.status == status)
        return [_recommendation_to_record(row) for row in session.scalars(stmt).all()]


def approve_recommendation(
    session_factory: sessionmaker[Session],
    recommendation_id: int,
    payload: ReactionRecommendationReview,
    *,
    actor: ReactionActor,
) -> ReactionRecommendation | None:
    comment = payload.reviewer_comment or payload.rationale
    if not comment:
        raise ReactionError("Recommendation approval requires reviewer_comment or rationale.")
    return _review_recommendation(
        session_factory,
        recommendation_id,
        status="approved",
        payload=payload,
        comment=comment,
        actor=actor,
    )


def reject_recommendation(
    session_factory: sessionmaker[Session],
    recommendation_id: int,
    payload: ReactionRecommendationReview,
    *,
    actor: ReactionActor,
) -> ReactionRecommendation | None:
    comment = payload.reviewer_comment or payload.rationale
    if not comment:
        raise ReactionError("Recommendation rejection requires reviewer_comment or rationale.")
    return _review_recommendation(
        session_factory,
        recommendation_id,
        status="rejected",
        payload=payload,
        comment=comment,
        actor=actor,
    )


def link_spectracheck_session(
    session_factory: sessionmaker[Session],
    experiment_id: int,
    payload: ReactionExperimentSpectraCheckLink,
    *,
    actor: ReactionActor,
) -> ReactionExperiment | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExperimentORM, experiment_id)
        if row is None:
            return None
        _verify_spectracheck_session(session, payload.session_id)
        row.linked_spectracheck_session_id = payload.session_id
        metadata = _json_dict(row.metadata_json)
        metadata.update(payload.metadata_json)
        row.metadata_json = _json_dump(metadata)
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.experiment.link_spectracheck",
            message="SpectraCheck session linked to reaction experiment.",
            entity_type="reaction_experiment",
            entity_id=row.id,
            metadata={"spectracheck_session_id": payload.session_id},
        )
        return _experiment_to_record(row)


def experiment_evidence(
    session_factory: sessionmaker[Session],
    experiment_id: int,
) -> ReactionExperimentEvidence | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExperimentORM, experiment_id)
        if row is None:
            return None
        warnings = []
        evidence_records: list[dict[str, Any]] = []
        linked_id = row.linked_spectracheck_session_id
        if linked_id is None:
            warnings.append("No SpectraCheck session is linked to this reaction experiment.")
        else:
            evidence_rows = session.scalars(
                select(SpectraCheckEvidenceRecordORM)
                .where(SpectraCheckEvidenceRecordORM.session_id == linked_id)
                .order_by(SpectraCheckEvidenceRecordORM.id.asc())
            ).all()
            evidence_records = [
                {
                    "id": evidence.id,
                    "layer": evidence.layer,
                    "title": evidence.title,
                    "status": evidence.status,
                    "score": evidence.score,
                    "label": evidence.label,
                    "summary": evidence.summary,
                    "warnings": _json_list(evidence.warnings_json),
                    "created_at": evidence.created_at.isoformat(),
                }
                for evidence in evidence_rows
            ]
    return ReactionExperimentEvidence(
        experiment_id=experiment_id,
        linked_spectracheck_session_id=linked_id,
        evidence_records=evidence_records,
        warnings=warnings,
        notes=[_SAFE_NOTE],
        metadata={"evidence_count": len(evidence_records)},
        human_review_required=True,
    )


def _review_recommendation(
    session_factory: sessionmaker[Session],
    recommendation_id: int,
    *,
    status: str,
    payload: ReactionRecommendationReview,
    comment: str,
    actor: ReactionActor,
) -> ReactionRecommendation | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionRecommendationORM, recommendation_id)
        if row is None:
            return None
        row.status = status
        row.reviewer_name = payload.reviewer_name or actor.email
        row.reviewer_comment = comment
        metadata = _json_dict(row.metadata_json)
        metadata.update(payload.metadata_json)
        row.metadata_json = _json_dump(metadata)
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type=f"reaction.recommendation.{status}",
            message=f"Reaction recommendation {status}.",
            entity_type="reaction_recommendation",
            entity_id=row.id,
            metadata={"project_id": row.reaction_project_id, "status": status},
        )
        return _recommendation_to_record(row)


def _build_recommendations(
    *,
    project: ReactionProjectORM,
    variables: list[ReactionVariableORM],
    experiments: list[ReactionExperimentORM],
    objective: str,
    max_recommendations: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    completed = [row for row in experiments if row.status == "completed"]
    scored = [
        scored_row
        for row in completed
        if (scored_row := _score_experiment(row, objective)) is not None
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)
    warnings: list[str] = []
    if len(completed) < 3:
        warnings.append(
            "Fewer than 3 completed experiments are available; recommendations are "
            "exploratory and require human review."
        )
    if not variables:
        warnings.append("No reaction variables are defined; condition proposals are limited.")
    recommendations: list[dict[str, Any]] = []
    seen: set[str] = set()

    if len(completed) >= 3 and scored:
        for scored_item in scored[:max_recommendations]:
            experiment = scored_item["experiment"]
            conditions = _json_dict(experiment.conditions_json)
            _append_recommendation(
                recommendations,
                seen,
                conditions=conditions,
                predicted_outcome={
                    "source_experiment_id": experiment.id,
                    "source_experiment_code": experiment.experiment_code,
                    "optimization_score": round(scored_item["score"], 3),
                    "score_basis": _OBJECTIVE_LABELS.get(objective, objective),
                    "observed_outcome": _json_dict(experiment.outcome_json),
                },
                uncertainty={
                    "label": "moderate",
                    "completed_experiment_count": len(completed),
                    "basis": "ranked_completed_outcomes",
                },
                rationale=(
                    f"Condition follows the best observed {objective} score from "
                    f"{experiment.experiment_code}. Treat as a human-reviewed follow-up "
                    "or control; success is not guaranteed."
                ),
                label="recommended_next_experiment",
            )
            if len(recommendations) >= max_recommendations:
                break

    exploratory = _exploratory_recommendations(
        variables=variables,
        experiments=experiments,
        completed_count=len(completed),
    )
    for rec in exploratory:
        if len(recommendations) >= max_recommendations:
            break
        _append_recommendation(recommendations, seen, **rec)

    if not recommendations:
        recommendations.append(
            {
                "conditions_json": {},
                "predicted_outcome_json": {
                    "optimization_score": None,
                    "score_basis": _OBJECTIVE_LABELS.get(objective, objective),
                },
                "uncertainty_json": {
                    "label": "high_uncertainty",
                    "completed_experiment_count": len(completed),
                },
                "rationale": (
                    "Insufficient structured variables or outcomes are available. Add "
                    "reviewed variables and completed outcomes before prioritizing."
                ),
                "label": "insufficient_data",
                "metadata_json": {"human_review_required": True},
            }
        )

    for index, rec in enumerate(recommendations, start=1):
        rec["rank"] = index

    metrics = {
        "objective": objective,
        "experiment_count": len(experiments),
        "completed_experiment_count": len(completed),
        "scored_experiment_count": len(scored),
        "best_score": round(scored[0]["score"], 3) if scored else None,
        "score_basis": _OBJECTIVE_LABELS.get(objective, objective),
        "model_behavior": "transparent_rule_based_mvp",
    }
    return recommendations, metrics, warnings


def _exploratory_recommendations(
    *,
    variables: list[ReactionVariableORM],
    experiments: list[ReactionExperimentORM],
    completed_count: int,
) -> list[dict[str, Any]]:
    base = _default_conditions(variables)
    recs: list[dict[str, Any]] = []
    for variable in variables:
        if variable.variable_type == "categorical":
            allowed_values = _json_value(variable.allowed_values_json) or []
            if not isinstance(allowed_values, list):
                continue
            seen = {
                str(_json_dict(exp.conditions_json).get(variable.name))
                for exp in experiments
                if variable.name in _json_dict(exp.conditions_json)
            }
            for value in allowed_values:
                if str(value) in seen:
                    continue
                conditions = {**base, variable.name: value}
                recs.append(
                    _exploratory_rec(
                        conditions,
                        rationale=(
                            f"{variable.name}={value!r} has not been tested in this "
                            "project. Suggested only as an exploratory condition."
                        ),
                        completed_count=completed_count,
                    )
                )
        elif variable.variable_type == "numeric":
            values = _numeric_probe_values(variable)
            for value, rationale in values:
                conditions = {**base, variable.name: value}
                recs.append(
                    _exploratory_rec(
                        conditions,
                        rationale=rationale,
                        completed_count=completed_count,
                    )
                )
        elif variable.variable_type == "boolean":
            seen = {
                bool(_json_dict(exp.conditions_json).get(variable.name))
                for exp in experiments
                if variable.name in _json_dict(exp.conditions_json)
            }
            for value in (False, True):
                if value not in seen:
                    recs.append(
                        _exploratory_rec(
                            {**base, variable.name: value},
                            rationale=(
                                f"{variable.name}={value} has not been tested yet. "
                                "Suggested for human-reviewed coverage."
                            ),
                            completed_count=completed_count,
                        )
                    )
    return recs


def _exploratory_rec(
    conditions: dict[str, Any],
    *,
    rationale: str,
    completed_count: int,
) -> dict[str, Any]:
    return {
        "conditions": conditions,
        "predicted_outcome": {
            "optimization_score": None,
            "score_basis": "not predicted in MVP",
        },
        "uncertainty": {
            "label": "low_data" if completed_count < 3 else "high_uncertainty",
            "completed_experiment_count": completed_count,
        },
        "rationale": rationale + " This is not a guarantee of success.",
        "label": "exploratory_condition",
    }


def _append_recommendation(
    recommendations: list[dict[str, Any]],
    seen: set[str],
    *,
    conditions: dict[str, Any] | None = None,
    predicted_outcome: dict[str, Any] | None = None,
    uncertainty: dict[str, Any] | None = None,
    conditions_json: dict[str, Any] | None = None,
    predicted_outcome_json: dict[str, Any] | None = None,
    uncertainty_json: dict[str, Any] | None = None,
    rationale: str,
    label: str,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    normalized_conditions = conditions_json if conditions_json is not None else conditions or {}
    key = json.dumps(normalized_conditions, sort_keys=True, default=str)
    if key in seen:
        return
    seen.add(key)
    recommendations.append(
        {
            "conditions_json": normalized_conditions,
            "predicted_outcome_json": predicted_outcome_json
            if predicted_outcome_json is not None
            else predicted_outcome or {},
            "uncertainty_json": uncertainty_json
            if uncertainty_json is not None
            else uncertainty or {},
            "rationale": rationale,
            "label": label,
            "metadata_json": metadata_json or {"human_review_required": True},
        }
    )


def _score_experiment(row: ReactionExperimentORM, objective: str) -> dict[str, Any] | None:
    outcome = _json_dict(row.outcome_json)
    if objective == "maximize_yield":
        value = _float_or_none(outcome.get("yield_percent"))
    elif objective == "maximize_selectivity":
        value = _float_or_none(outcome.get("selectivity_percent"))
    elif objective == "maximize_conversion":
        value = _float_or_none(outcome.get("conversion_percent"))
    elif objective == "minimize_impurity":
        impurity = _float_or_none(outcome.get("impurity_percent"))
        value = 100.0 - impurity if impurity is not None else None
    else:
        yield_value = _float_or_none(outcome.get("yield_percent")) or 0.0
        selectivity = _float_or_none(outcome.get("selectivity_percent")) or 0.0
        impurity = _float_or_none(outcome.get("impurity_percent")) or 0.0
        value = yield_value * 0.45 + selectivity * 0.35 + (100.0 - impurity) * 0.20
    if value is None:
        return None
    return {"experiment": row, "score": value}


def _numeric_probe_values(variable: ReactionVariableORM) -> list[tuple[float, str]]:
    if variable.min_value is None or variable.max_value is None:
        return []
    midpoint = round((variable.min_value + variable.max_value) / 2.0, 6)
    return [
        (
            midpoint,
            f"{variable.name} midpoint explores the center of the configured range.",
        ),
        (
            variable.min_value,
            f"{variable.name} lower boundary checks range sensitivity under review.",
        ),
        (
            variable.max_value,
            f"{variable.name} upper boundary checks range sensitivity under review.",
        ),
    ]


def _default_conditions(variables: list[ReactionVariableORM]) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    for variable in variables:
        default = _json_value(variable.default_value)
        if default is not None:
            conditions[variable.name] = default
        elif variable.variable_type == "numeric":
            if variable.min_value is not None and variable.max_value is not None:
                conditions[variable.name] = round((variable.min_value + variable.max_value) / 2, 6)
        elif variable.variable_type == "categorical":
            allowed = _json_value(variable.allowed_values_json)
            if isinstance(allowed, list) and allowed:
                conditions[variable.name] = allowed[0]
        elif variable.variable_type == "boolean":
            conditions[variable.name] = False
    return conditions


def _project_variables(session: Session, project_id: int) -> list[ReactionVariableORM]:
    return list(
        session.scalars(
            select(ReactionVariableORM)
            .where(ReactionVariableORM.reaction_project_id == project_id)
            .order_by(ReactionVariableORM.id.asc())
        ).all()
    )


def _project_experiments(session: Session, project_id: int) -> list[ReactionExperimentORM]:
    return list(
        session.scalars(
            select(ReactionExperimentORM)
            .where(ReactionExperimentORM.reaction_project_id == project_id)
            .order_by(ReactionExperimentORM.id.asc())
        ).all()
    )


def _project_or_raise(session: Session, project_id: int) -> ReactionProjectORM:
    row = session.get(ReactionProjectORM, project_id)
    if row is None:
        raise KeyError("Reaction project not found.")
    return row


def _verify_spectracheck_session(session: Session, session_id: int | None) -> None:
    if session_id is None:
        return
    if session.get(SpectraCheckSessionORM, session_id) is None:
        raise KeyError("SpectraCheck session not found.")


def _validate_variable(
    variable_type: str,
    min_value: float | None,
    max_value: float | None,
) -> None:
    if variable_type == "numeric":
        if min_value is None or max_value is None:
            raise ReactionError("Numeric reaction variables require min_value and max_value.")
        if min_value > max_value:
            raise ReactionError("Numeric reaction variable min_value cannot exceed max_value.")


def _validate_conditions_against_variables(
    session: Session,
    project_id: int,
    conditions: dict[str, Any],
) -> None:
    variables = {row.name: row for row in _project_variables(session, project_id)}
    for key, value in conditions.items():
        variable = variables.get(str(key))
        if variable is None:
            continue
        if variable.variable_type == "numeric":
            numeric = _float_or_none(value)
            if numeric is None:
                raise ReactionError(f"Condition {key} must be numeric.")
            if variable.min_value is not None and numeric < variable.min_value:
                raise ReactionError(f"Condition {key} is below min_value.")
            if variable.max_value is not None and numeric > variable.max_value:
                raise ReactionError(f"Condition {key} is above max_value.")
        if variable.variable_type == "categorical" and variable.allowed_values_json:
            allowed = _json_value(variable.allowed_values_json)
            if isinstance(allowed, list) and value not in allowed:
                raise ReactionError(f"Condition {key} is not in allowed_values_json.")


def _validate_outcome(outcome: dict[str, Any]) -> None:
    for field in _OUTCOME_FIELDS - {"notes"}:
        if field in outcome:
            value = _float_or_none(outcome[field])
            if value is None or value < 0 or value > 100:
                raise ReactionError(f"Outcome {field} must be a percentage from 0 to 100.")


def _project_to_record(row: ReactionProjectORM) -> ReactionProject:
    return ReactionProject(
        id=row.id,
        name=row.name,
        description=row.description,
        objective=row.objective,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        target_product_name=row.target_product_name,
        target_product_smiles=row.target_product_smiles,
        owner_id=row.owner_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        metadata={"human_review_language": True},
        human_review_required=True,
    )


def _variable_to_record(row: ReactionVariableORM) -> ReactionVariable:
    return ReactionVariable(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        name=row.name,
        variable_type=row.variable_type,  # type: ignore[arg-type]
        unit=row.unit,
        allowed_values_json=_json_value(row.allowed_values_json),
        min_value=row.min_value,
        max_value=row.max_value,
        default_value=_json_value(row.default_value),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _experiment_to_record(row: ReactionExperimentORM) -> ReactionExperiment:
    outcome_json = _json_dict(row.outcome_json)
    return ReactionExperiment(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        experiment_code=row.experiment_code,
        status=row.status,  # type: ignore[arg-type]
        conditions_json=_json_dict(row.conditions_json),
        outcome_json=outcome_json,
        outcome=_outcome_from_json(outcome_json),
        linked_spectracheck_session_id=row.linked_spectracheck_session_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        metadata={"spectracheck_linked": row.linked_spectracheck_session_id is not None},
        human_review_required=True,
    )


def _run_to_record(row: ReactionOptimizationRunORM) -> ReactionOptimizationRun:
    return ReactionOptimizationRun(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        status=row.status,  # type: ignore[arg-type]
        model_type=row.model_type,  # type: ignore[arg-type]
        objective=row.objective,  # type: ignore[arg-type]
        input_experiment_count=row.input_experiment_count,
        recommendations_json=_json_list(row.recommendations_json),
        metrics_json=_json_dict(row.metrics_json),
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=[str(item) for item in _json_list(row.warnings_json)],
        notes=[str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE],
        metadata={"human_review_language": True},
        human_review_required=True,
    )


def _recommendation_to_record(row: ReactionRecommendationORM) -> ReactionRecommendation:
    return ReactionRecommendation(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        optimization_run_id=row.optimization_run_id,
        rank=row.rank,
        conditions_json=_json_dict(row.conditions_json),
        predicted_outcome_json=_json_dict(row.predicted_outcome_json),
        uncertainty_json=_json_dict(row.uncertainty_json),
        rationale=row.rationale,
        label=row.label,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        metadata={"approved": row.status == "approved"},
        human_review_required=row.status not in {"approved", "rejected", "completed"},
    )


def _outcome_from_json(value: dict[str, Any]) -> ReactionOutcome:
    return ReactionOutcome(**{key: value[key] for key in _OUTCOME_FIELDS if key in value})


def _audit(
    session: Session,
    *,
    actor: ReactionActor,
    event_type: str,
    message: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_json_dump(value: Any | None) -> str | None:
    if value is None:
        return None
    return _json_dump(value)


def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


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


def _json_value(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
