from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ReactionAcquisitionCandidate,
    ReactionBayesianOptimizationRun,
    ReactionBayesianOptimizationRunRequest,
    ReactionCostProfile,
    ReactionCostProfileCreate,
    ReactionCostProfileUpdate,
    ReactionDesignSpace,
    ReactionDesignSpaceCreate,
    ReactionDesignSpaceUpdate,
    ReactionObjectiveProfile,
    ReactionObjectiveProfileCreate,
    ReactionObjectiveProfileUpdate,
    ReactionOptimizationBenchmarkRequest,
    ReactionOptimizationBenchmarkRun,
    ReactionRecommendationBatch,
    ReactionRecommendationBatchCreate,
    ReactionSafetyConstraintProfile,
    ReactionSafetyConstraintProfileCreate,
    ReactionSafetyConstraintProfileUpdate,
    ReactionSurrogateModelRecord,
)
from .orm import (
    AuditEventORM,
    ReactionAcquisitionCandidateORM,
    ReactionBayesianOptimizationRunORM,
    ReactionCostProfileORM,
    ReactionDesignSpaceORM,
    ReactionExperimentORM,
    ReactionOptimizationBenchmarkRunORM,
    ReactionObjectiveProfileORM,
    ReactionProjectORM,
    ReactionRecommendationBatchORM,
    ReactionRecommendationORM,
    ReactionSafetyConstraintProfileORM,
    ReactionSurrogateModelRecordORM,
    ReactionVariableORM,
    utcnow,
)
from .reaction_store import ReactionActor, ReactionError


_SAFE_NOTE = (
    "Bayesian optimization recommendations are advisory, data-efficient proposals. "
    "They do not guarantee an optimum and require human review before scheduling."
)
_LLM_DISABLED_WARNING = "LLM-guided optimization is not enabled in this deployment."
_MODEL_VERSION = "phase50.1"
_PERCENT_FIELDS = {
    "yield_percent",
    "selectivity_percent",
    "impurity_percent",
    "conversion_percent",
    "isolated_yield_percent",
    "lcms_area_percent",
    "nmr_purity_percent",
}


@dataclass(frozen=True)
class _TrainingExample:
    experiment_id: int
    experiment_code: str
    conditions: dict[str, Any]
    outcome: dict[str, Any]
    score: float
    status: str


@dataclass(frozen=True)
class _ConditionDomain:
    numeric: dict[str, list[float]]
    numeric_ranges: dict[str, tuple[float, float]]
    categorical: dict[str, list[Any]]
    boolean: dict[str, list[bool]]
    fixed: dict[str, Any]
    excluded: list[dict[str, Any]]


@dataclass(frozen=True)
class _CostEstimate:
    total: float | None
    penalty: float
    unavailable: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class _SafetyAssessment:
    status: str
    reasons: list[str]
    required_controls: list[str]


def create_design_space(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionDesignSpaceCreate,
    *,
    actor: ReactionActor,
) -> ReactionDesignSpace:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionDesignSpaceORM(
            reaction_project_id=project_id,
            variables_json=_json_dump(payload.variables_json),
            categorical_variables_json=_json_dump(payload.categorical_variables_json),
            numeric_variables_json=_json_dump(payload.numeric_variables_json),
            boolean_variables_json=_json_dump(payload.boolean_variables_json),
            fixed_conditions_json=_json_dump(payload.fixed_conditions_json),
            excluded_conditions_json=_json_dump(payload.excluded_conditions_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.design_space.create",
            message="Reaction BO design space created.",
            entity_type="reaction_design_space",
            entity_id=row.id,
            metadata={"project_id": project_id},
        )
        return _design_space_to_record(row)


def get_design_space(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> ReactionDesignSpace | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_design_space(session, project_id)
        return _design_space_to_record(row) if row is not None else None


def patch_design_space(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionDesignSpaceUpdate,
    *,
    actor: ReactionActor,
) -> ReactionDesignSpace | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_design_space(session, project_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in (
            "variables_json",
            "categorical_variables_json",
            "numeric_variables_json",
            "boolean_variables_json",
            "fixed_conditions_json",
            "excluded_conditions_json",
            "metadata_json",
        ):
            if field in update:
                setattr(row, field, _json_dump(update[field] if update[field] is not None else {}))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.design_space.update",
            message="Reaction BO design space updated.",
            entity_type="reaction_design_space",
            entity_id=row.id,
            metadata={"project_id": project_id, "updated_fields": sorted(update)},
        )
        return _design_space_to_record(row)


def create_objective_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionObjectiveProfileCreate,
    *,
    actor: ReactionActor,
) -> ReactionObjectiveProfile:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionObjectiveProfileORM(
            reaction_project_id=project_id,
            objective_type=payload.objective_type,
            weights_json=_json_dump(payload.weights_json),
            target_thresholds_json=_json_dump(payload.target_thresholds_json),
            hard_constraints_json=_json_dump(payload.hard_constraints_json),
            soft_constraints_json=_json_dump(payload.soft_constraints_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.objective_profile.create",
            message="Reaction BO objective profile created.",
            entity_type="reaction_objective_profile",
            entity_id=row.id,
            metadata={"project_id": project_id, "objective_type": row.objective_type},
        )
        return _objective_profile_to_record(row)


def get_objective_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> ReactionObjectiveProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_objective_profile(session, project_id)
        return _objective_profile_to_record(row) if row is not None else None


def patch_objective_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionObjectiveProfileUpdate,
    *,
    actor: ReactionActor,
) -> ReactionObjectiveProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_objective_profile(session, project_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        if "objective_type" in update and update["objective_type"] is not None:
            row.objective_type = update["objective_type"]
        for field in (
            "weights_json",
            "target_thresholds_json",
            "hard_constraints_json",
            "soft_constraints_json",
            "metadata_json",
        ):
            if field in update:
                setattr(row, field, _json_dump(update[field] or {}))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.objective_profile.update",
            message="Reaction BO objective profile updated.",
            entity_type="reaction_objective_profile",
            entity_id=row.id,
            metadata={"project_id": project_id, "updated_fields": sorted(update)},
        )
        return _objective_profile_to_record(row)


def create_cost_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionCostProfileCreate,
    *,
    actor: ReactionActor,
) -> ReactionCostProfile:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionCostProfileORM(
            reaction_project_id=project_id,
            reagent_costs_json=_json_dump(payload.reagent_costs_json),
            solvent_costs_json=_json_dump(payload.solvent_costs_json),
            catalyst_costs_json=_json_dump(payload.catalyst_costs_json),
            ligand_costs_json=_json_dump(payload.ligand_costs_json),
            availability_json=_json_dump(payload.availability_json),
            max_cost_per_experiment=payload.max_cost_per_experiment,
            cost_penalty_weight=payload.cost_penalty_weight,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.cost_profile.create",
            message="Reaction BO cost profile created.",
            entity_type="reaction_cost_profile",
            entity_id=row.id,
            metadata={"project_id": project_id},
        )
        return _cost_profile_to_record(row)


def get_cost_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> ReactionCostProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_cost_profile(session, project_id)
        return _cost_profile_to_record(row) if row is not None else None


def patch_cost_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionCostProfileUpdate,
    *,
    actor: ReactionActor,
) -> ReactionCostProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_cost_profile(session, project_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in (
            "reagent_costs_json",
            "solvent_costs_json",
            "catalyst_costs_json",
            "ligand_costs_json",
            "availability_json",
            "metadata_json",
        ):
            if field in update:
                setattr(row, field, _json_dump(update[field] or {}))
        for field in ("max_cost_per_experiment", "cost_penalty_weight"):
            if field in update:
                setattr(row, field, update[field])
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.cost_profile.update",
            message="Reaction BO cost profile updated.",
            entity_type="reaction_cost_profile",
            entity_id=row.id,
            metadata={"project_id": project_id, "updated_fields": sorted(update)},
        )
        return _cost_profile_to_record(row)


def create_safety_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionSafetyConstraintProfileCreate,
    *,
    actor: ReactionActor,
) -> ReactionSafetyConstraintProfile:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionSafetyConstraintProfileORM(
            reaction_project_id=project_id,
            blocked_reagents_json=_json_dump(payload.blocked_reagents_json),
            blocked_solvents_json=_json_dump(payload.blocked_solvents_json),
            max_temperature_c=payload.max_temperature_c,
            max_pressure_bar=payload.max_pressure_bar,
            incompatible_pairs_json=_json_dump(payload.incompatible_pairs_json),
            required_controls_json=_json_dump(payload.required_controls_json),
            safety_notes_json=_json_dump(payload.safety_notes_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.safety_profile.create",
            message="Reaction BO safety profile created.",
            entity_type="reaction_safety_constraint_profile",
            entity_id=row.id,
            metadata={"project_id": project_id},
        )
        return _safety_profile_to_record(row)


def get_safety_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> ReactionSafetyConstraintProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_safety_profile(session, project_id)
        return _safety_profile_to_record(row) if row is not None else None


def patch_safety_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionSafetyConstraintProfileUpdate,
    *,
    actor: ReactionActor,
) -> ReactionSafetyConstraintProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_safety_profile(session, project_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in (
            "blocked_reagents_json",
            "blocked_solvents_json",
            "incompatible_pairs_json",
            "required_controls_json",
            "safety_notes_json",
            "metadata_json",
        ):
            if field in update:
                setattr(row, field, _json_dump(update[field] if update[field] is not None else []))
        for field in ("max_temperature_c", "max_pressure_bar"):
            if field in update:
                setattr(row, field, update[field])
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.safety_profile.update",
            message="Reaction BO safety profile updated.",
            entity_type="reaction_safety_constraint_profile",
            entity_id=row.id,
            metadata={"project_id": project_id, "updated_fields": sorted(update)},
        )
        return _safety_profile_to_record(row)


def run_bayesian_optimization(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionBayesianOptimizationRunRequest,
    *,
    actor: ReactionActor,
) -> ReactionBayesianOptimizationRun:
    with session_scope(session_factory) as session:
        project = _project_or_raise(session, project_id)
        variables = _project_variables(session, project_id)
        experiments = _project_experiments(session, project_id)
        design_space = _latest_design_space(session, project_id)
        objective_profile = _latest_objective_profile(session, project_id)
        cost_profile = _latest_cost_profile(session, project_id)
        safety_profile = _latest_safety_profile(session, project_id)

        objective_type = (
            objective_profile.objective_type if objective_profile is not None else project.objective
        )
        weights = _json_dict(objective_profile.weights_json) if objective_profile else {}
        warnings: list[str] = []
        notes = [_SAFE_NOTE]
        if payload.algorithm == "llm_guided_advisory":
            warnings.append(_LLM_DISABLED_WARNING)
        if payload.cost_aware and cost_profile is None:
            warnings.append("Cost-aware mode requested but no cost profile exists; cost penalty is zero.")
        if payload.safety_aware and safety_profile is None:
            warnings.append("Safety-aware mode requested but no safety profile exists; safety status is unknown.")

        training, training_warnings = _training_examples(
            experiments,
            objective_type=objective_type,
            weights=weights,
            include_negative=payload.include_negative_outcomes,
        )
        warnings.extend(training_warnings)
        domain = _build_domain(design_space, variables, experiments)
        candidate_conditions = _generate_candidate_conditions(
            domain,
            max_candidates=max(payload.candidate_count, payload.batch_size * 4),
        )
        if not candidate_conditions:
            candidate_conditions = [_default_candidate_from_experiments(experiments)]
            warnings.append("No enumerated design-space candidates were available; using a fallback shell.")

        ranked, diagnostics, model_type, feature_encoding, model_warnings = _rank_candidates(
            training=training,
            candidate_conditions=candidate_conditions,
            domain=domain,
            objective_type=objective_type,
            weights=weights,
            algorithm=payload.algorithm,
            batch_size=payload.batch_size,
            exploration_weight=payload.exploration_weight,
            cost_aware=payload.cost_aware,
            safety_aware=payload.safety_aware,
            cost_profile=cost_profile,
            safety_profile=safety_profile,
        )
        warnings.extend(model_warnings)
        status = "requires_review" if len(training) < 5 else "succeeded"
        if payload.algorithm == "llm_guided_advisory":
            status = "requires_review"
        diagnostics.update(
            {
                "objective_type": objective_type,
                "weights": weights,
                "completed_experiments_used": len(training),
                "failed_or_excluded_included_as_negative": payload.include_negative_outcomes,
                "guaranteed_optimum": False,
                "human_review_required": True,
            }
        )
        run = ReactionBayesianOptimizationRunORM(
            reaction_project_id=project_id,
            status=status,
            algorithm=payload.algorithm,
            batch_size=payload.batch_size,
            exploration_weight=payload.exploration_weight,
            cost_aware=payload.cost_aware,
            safety_aware=payload.safety_aware,
            input_experiment_count=len(training),
            candidate_count=diagnostics.get("evaluated_candidate_count", len(candidate_conditions)),
            recommendations_json="[]",
            diagnostics_json=_json_dump(diagnostics),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            finished_at=utcnow(),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(run)
        session.flush()

        surrogate = ReactionSurrogateModelRecordORM(
            reaction_project_id=project_id,
            bo_run_id=run.id,
            model_type=model_type,
            model_version=_MODEL_VERSION,
            training_experiment_count=len(training),
            feature_encoding_json=_json_dump(feature_encoding),
            objective_summary_json=_json_dump(
                {
                    "objective_type": objective_type,
                    "weights": weights,
                    "best_observed_objective": diagnostics.get("best_observed_objective"),
                }
            ),
            metrics_json=_json_dump(diagnostics.get("model_metrics", {})),
            warnings_json=_json_dump(warnings),
            metadata_json=_json_dump({"algorithm": payload.algorithm}),
        )
        session.add(surrogate)
        session.flush()

        candidate_rows: list[ReactionAcquisitionCandidateORM] = []
        for rank, item in enumerate(ranked[: payload.batch_size], start=1):
            metadata = dict(item.get("metadata_json") or {})
            metadata.update(
                {
                    "human_review_required": True,
                    "bo_run_id": run.id,
                    "model_type": model_type,
                    "algorithm": payload.algorithm,
                }
            )
            candidate = ReactionAcquisitionCandidateORM(
                bo_run_id=run.id,
                rank=rank,
                conditions_json=_json_dump(item["conditions_json"]),
                predicted_score=item.get("predicted_score"),
                expected_improvement=item.get("expected_improvement"),
                uncertainty=item.get("uncertainty"),
                estimated_cost=item.get("estimated_cost"),
                safety_status=item.get("safety_status", "unknown"),
                acquisition_score=item.get("acquisition_score"),
                rationale=item["rationale"],
                label=item["label"],
                metadata_json=_json_dump(metadata),
            )
            session.add(candidate)
            session.flush()
            recommendation = ReactionRecommendationORM(
                reaction_project_id=project_id,
                optimization_run_id=None,
                rank=rank,
                conditions_json=candidate.conditions_json,
                predicted_outcome_json=_json_dump(
                    {
                        "predicted_score": candidate.predicted_score,
                        "expected_improvement": candidate.expected_improvement,
                        "acquisition_score": candidate.acquisition_score,
                        "model_type": model_type,
                    }
                ),
                uncertainty_json=_json_dump(
                    {
                        "uncertainty": candidate.uncertainty,
                        "confidence_label": metadata.get("confidence_label", "requires_review"),
                    }
                ),
                rationale=candidate.rationale,
                label=candidate.label,
                status="proposed",
                metadata_json=_json_dump(
                    {
                        "source": "phase50_bayesian_optimization",
                        "bo_run_id": run.id,
                        "acquisition_candidate_id": candidate.id,
                        "human_review_required": True,
                    }
                ),
            )
            session.add(recommendation)
            session.flush()
            metadata["recommendation_id"] = recommendation.id
            candidate.metadata_json = _json_dump(metadata)
            candidate_rows.append(candidate)

        run.recommendations_json = _json_dump(
            [_candidate_summary(row) for row in candidate_rows]
        )
        diagnostics["surrogate_model_record_id"] = surrogate.id
        run.diagnostics_json = _json_dump(diagnostics)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.bo.run",
            message="Reaction Bayesian optimization run completed.",
            entity_type="reaction_bayesian_optimization_run",
            entity_id=run.id,
            metadata={
                "project_id": project_id,
                "algorithm": payload.algorithm,
                "model_type": model_type,
                "recommendation_count": len(candidate_rows),
                "human_review_required": True,
            },
        )
        return _bo_run_to_record(run, candidate_rows, model_type=model_type)


def list_bayesian_optimization_runs(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionBayesianOptimizationRun]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionBayesianOptimizationRunORM)
            .where(ReactionBayesianOptimizationRunORM.reaction_project_id == project_id)
            .order_by(ReactionBayesianOptimizationRunORM.id.desc())
        ).all()
        return [_bo_run_to_record(row, _bo_candidates(session, row.id), model_type=_bo_model_type(session, row.id)) for row in rows]


def get_bayesian_optimization_run(
    session_factory: sessionmaker[Session],
    bo_run_id: int,
) -> ReactionBayesianOptimizationRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionBayesianOptimizationRunORM, bo_run_id)
        if row is None:
            return None
        return _bo_run_to_record(row, _bo_candidates(session, row.id), model_type=_bo_model_type(session, row.id))


def create_recommendation_batch(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionRecommendationBatchCreate,
    *,
    actor: ReactionActor,
) -> ReactionRecommendationBatch:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        recommendations = list(payload.recommendations_json)
        if payload.bo_run_id is not None:
            run = session.get(ReactionBayesianOptimizationRunORM, payload.bo_run_id)
            if run is None or run.reaction_project_id != project_id:
                raise KeyError("Reaction Bayesian optimization run not found.")
            if not recommendations:
                recommendations = [_candidate_summary(row) for row in _bo_candidates(session, run.id)]
        row = ReactionRecommendationBatchORM(
            reaction_project_id=project_id,
            bo_run_id=payload.bo_run_id,
            status="proposed",
            recommendations_json=_json_dump(recommendations),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.recommendation_batch.create",
            message="Reaction recommendation batch proposed.",
            entity_type="reaction_recommendation_batch",
            entity_id=row.id,
            metadata={"project_id": project_id, "bo_run_id": payload.bo_run_id},
        )
        return _recommendation_batch_to_record(row)


def list_recommendation_batches(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionRecommendationBatch]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionRecommendationBatchORM)
            .where(ReactionRecommendationBatchORM.reaction_project_id == project_id)
            .order_by(ReactionRecommendationBatchORM.id.desc())
        ).all()
        return [_recommendation_batch_to_record(row) for row in rows]


def get_recommendation_batch(
    session_factory: sessionmaker[Session],
    batch_id: int,
) -> ReactionRecommendationBatch | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionRecommendationBatchORM, batch_id)
        return _recommendation_batch_to_record(row) if row is not None else None


def run_benchmark(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionOptimizationBenchmarkRequest,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationBenchmarkRun:
    with session_scope(session_factory) as session:
        project = _project_or_raise(session, project_id)
        objective_profile = _latest_objective_profile(session, project_id)
        objective_type = (
            objective_profile.objective_type if objective_profile is not None else project.objective
        )
        weights = _json_dict(objective_profile.weights_json) if objective_profile is not None else {}
        experiments = _project_experiments(session, project_id)
        training, warnings = _training_examples(
            experiments,
            objective_type=objective_type,
            weights=weights,
            include_negative=False,
        )
        trajectory: list[dict[str, Any]] = []
        if len(training) < 5:
            warnings.append(
                "Fewer than 5 completed experiments are available; benchmark is descriptive only."
            )
        sorted_training = sorted(training, key=lambda item: item.experiment_id)
        best_so_far: float | None = None
        for index, example in enumerate(sorted_training, start=1):
            best_so_far = example.score if best_so_far is None else max(best_so_far, example.score)
            trajectory.append(
                {
                    "step": index,
                    "experiment_id": example.experiment_id,
                    "experiment_code": example.experiment_code,
                    "objective_score": round(example.score, 6),
                    "best_so_far": round(best_so_far, 6),
                }
            )
        best_observed = max((item.score for item in training), default=None)
        latest_score = sorted_training[-1].score if sorted_training else None
        simple_regret = (
            round(max(0.0, best_observed - latest_score), 6)
            if best_observed is not None and latest_score is not None
            else None
        )
        metrics = {
            "best_observed_objective": round(best_observed, 6) if best_observed is not None else None,
            "recommendation_rank": _rank_of_latest_best(sorted_training),
            "simple_regret": simple_regret,
            "number_of_experiments_used": len(training),
            "objective_type": objective_type,
        }
        row = ReactionOptimizationBenchmarkRunORM(
            reaction_project_id=project_id,
            benchmark_name=payload.benchmark_name,
            algorithm=payload.algorithm,
            status="succeeded" if training else "requires_review",
            metrics_json=_json_dump(metrics),
            trajectory_json=_json_dump(trajectory),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_SAFE_NOTE]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.optimization_benchmark.run",
            message="Reaction optimization benchmark run completed.",
            entity_type="reaction_optimization_benchmark_run",
            entity_id=row.id,
            metadata={"project_id": project_id, "algorithm": payload.algorithm},
        )
        return _benchmark_to_record(row)


def list_benchmark_runs(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionOptimizationBenchmarkRun]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionOptimizationBenchmarkRunORM)
            .where(ReactionOptimizationBenchmarkRunORM.reaction_project_id == project_id)
            .order_by(ReactionOptimizationBenchmarkRunORM.id.desc())
        ).all()
        return [_benchmark_to_record(row) for row in rows]


def _rank_candidates(
    *,
    training: list[_TrainingExample],
    candidate_conditions: list[dict[str, Any]],
    domain: _ConditionDomain,
    objective_type: str,
    weights: dict[str, Any],
    algorithm: str,
    batch_size: int,
    exploration_weight: float | None,
    cost_aware: bool,
    safety_aware: bool,
    cost_profile: ReactionCostProfileORM | None,
    safety_profile: ReactionSafetyConstraintProfileORM | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str, dict[str, Any], list[str]]:
    warnings: list[str] = []
    feature_encoding = _build_feature_encoding(domain, training)
    y_best = max((item.score for item in training), default=None)
    model_type = "rule_based_fallback"
    model_metrics: dict[str, Any] = {}
    predictions: list[dict[str, Any]]

    if len(training) < 5:
        warnings.append(
            "Fewer than 5 completed experiments are available; using exploratory fallback."
        )
        predictions = _fallback_predictions(training, candidate_conditions, domain, low_data=True)
    elif algorithm == "llm_guided_advisory":
        warnings.append(_LLM_DISABLED_WARNING)
        predictions = _fallback_predictions(training, candidate_conditions, domain, low_data=False)
    elif algorithm.startswith("gaussian_process"):
        model_type, predictions, model_metrics, model_warning = _sklearn_gp_predictions(
            training,
            candidate_conditions,
            feature_encoding,
            algorithm=algorithm,
            exploration_weight=exploration_weight,
        )
        if model_warning:
            warnings.append(model_warning)
    elif algorithm == "random_forest_ei":
        model_type, predictions, model_metrics, model_warning = _sklearn_forest_predictions(
            training,
            candidate_conditions,
            feature_encoding,
        )
        if model_warning:
            warnings.append(model_warning)
    elif algorithm == "tpe_like":
        model_type = "tpe_like"
        predictions = _tpe_like_predictions(training, candidate_conditions, domain)
    else:
        predictions = _fallback_predictions(training, candidate_conditions, domain, low_data=False)

    scored: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for prediction in predictions:
        conditions = prediction["conditions_json"]
        safety = _assess_safety(conditions, safety_profile)
        cost = _estimate_cost(conditions, cost_profile)
        acquisition = prediction.get("acquisition_score")
        if acquisition is None:
            predicted = prediction.get("predicted_score")
            acquisition = predicted if predicted is not None else 0.0
        if cost_aware:
            acquisition -= cost.penalty
        if cost.unavailable:
            acquisition -= 50.0
        item = {
            **prediction,
            "estimated_cost": cost.total,
            "safety_status": safety.status,
            "acquisition_score": round(float(acquisition), 6),
            "metadata_json": {
                **prediction.get("metadata_json", {}),
                "safety_reasons": safety.reasons,
                "required_controls": safety.required_controls,
                "cost_details": cost.details,
                "confidence_label": _confidence_label(prediction, len(training)),
            },
        }
        item["label"] = _candidate_label(
            item,
            training_count=len(training),
            cost_aware=cost_aware,
            safety_status=safety.status,
        )
        item["rationale"] = _candidate_rationale(
            item,
            objective_type=objective_type,
            model_type=model_type,
            cost_aware=cost_aware,
            safety=safety,
            cost=cost,
        )
        if safety_aware and safety.status == "blocked":
            blocked.append(item)
            continue
        scored.append(item)

    scored.sort(key=lambda item: (item["acquisition_score"], -(item.get("estimated_cost") or 0)), reverse=True)
    if not scored and blocked:
        blocked.sort(key=lambda item: item["acquisition_score"], reverse=True)
        scored = blocked[:batch_size]
        warnings.append("All enumerated candidates violate safety constraints; only blocked records were returned.")
    if not scored:
        scored = [
            {
                "conditions_json": {},
                "predicted_score": None,
                "expected_improvement": None,
                "uncertainty": None,
                "estimated_cost": None,
                "safety_status": "unknown",
                "acquisition_score": None,
                "rationale": (
                    "Insufficient structured conditions were available. Add a design space and "
                    "completed experiments before scheduling; human review is required."
                ),
                "label": "insufficient_data",
                "metadata_json": {"confidence_label": "insufficient_data"},
            }
        ]
    diagnostics = {
        "best_observed_objective": round(y_best, 6) if y_best is not None else None,
        "evaluated_candidate_count": len(predictions),
        "safety_blocked_candidate_count": len(blocked),
        "model_metrics": model_metrics,
        "feature_encoding": feature_encoding,
        "scalarization": _objective_summary(objective_type, weights),
    }
    return scored, diagnostics, model_type, feature_encoding, warnings


def _sklearn_gp_predictions(
    training: list[_TrainingExample],
    candidates: list[dict[str, Any]],
    encoding: dict[str, Any],
    *,
    algorithm: str,
    exploration_weight: float | None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], str | None]:
    try:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern, WhiteKernel
    except Exception as exc:  # pragma: no cover - depends on optional deployment package
        return (
            "rule_based_fallback",
            _fallback_predictions(training, candidates, _domain_from_encoding(encoding), low_data=False),
            {"fallback_reason": "sklearn_unavailable"},
            f"sklearn GaussianProcessRegressor unavailable; used rule-based fallback ({exc}).",
        )
    x_train = [_encode_conditions(item.conditions, encoding) for item in training]
    y_train = [item.score for item in training]
    x_candidates = [_encode_conditions(conditions, encoding) for conditions in candidates]
    try:
        kernel = Matern(nu=2.5) + WhiteKernel(noise_level=1e-3)
        model = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=50)
        model.fit(x_train, y_train)
        means, stds = model.predict(x_candidates, return_std=True)
    except Exception as exc:  # pragma: no cover - optional model branch
        return (
            "rule_based_fallback",
            _fallback_predictions(training, candidates, _domain_from_encoding(encoding), low_data=False),
            {"fallback_reason": "gp_fit_failed"},
            f"Gaussian process fit failed; used rule-based fallback ({exc}).",
        )
    best = max(y_train)
    exploration = 1.0 if exploration_weight is None else exploration_weight
    predictions = []
    for conditions, mean, std in zip(candidates, means, stds, strict=False):
        mean_f = float(mean)
        std_f = max(float(std), 1e-9)
        ei = _expected_improvement(mean_f, std_f, best)
        acquisition = mean_f + exploration * std_f if algorithm == "gaussian_process_ucb" else ei
        predictions.append(
            {
                "conditions_json": conditions,
                "predicted_score": round(mean_f, 6),
                "expected_improvement": round(ei, 6),
                "uncertainty": round(std_f, 6),
                "acquisition_score": round(float(acquisition), 6),
                "metadata_json": {"model_branch": "gaussian_process"},
            }
        )
    return "gaussian_process", predictions, {"kernel": str(model.kernel_)}, None


def _sklearn_forest_predictions(
    training: list[_TrainingExample],
    candidates: list[dict[str, Any]],
    encoding: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any], str | None]:
    try:
        from sklearn.ensemble import RandomForestRegressor
    except Exception as exc:  # pragma: no cover - depends on optional deployment package
        return (
            "rule_based_fallback",
            _fallback_predictions(training, candidates, _domain_from_encoding(encoding), low_data=False),
            {"fallback_reason": "sklearn_unavailable"},
            f"sklearn RandomForestRegressor unavailable; used rule-based fallback ({exc}).",
        )
    x_train = [_encode_conditions(item.conditions, encoding) for item in training]
    y_train = [item.score for item in training]
    x_candidates = [_encode_conditions(conditions, encoding) for conditions in candidates]
    try:
        model = RandomForestRegressor(n_estimators=100, random_state=50, min_samples_leaf=1)
        model.fit(x_train, y_train)
        tree_predictions = [tree.predict(x_candidates) for tree in model.estimators_]
    except Exception as exc:  # pragma: no cover - optional model branch
        return (
            "rule_based_fallback",
            _fallback_predictions(training, candidates, _domain_from_encoding(encoding), low_data=False),
            {"fallback_reason": "forest_fit_failed"},
            f"Random forest fit failed; used rule-based fallback ({exc}).",
        )
    best = max(y_train)
    predictions = []
    for index, conditions in enumerate(candidates):
        values = [float(row[index]) for row in tree_predictions]
        mean = sum(values) / len(values)
        std = _std(values)
        ei = _expected_improvement(mean, std, best)
        predictions.append(
            {
                "conditions_json": conditions,
                "predicted_score": round(mean, 6),
                "expected_improvement": round(ei, 6),
                "uncertainty": round(std, 6),
                "acquisition_score": round(ei, 6),
                "metadata_json": {"model_branch": "random_forest"},
            }
        )
    return "random_forest", predictions, {"n_estimators": len(model.estimators_)}, None


def _fallback_predictions(
    training: list[_TrainingExample],
    candidates: list[dict[str, Any]],
    domain: _ConditionDomain,
    *,
    low_data: bool,
) -> list[dict[str, Any]]:
    best = max((item.score for item in training), default=None)
    mean = sum(item.score for item in training) / len(training) if training else None
    seen = {_condition_key(item.conditions) for item in training}
    predictions = []
    for conditions in candidates:
        nearest_score = _nearest_training_score(conditions, training, domain)
        predicted = nearest_score if nearest_score is not None else mean
        exploration = 12.0 if _condition_key(conditions) not in seen else 0.0
        acquisition = (predicted if predicted is not None else 0.0) + exploration
        ei = max(0.0, (predicted or 0.0) - best) if best is not None and predicted is not None else None
        predictions.append(
            {
                "conditions_json": conditions,
                "predicted_score": round(predicted, 6) if predicted is not None else None,
                "expected_improvement": round(ei, 6) if ei is not None else None,
                "uncertainty": 1.0 if low_data else 0.5,
                "acquisition_score": round(acquisition, 6),
                "metadata_json": {
                    "model_branch": "rule_based_fallback",
                    "low_data": low_data,
                },
            }
        )
    return predictions


def _tpe_like_predictions(
    training: list[_TrainingExample],
    candidates: list[dict[str, Any]],
    domain: _ConditionDomain,
) -> list[dict[str, Any]]:
    sorted_training = sorted(training, key=lambda item: item.score, reverse=True)
    top = sorted_training[: max(1, math.ceil(len(sorted_training) * 0.35))]
    top_mean = sum(item.score for item in top) / len(top)
    global_mean = sum(item.score for item in training) / len(training)
    best = sorted_training[0].score
    predictions = []
    for conditions in candidates:
        affinity = _top_condition_affinity(conditions, top, domain)
        predicted = global_mean * (1.0 - affinity) + top_mean * affinity
        uncertainty = max(0.05, 1.0 - affinity)
        ei = _expected_improvement(predicted, uncertainty * 10.0, best)
        predictions.append(
            {
                "conditions_json": conditions,
                "predicted_score": round(predicted, 6),
                "expected_improvement": round(ei, 6),
                "uncertainty": round(uncertainty, 6),
                "acquisition_score": round(ei + predicted * 0.02, 6),
                "metadata_json": {"model_branch": "tpe_like", "top_affinity": round(affinity, 6)},
            }
        )
    return predictions


def _training_examples(
    experiments: list[ReactionExperimentORM],
    *,
    objective_type: str,
    weights: dict[str, Any],
    include_negative: bool,
) -> tuple[list[_TrainingExample], list[str]]:
    examples: list[_TrainingExample] = []
    warnings: list[str] = []
    for row in experiments:
        if row.status == "completed":
            score = _score_outcome(_json_dict(row.outcome_json), objective_type, weights)
        elif include_negative and row.status in {"failed", "excluded"}:
            score = 0.0
        else:
            continue
        if score is None:
            warnings.append(f"Experiment {row.experiment_code} has no usable objective outcome.")
            continue
        examples.append(
            _TrainingExample(
                experiment_id=row.id,
                experiment_code=row.experiment_code,
                conditions=_json_dict(row.conditions_json),
                outcome=_json_dict(row.outcome_json),
                score=float(score),
                status=row.status,
            )
        )
    return examples, warnings


def _score_outcome(outcome: dict[str, Any], objective_type: str, weights: dict[str, Any]) -> float | None:
    if objective_type == "maximize_yield":
        return _float_or_none(outcome.get("yield_percent"))
    if objective_type == "maximize_selectivity":
        return _float_or_none(outcome.get("selectivity_percent"))
    if objective_type == "maximize_conversion":
        return _float_or_none(outcome.get("conversion_percent"))
    if objective_type == "minimize_impurity":
        impurity = _float_or_none(outcome.get("impurity_percent"))
        return 100.0 - impurity if impurity is not None else None
    if objective_type == "custom":
        custom = _float_or_none(outcome.get("objective_value"))
        if custom is not None:
            return custom
    yield_weight = _float_or_default(weights.get("yield_weight", weights.get("yield", 0.45)), 0.45)
    selectivity_weight = _float_or_default(
        weights.get("selectivity_weight", weights.get("selectivity", 0.25)),
        0.25,
    )
    impurity_weight = _float_or_default(
        weights.get("impurity_penalty", weights.get("impurity", 0.20)),
        0.20,
    )
    conversion_weight = _float_or_default(
        weights.get("conversion_weight", weights.get("conversion", 0.10)),
        0.10,
    )
    yield_value = _float_or_none(outcome.get("yield_percent"))
    selectivity = _float_or_none(outcome.get("selectivity_percent"))
    impurity = _float_or_none(outcome.get("impurity_percent"))
    conversion = _float_or_none(outcome.get("conversion_percent"))
    available = [value for value in (yield_value, selectivity, impurity, conversion) if value is not None]
    if not available:
        return None
    return (
        (yield_value or 0.0) * yield_weight
        + (selectivity or 0.0) * selectivity_weight
        + (100.0 - (impurity or 100.0)) * impurity_weight
        + (conversion or 0.0) * conversion_weight
    )


def _build_domain(
    design_space: ReactionDesignSpaceORM | None,
    variables: list[ReactionVariableORM],
    experiments: list[ReactionExperimentORM],
) -> _ConditionDomain:
    numeric: dict[str, list[float]] = {}
    numeric_ranges: dict[str, tuple[float, float]] = {}
    categorical: dict[str, list[Any]] = {}
    boolean: dict[str, list[bool]] = {}
    fixed: dict[str, Any] = {}
    excluded: list[dict[str, Any]] = []

    if design_space is not None:
        fixed.update(_json_dict(design_space.fixed_conditions_json))
        excluded = _excluded_conditions(_json_value(design_space.excluded_conditions_json))
        for name, spec in _json_dict(design_space.numeric_variables_json).items():
            values, value_range = _numeric_values_from_spec(spec)
            if values:
                numeric[str(name)] = values
                numeric_ranges[str(name)] = value_range
        for name, spec in _json_dict(design_space.categorical_variables_json).items():
            values = _categorical_values_from_spec(spec)
            if values:
                categorical[str(name)] = values
        for name, spec in _json_dict(design_space.boolean_variables_json).items():
            boolean[str(name)] = _boolean_values_from_spec(spec)
        for name, spec in _json_dict(design_space.variables_json).items():
            _merge_general_variable_spec(
                str(name),
                spec,
                numeric=numeric,
                numeric_ranges=numeric_ranges,
                categorical=categorical,
                boolean=boolean,
            )

    for variable in variables:
        if variable.name in fixed:
            continue
        if variable.variable_type == "numeric" and variable.name not in numeric:
            values, value_range = _numeric_values_from_bounds(
                variable.min_value,
                variable.max_value,
                _json_value(variable.default_value),
            )
            if values:
                numeric[variable.name] = values
                numeric_ranges[variable.name] = value_range
        elif variable.variable_type == "categorical" and variable.name not in categorical:
            values = _json_value(variable.allowed_values_json)
            if isinstance(values, list):
                categorical[variable.name] = values
        elif variable.variable_type == "boolean" and variable.name not in boolean:
            boolean[variable.name] = [False, True]

    _fill_domain_from_observed(numeric, numeric_ranges, categorical, boolean, fixed, experiments)
    return _ConditionDomain(
        numeric=numeric,
        numeric_ranges=numeric_ranges,
        categorical=categorical,
        boolean=boolean,
        fixed=fixed,
        excluded=excluded,
    )


def _generate_candidate_conditions(domain: _ConditionDomain, *, max_candidates: int) -> list[dict[str, Any]]:
    dimensions: list[tuple[str, list[Any]]] = []
    for name, values in sorted(domain.numeric.items()):
        dimensions.append((name, values))
    for name, values in sorted(domain.categorical.items()):
        dimensions.append((name, values))
    for name, values in sorted(domain.boolean.items()):
        dimensions.append((name, values))
    if not dimensions:
        return [dict(domain.fixed)] if domain.fixed else []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    value_sets = [values for _name, values in dimensions]
    for combo in itertools.product(*value_sets):
        conditions = dict(domain.fixed)
        for (name, _values), value in zip(dimensions, combo, strict=False):
            conditions[name] = value
        if _is_excluded(conditions, domain.excluded):
            continue
        key = _condition_key(conditions)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(conditions)
        if len(candidates) >= max_candidates:
            break
    return candidates


def _build_feature_encoding(domain: _ConditionDomain, training: list[_TrainingExample]) -> dict[str, Any]:
    categorical_values = {name: list(values) for name, values in domain.categorical.items()}
    boolean_values = {name: list(values) for name, values in domain.boolean.items()}
    numeric_ranges = {name: list(value) for name, value in domain.numeric_ranges.items()}
    for item in training:
        for key, value in item.conditions.items():
            if key in numeric_ranges:
                continue
            numeric = _float_or_none(value)
            if numeric is not None and key not in categorical_values and key not in boolean_values:
                numeric_ranges[key] = [numeric, numeric]
            elif isinstance(value, bool):
                boolean_values.setdefault(key, [False, True])
            elif value is not None:
                values = categorical_values.setdefault(key, [])
                if value not in values:
                    values.append(value)
    for item in training:
        for key, value in item.conditions.items():
            if key in numeric_ranges:
                numeric = _float_or_none(value)
                if numeric is not None:
                    numeric_ranges[key][0] = min(numeric_ranges[key][0], numeric)
                    numeric_ranges[key][1] = max(numeric_ranges[key][1], numeric)
    return {
        "numeric_ranges": numeric_ranges,
        "categorical_values": categorical_values,
        "boolean_values": boolean_values,
        "encoding": "min_max_numeric_plus_transparent_one_hot_categorical",
    }


def _encode_conditions(conditions: dict[str, Any], encoding: dict[str, Any]) -> list[float]:
    features: list[float] = []
    for name, value_range in sorted(_json_dictish(encoding.get("numeric_ranges")).items()):
        low, high = float(value_range[0]), float(value_range[1])
        value = _float_or_default(conditions.get(name), low)
        scale = high - low
        features.append(0.0 if abs(scale) < 1e-12 else (value - low) / scale)
    for name, values in sorted(_json_dictish(encoding.get("categorical_values")).items()):
        for value in values if isinstance(values, list) else []:
            features.append(1.0 if conditions.get(name) == value else 0.0)
    for name in sorted(_json_dictish(encoding.get("boolean_values"))):
        features.append(1.0 if bool(conditions.get(name)) else 0.0)
    return features or [0.0]


def _estimate_cost(
    conditions: dict[str, Any],
    profile: ReactionCostProfileORM | None,
) -> _CostEstimate:
    if profile is None:
        return _CostEstimate(total=None, penalty=0.0, unavailable=False, details={})
    cost_maps = [
        _json_dict(profile.reagent_costs_json),
        _json_dict(profile.solvent_costs_json),
        _json_dict(profile.catalyst_costs_json),
        _json_dict(profile.ligand_costs_json),
    ]
    total = 0.0
    details: dict[str, Any] = {}
    for key, value in conditions.items():
        amount = 0.0
        for cost_map in cost_maps:
            amount += _lookup_cost(cost_map, key, value)
        if amount:
            details[str(key)] = {"value": value, "cost": round(amount, 6)}
            total += amount
    unavailable = _is_unavailable(conditions, _json_dict(profile.availability_json))
    penalty_weight = profile.cost_penalty_weight if profile.cost_penalty_weight is not None else 0.01
    penalty = total * penalty_weight
    if profile.max_cost_per_experiment is not None and total > profile.max_cost_per_experiment:
        penalty += (total - profile.max_cost_per_experiment) * max(1.0, penalty_weight)
        details["max_cost_per_experiment_exceeded"] = profile.max_cost_per_experiment
    if unavailable:
        details["availability"] = "one_or_more_conditions_unavailable"
        penalty += 50.0
    return _CostEstimate(
        total=round(total, 6),
        penalty=round(penalty, 6),
        unavailable=unavailable,
        details=details,
    )


def _assess_safety(
    conditions: dict[str, Any],
    profile: ReactionSafetyConstraintProfileORM | None,
) -> _SafetyAssessment:
    if profile is None:
        return _SafetyAssessment(status="unknown", reasons=[], required_controls=[])
    reasons: list[str] = []
    warnings: list[str] = []
    blocked_reagents = _blocked_values(_json_value(profile.blocked_reagents_json))
    blocked_solvents = _blocked_values(_json_value(profile.blocked_solvents_json))
    values_lower = {str(value).strip().lower() for value in conditions.values()}
    if values_lower.intersection(blocked_reagents):
        reasons.append("Condition contains a blocked reagent.")
    if values_lower.intersection(blocked_solvents):
        reasons.append("Condition contains a blocked solvent.")
    temperature = _first_numeric_condition(
        conditions,
        ("temperature_c", "temp_c", "temperature", "temperature_deg_c"),
    )
    if (
        profile.max_temperature_c is not None
        and temperature is not None
        and temperature > profile.max_temperature_c
    ):
        reasons.append(
            f"Temperature {temperature:g} C exceeds max_temperature_c {profile.max_temperature_c:g}."
        )
    pressure = _first_numeric_condition(conditions, ("pressure_bar", "pressure", "bar"))
    if (
        profile.max_pressure_bar is not None
        and pressure is not None
        and pressure > profile.max_pressure_bar
    ):
        reasons.append(f"Pressure {pressure:g} bar exceeds max_pressure_bar {profile.max_pressure_bar:g}.")
    for pair in _pairs(_json_value(profile.incompatible_pairs_json)):
        if _pair_present(pair, conditions):
            reasons.append(f"Incompatible pair present: {pair!r}.")
    required_controls = _required_controls(_json_value(profile.required_controls_json), conditions)
    if required_controls:
        warnings.append("Required safety controls must be confirmed before scheduling.")
    if reasons:
        return _SafetyAssessment(status="blocked", reasons=reasons, required_controls=required_controls)
    if warnings or required_controls:
        return _SafetyAssessment(status="warning", reasons=warnings, required_controls=required_controls)
    return _SafetyAssessment(status="allowed", reasons=[], required_controls=[])


def _candidate_label(
    item: dict[str, Any],
    *,
    training_count: int,
    cost_aware: bool,
    safety_status: str,
) -> str:
    if safety_status == "blocked":
        return "safety_blocked"
    if training_count < 5:
        return "insufficient_data"
    if cost_aware and item.get("estimated_cost") is not None and item.get("estimated_cost", 0) <= 25:
        return "cost_efficient_candidate"
    if (item.get("expected_improvement") or 0.0) > 0:
        return "high_expected_improvement"
    if (item.get("uncertainty") or 0.0) >= 0.5:
        return "exploratory_candidate"
    return "requires_human_review"


def _candidate_rationale(
    item: dict[str, Any],
    *,
    objective_type: str,
    model_type: str,
    cost_aware: bool,
    safety: _SafetyAssessment,
    cost: _CostEstimate,
) -> str:
    parts = [
        f"Ranked by {model_type} advisory scoring for {objective_type}.",
        "This is a decision-support recommendation, not a guaranteed optimum.",
    ]
    if item.get("expected_improvement") is not None:
        parts.append(f"Expected improvement estimate: {item['expected_improvement']:.3g}.")
    if item.get("uncertainty") is not None:
        parts.append(f"Uncertainty estimate: {item['uncertainty']:.3g}.")
    if cost_aware and cost.total is not None:
        parts.append(f"Estimated condition cost {cost.total:.2f} with penalty {cost.penalty:.2f}.")
    if safety.status == "blocked":
        parts.append("Safety hard constraint violation: " + "; ".join(safety.reasons))
    elif safety.status == "warning":
        parts.append("Safety review warning: " + "; ".join(safety.reasons or safety.required_controls))
    parts.append("Human review and approval are required before scheduling.")
    return " ".join(parts)


def _latest_design_space(session: Session, project_id: int) -> ReactionDesignSpaceORM | None:
    return session.scalar(
        select(ReactionDesignSpaceORM)
        .where(ReactionDesignSpaceORM.reaction_project_id == project_id)
        .order_by(ReactionDesignSpaceORM.id.desc())
    )


def _latest_objective_profile(session: Session, project_id: int) -> ReactionObjectiveProfileORM | None:
    return session.scalar(
        select(ReactionObjectiveProfileORM)
        .where(ReactionObjectiveProfileORM.reaction_project_id == project_id)
        .order_by(ReactionObjectiveProfileORM.id.desc())
    )


def _latest_cost_profile(session: Session, project_id: int) -> ReactionCostProfileORM | None:
    return session.scalar(
        select(ReactionCostProfileORM)
        .where(ReactionCostProfileORM.reaction_project_id == project_id)
        .order_by(ReactionCostProfileORM.id.desc())
    )


def _latest_safety_profile(
    session: Session,
    project_id: int,
) -> ReactionSafetyConstraintProfileORM | None:
    return session.scalar(
        select(ReactionSafetyConstraintProfileORM)
        .where(ReactionSafetyConstraintProfileORM.reaction_project_id == project_id)
        .order_by(ReactionSafetyConstraintProfileORM.id.desc())
    )


def _project_or_raise(session: Session, project_id: int) -> ReactionProjectORM:
    row = session.get(ReactionProjectORM, project_id)
    if row is None:
        raise KeyError("Reaction project not found.")
    return row


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


def _bo_candidates(session: Session, bo_run_id: int) -> list[ReactionAcquisitionCandidateORM]:
    return list(
        session.scalars(
            select(ReactionAcquisitionCandidateORM)
            .where(ReactionAcquisitionCandidateORM.bo_run_id == bo_run_id)
            .order_by(ReactionAcquisitionCandidateORM.rank.asc(), ReactionAcquisitionCandidateORM.id.asc())
        ).all()
    )


def _bo_model_type(session: Session, bo_run_id: int) -> str:
    row = session.scalar(
        select(ReactionSurrogateModelRecordORM)
        .where(ReactionSurrogateModelRecordORM.bo_run_id == bo_run_id)
        .order_by(ReactionSurrogateModelRecordORM.id.desc())
    )
    return row.model_type if row is not None else "rule_based_fallback"


def _design_space_to_record(row: ReactionDesignSpaceORM) -> ReactionDesignSpace:
    return ReactionDesignSpace(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        variables_json=_json_dict(row.variables_json),
        categorical_variables_json=_json_dict(row.categorical_variables_json),
        numeric_variables_json=_json_dict(row.numeric_variables_json),
        boolean_variables_json=_json_dict(row.boolean_variables_json),
        fixed_conditions_json=_json_dict(row.fixed_conditions_json),
        excluded_conditions_json=_json_value(row.excluded_conditions_json) or [],
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _objective_profile_to_record(row: ReactionObjectiveProfileORM) -> ReactionObjectiveProfile:
    return ReactionObjectiveProfile(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        objective_type=row.objective_type,  # type: ignore[arg-type]
        weights_json=_json_dict(row.weights_json),
        target_thresholds_json=_json_dict(row.target_thresholds_json),
        hard_constraints_json=_json_dict(row.hard_constraints_json),
        soft_constraints_json=_json_dict(row.soft_constraints_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _cost_profile_to_record(row: ReactionCostProfileORM) -> ReactionCostProfile:
    return ReactionCostProfile(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        reagent_costs_json=_json_dict(row.reagent_costs_json),
        solvent_costs_json=_json_dict(row.solvent_costs_json),
        catalyst_costs_json=_json_dict(row.catalyst_costs_json),
        ligand_costs_json=_json_dict(row.ligand_costs_json),
        availability_json=_json_dict(row.availability_json),
        max_cost_per_experiment=row.max_cost_per_experiment,
        cost_penalty_weight=row.cost_penalty_weight,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _safety_profile_to_record(
    row: ReactionSafetyConstraintProfileORM,
) -> ReactionSafetyConstraintProfile:
    return ReactionSafetyConstraintProfile(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        blocked_reagents_json=_json_value(row.blocked_reagents_json) or [],
        blocked_solvents_json=_json_value(row.blocked_solvents_json) or [],
        max_temperature_c=row.max_temperature_c,
        max_pressure_bar=row.max_pressure_bar,
        incompatible_pairs_json=_json_value(row.incompatible_pairs_json) or [],
        required_controls_json=_json_value(row.required_controls_json) or [],
        safety_notes_json=_json_value(row.safety_notes_json) or [],
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _surrogate_to_record(row: ReactionSurrogateModelRecordORM) -> ReactionSurrogateModelRecord:
    return ReactionSurrogateModelRecord(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        bo_run_id=row.bo_run_id,
        model_type=row.model_type,  # type: ignore[arg-type]
        model_version=row.model_version,
        training_experiment_count=row.training_experiment_count,
        feature_encoding_json=_json_dict(row.feature_encoding_json),
        objective_summary_json=_json_dict(row.objective_summary_json),
        metrics_json=_json_dict(row.metrics_json),
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _candidate_to_record(row: ReactionAcquisitionCandidateORM) -> ReactionAcquisitionCandidate:
    return ReactionAcquisitionCandidate(
        id=row.id,
        bo_run_id=row.bo_run_id,
        rank=row.rank,
        conditions_json=_json_dict(row.conditions_json),
        predicted_score=row.predicted_score,
        expected_improvement=row.expected_improvement,
        uncertainty=row.uncertainty,
        estimated_cost=row.estimated_cost,
        safety_status=row.safety_status,  # type: ignore[arg-type]
        acquisition_score=row.acquisition_score,
        rationale=row.rationale,
        label=row.label,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _bo_run_to_record(
    row: ReactionBayesianOptimizationRunORM,
    candidates: list[ReactionAcquisitionCandidateORM],
    *,
    model_type: str,
) -> ReactionBayesianOptimizationRun:
    warnings = [str(item) for item in _json_list(row.warnings_json)]
    notes = [str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE]
    diagnostics = _json_dict(row.diagnostics_json)
    recommendations_json = _json_list(row.recommendations_json)
    return ReactionBayesianOptimizationRun(
        id=row.id,
        bo_run_id=row.id,
        reaction_project_id=row.reaction_project_id,
        status=row.status,  # type: ignore[arg-type]
        algorithm=row.algorithm,  # type: ignore[arg-type]
        model_type=model_type,  # type: ignore[arg-type]
        batch_size=row.batch_size,
        exploration_weight=row.exploration_weight,
        cost_aware=row.cost_aware,
        safety_aware=row.safety_aware,
        input_experiment_count=row.input_experiment_count,
        candidate_count=row.candidate_count,
        recommendations_json=recommendations_json,
        recommendations=[_candidate_to_record(candidate) for candidate in candidates],
        diagnostics_json=diagnostics,
        diagnostics=diagnostics,
        warnings_json=warnings,
        warnings=warnings,
        notes_json=notes,
        notes=notes,
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _recommendation_batch_to_record(row: ReactionRecommendationBatchORM) -> ReactionRecommendationBatch:
    return ReactionRecommendationBatch(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        bo_run_id=row.bo_run_id,
        status=row.status,  # type: ignore[arg-type]
        recommendations_json=_json_list(row.recommendations_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _benchmark_to_record(row: ReactionOptimizationBenchmarkRunORM) -> ReactionOptimizationBenchmarkRun:
    return ReactionOptimizationBenchmarkRun(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        benchmark_name=row.benchmark_name,
        algorithm=row.algorithm,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        metrics_json=_json_dict(row.metrics_json),
        trajectory_json=_json_list(row.trajectory_json),
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _candidate_summary(row: ReactionAcquisitionCandidateORM) -> dict[str, Any]:
    metadata = _json_dict(row.metadata_json)
    return {
        "id": row.id,
        "acquisition_candidate_id": row.id,
        "recommendation_id": metadata.get("recommendation_id"),
        "bo_run_id": row.bo_run_id,
        "rank": row.rank,
        "conditions_json": _json_dict(row.conditions_json),
        "predicted_score": row.predicted_score,
        "expected_improvement": row.expected_improvement,
        "uncertainty": row.uncertainty,
        "estimated_cost": row.estimated_cost,
        "safety_status": row.safety_status,
        "acquisition_score": row.acquisition_score,
        "rationale": row.rationale,
        "label": row.label,
        "metadata_json": metadata,
        "human_review_required": True,
    }


def _numeric_values_from_spec(value: Any) -> tuple[list[float], tuple[float, float]]:
    if isinstance(value, list):
        values = [_float_or_none(item) for item in value]
        clean = sorted({float(item) for item in values if item is not None})
        if clean:
            return clean, (min(clean), max(clean))
        return [], (0.0, 0.0)
    if isinstance(value, dict):
        if isinstance(value.get("values"), list):
            return _numeric_values_from_spec(value["values"])
        return _numeric_values_from_bounds(
            value.get("min", value.get("min_value")),
            value.get("max", value.get("max_value")),
            value.get("default", value.get("default_value")),
        )
    return [], (0.0, 0.0)


def _numeric_values_from_bounds(
    minimum: Any,
    maximum: Any,
    default: Any = None,
) -> tuple[list[float], tuple[float, float]]:
    low = _float_or_none(minimum)
    high = _float_or_none(maximum)
    if low is None or high is None:
        return [], (0.0, 0.0)
    if low > high:
        low, high = high, low
    midpoint = (low + high) / 2.0
    values = [low, midpoint, high]
    default_numeric = _float_or_none(default)
    if default_numeric is not None:
        values.append(default_numeric)
    clean = sorted({round(float(item), 6) for item in values})
    return clean, (low, high)


def _categorical_values_from_spec(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        values = value.get("values", value.get("allowed_values_json"))
        return values if isinstance(values, list) else []
    return []


def _boolean_values_from_spec(value: Any) -> list[bool]:
    if isinstance(value, list):
        values = [bool(item) for item in value]
        return values or [False, True]
    if isinstance(value, dict) and isinstance(value.get("values"), list):
        values = [bool(item) for item in value["values"]]
        return values or [False, True]
    return [False, True]


def _merge_general_variable_spec(
    name: str,
    spec: Any,
    *,
    numeric: dict[str, list[float]],
    numeric_ranges: dict[str, tuple[float, float]],
    categorical: dict[str, list[Any]],
    boolean: dict[str, list[bool]],
) -> None:
    if not isinstance(spec, dict):
        return
    variable_type = str(spec.get("type", spec.get("variable_type", ""))).lower()
    if variable_type == "numeric" and name not in numeric:
        values, value_range = _numeric_values_from_spec(spec)
        if values:
            numeric[name] = values
            numeric_ranges[name] = value_range
    elif variable_type == "categorical" and name not in categorical:
        values = _categorical_values_from_spec(spec)
        if values:
            categorical[name] = values
    elif variable_type == "boolean" and name not in boolean:
        boolean[name] = _boolean_values_from_spec(spec)


def _fill_domain_from_observed(
    numeric: dict[str, list[float]],
    numeric_ranges: dict[str, tuple[float, float]],
    categorical: dict[str, list[Any]],
    boolean: dict[str, list[bool]],
    fixed: dict[str, Any],
    experiments: list[ReactionExperimentORM],
) -> None:
    for row in experiments:
        for key, value in _json_dict(row.conditions_json).items():
            if key in fixed or key in numeric or key in categorical or key in boolean:
                continue
            if isinstance(value, bool):
                boolean[key] = [False, True]
            else:
                numeric_value = _float_or_none(value)
                if numeric_value is not None:
                    numeric[key] = [numeric_value]
                    numeric_ranges[key] = (numeric_value, numeric_value)
                elif value is not None:
                    categorical[key] = [value]


def _excluded_conditions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if isinstance(value.get("conditions"), list):
            return [item for item in value["conditions"] if isinstance(item, dict)]
        return [value]
    return []


def _is_excluded(conditions: dict[str, Any], excluded: list[dict[str, Any]]) -> bool:
    for excluded_condition in excluded:
        if all(conditions.get(key) == value for key, value in excluded_condition.items()):
            return True
    return False


def _default_candidate_from_experiments(experiments: list[ReactionExperimentORM]) -> dict[str, Any]:
    for row in experiments:
        conditions = _json_dict(row.conditions_json)
        if conditions:
            return conditions
    return {}


def _expected_improvement(mean: float, std: float, best: float) -> float:
    if std <= 1e-12:
        return max(0.0, mean - best)
    improvement = mean - best
    z = improvement / std
    return improvement * _normal_cdf(z) + std * _normal_pdf(z)


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _nearest_training_score(
    conditions: dict[str, Any],
    training: list[_TrainingExample],
    domain: _ConditionDomain,
) -> float | None:
    if not training:
        return None
    best_distance = None
    best_score = None
    for item in training:
        distance = _condition_distance(conditions, item.conditions, domain)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_score = item.score
    return best_score


def _condition_distance(
    left: dict[str, Any],
    right: dict[str, Any],
    domain: _ConditionDomain,
) -> float:
    distance = 0.0
    for key, (low, high) in domain.numeric_ranges.items():
        left_value = _float_or_none(left.get(key))
        right_value = _float_or_none(right.get(key))
        if left_value is None or right_value is None:
            continue
        scale = max(abs(high - low), 1.0)
        distance += abs(left_value - right_value) / scale
    for key in set(domain.categorical) | set(domain.boolean):
        if left.get(key) != right.get(key):
            distance += 1.0
    return distance


def _top_condition_affinity(
    conditions: dict[str, Any],
    top: list[_TrainingExample],
    domain: _ConditionDomain,
) -> float:
    if not top:
        return 0.0
    scores: list[float] = []
    for item in top:
        distance = _condition_distance(conditions, item.conditions, domain)
        scores.append(1.0 / (1.0 + distance))
    return sum(scores) / len(scores)


def _lookup_cost(cost_map: dict[str, Any], key: str, value: Any) -> float:
    total = 0.0
    direct = _float_or_none(cost_map.get(str(value)))
    if direct is not None:
        total += direct
    keyed = cost_map.get(key)
    if isinstance(keyed, dict):
        mapped = _float_or_none(keyed.get(str(value), keyed.get(value)))
        if mapped is not None:
            total += mapped
    else:
        keyed_cost = _float_or_none(keyed)
        if keyed_cost is not None:
            total += keyed_cost
    return total


def _is_unavailable(conditions: dict[str, Any], availability: dict[str, Any]) -> bool:
    for key, value in conditions.items():
        direct = availability.get(str(value), availability.get(value))
        if _availability_is_false(direct):
            return True
        keyed = availability.get(key)
        if isinstance(keyed, dict) and _availability_is_false(keyed.get(str(value), keyed.get(value))):
            return True
        if _availability_is_false(keyed):
            return True
    return False


def _availability_is_false(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in {"false", "unavailable", "blocked", "no", "0"}


def _blocked_values(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value}
    if isinstance(value, dict):
        blocked: set[str] = set()
        for key, item in value.items():
            if isinstance(item, bool) and item:
                blocked.add(str(key).strip().lower())
            elif isinstance(item, list):
                blocked.update(str(entry).strip().lower() for entry in item)
        return blocked
    return set()


def _first_numeric_condition(conditions: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    lower_map = {str(key).lower(): value for key, value in conditions.items()}
    for key in keys:
        value = _float_or_none(lower_map.get(key))
        if value is not None:
            return value
    return None


def _pairs(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        pairs = value.get("pairs", value.get("incompatible_pairs"))
        return pairs if isinstance(pairs, list) else []
    return []


def _pair_present(pair: Any, conditions: dict[str, Any]) -> bool:
    values = {str(value).strip().lower() for value in conditions.values()}
    if isinstance(pair, list) and len(pair) >= 2:
        return str(pair[0]).strip().lower() in values and str(pair[1]).strip().lower() in values
    if isinstance(pair, dict):
        left = pair.get("left", pair.get("a"))
        right = pair.get("right", pair.get("b"))
        if left is not None and right is not None:
            return str(left).strip().lower() in values and str(right).strip().lower() in values
        return all(conditions.get(key) == value for key, value in pair.items())
    return False


def _required_controls(value: Any, conditions: dict[str, Any]) -> list[str]:
    controls: list[str] = []
    if isinstance(value, list):
        controls.extend(str(item) for item in value)
    elif isinstance(value, dict):
        for key, required in value.items():
            if bool(required) and not bool(conditions.get(key)):
                controls.append(str(key))
    return controls


def _confidence_label(prediction: dict[str, Any], training_count: int) -> str:
    if training_count < 5:
        return "low_data"
    uncertainty = prediction.get("uncertainty")
    if uncertainty is None:
        return "uncertain"
    if uncertainty >= 0.75:
        return "high_uncertainty"
    if uncertainty >= 0.35:
        return "moderate_uncertainty"
    return "lower_uncertainty"


def _objective_summary(objective_type: str, weights: dict[str, Any]) -> dict[str, Any]:
    if objective_type == "multi_objective":
        return {
            "method": "transparent_scalarization",
            "yield_weight": _float_or_default(weights.get("yield_weight", weights.get("yield", 0.45)), 0.45),
            "selectivity_weight": _float_or_default(
                weights.get("selectivity_weight", weights.get("selectivity", 0.25)),
                0.25,
            ),
            "impurity_penalty": _float_or_default(
                weights.get("impurity_penalty", weights.get("impurity", 0.20)),
                0.20,
            ),
            "conversion_weight": _float_or_default(
                weights.get("conversion_weight", weights.get("conversion", 0.10)),
                0.10,
            ),
        }
    return {"method": objective_type}


def _domain_from_encoding(encoding: dict[str, Any]) -> _ConditionDomain:
    numeric_ranges = {
        str(key): (float(value[0]), float(value[1]))
        for key, value in _json_dictish(encoding.get("numeric_ranges")).items()
        if isinstance(value, list) and len(value) >= 2
    }
    return _ConditionDomain(
        numeric={key: [low, high] for key, (low, high) in numeric_ranges.items()},
        numeric_ranges=numeric_ranges,
        categorical=_json_dictish(encoding.get("categorical_values")),
        boolean={key: [False, True] for key in _json_dictish(encoding.get("boolean_values"))},
        fixed={},
        excluded=[],
    )


def _rank_of_latest_best(training: list[_TrainingExample]) -> int | None:
    if not training:
        return None
    sorted_by_score = sorted(training, key=lambda item: item.score, reverse=True)
    latest = training[-1]
    for index, item in enumerate(sorted_by_score, start=1):
        if item.experiment_id == latest.experiment_id:
            return index
    return None


def _condition_key(conditions: dict[str, Any]) -> str:
    return json.dumps(conditions, sort_keys=True, separators=(",", ":"), default=str)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def _float_or_default(value: Any, default: float) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _json_dictish(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
