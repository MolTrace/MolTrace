from __future__ import annotations

import json
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ReactionAdvisorReviewRequest,
    ReactionConditionCritique,
    ReactionConditionCritiqueRequest,
    ReactionLiteraturePrior,
    ReactionLiteraturePriorCreate,
    ReactionMechanisticHypothesis,
    ReactionMechanisticHypothesisCreate,
    ReactionMechanisticHypothesisUpdate,
    ReactionOptimizationAdvisorRun,
    ReactionOptimizationAdvisorRunRequest,
    ReactionOptimizationDebate,
    ReactionOptimizationDebateRequest,
)
from .orm import (
    AuditEventORM,
    ReactionAcquisitionCandidateORM,
    ReactionBayesianOptimizationRunORM,
    ReactionConditionCritiqueORM,
    ReactionCostProfileORM,
    ReactionDesignSpaceORM,
    ReactionExperimentORM,
    ReactionLiteraturePriorORM,
    ReactionMechanisticHypothesisORM,
    ReactionObjectiveProfileORM,
    ReactionOptimizationAdvisorRunORM,
    ReactionOptimizationDebateORM,
    ReactionProjectORM,
    ReactionRecommendationBatchORM,
    ReactionRecommendationORM,
    ReactionSafetyConstraintProfileORM,
    ReactionVariableORM,
    utcnow,
)
from .reaction_store import ReactionActor


_SAFE_NOTE = (
    "Reaction advisor output is explanatory decision support. It critiques and contextualizes "
    "optimization suggestions, does not schedule experiments, and requires review."
)
_LLM_NOT_CONFIGURED_NOTE = (
    "External LLM guidance is not configured. Rule-based mechanistic advisor was used."
)


def run_advisor(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionOptimizationAdvisorRunRequest,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationAdvisorRun:
    with session_scope(session_factory) as session:
        project = _project_or_raise(session, project_id)
        bo_run = _resolve_bo_run(session, project_id, payload.bo_run_id)
        batch = _resolve_batch(session, project_id, payload.recommendation_batch_id)
        recommendations = _advisor_recommendations(session, project_id, bo_run, batch)
        experiments = _project_experiments(session, project_id)
        variables = _project_variables(session, project_id)
        objective_profile = _latest_objective_profile(session, project_id)
        cost_profile = _latest_cost_profile(session, project_id)
        safety_profile = _latest_safety_profile(session, project_id)
        design_space = _latest_design_space(session, project_id)

        mode = "rule_based_mechanistic"
        warnings: list[str] = []
        notes = [_SAFE_NOTE, _LLM_NOT_CONFIGURED_NOTE]
        if payload.advisor_mode != "rule_based_mechanistic":
            warnings.append(_LLM_NOT_CONFIGURED_NOTE)
        input_summary = _input_summary(
            project=project,
            variables=variables,
            experiments=experiments,
            objective_profile=objective_profile,
            cost_profile=cost_profile,
            safety_profile=safety_profile,
            bo_run=bo_run,
            batch=batch,
            recommendation_count=len(recommendations),
        )
        run_row = ReactionOptimizationAdvisorRunORM(
            reaction_project_id=project_id,
            bo_run_id=bo_run.id if bo_run is not None else None,
            recommendation_batch_id=batch.id if batch is not None else None,
            status="running",
            advisor_mode=mode,
            input_summary_json=_json_dump(input_summary),
            advisor_output_json="{}",
            warnings_json="[]",
            notes_json=_json_dump(notes),
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "requested_advisor_mode": payload.advisor_mode,
                    "human_review_required": True,
                }
            ),
        )
        session.add(run_row)
        session.flush()

        context = _AdvisorContext(
            project=project,
            experiments=experiments,
            variables=variables,
            design_space=design_space,
            cost_profile=cost_profile,
            safety_profile=safety_profile,
            completed_count=sum(1 for item in experiments if item.status == "completed"),
            outcome_variance=_outcome_variance(experiments),
        )
        run_warnings = _run_warnings(context, recommendations)
        warnings.extend(run_warnings)
        critique_rows: list[ReactionConditionCritiqueORM] = []
        for recommendation in recommendations:
            critique = _build_critique_payload(context, recommendation, advisor_run_id=run_row.id)
            critique_row = _create_critique_row(
                session,
                project_id=project_id,
                recommendation_id=recommendation.get("recommendation_id"),
                advisor_run_id=run_row.id,
                critique=critique,
                metadata={"source": "advisor_run"},
            )
            critique_rows.append(critique_row)

        critique_dicts = [_critique_to_record(row).model_dump(mode="json") for row in critique_rows]
        hypotheses = _advisor_hypotheses(context, critique_dicts)
        agreements, disagreements = _agreements_and_disagreements(recommendations, critique_dicts)
        output = {
            "critiques": critique_dicts,
            "hypotheses": hypotheses,
            "agreements": agreements,
            "disagreements": disagreements,
            "suggested_controls": _collect_unique(critique_dicts, "suggested_controls"),
            "suggested_alternatives": _collect_unique(critique_dicts, "suggested_alternatives"),
            "recommendation_count": len(recommendations),
            "human_review_required": True,
            "advisor_scope": "critique_and_context_only",
        }
        status = "requires_review" if context.completed_count < 5 or not recommendations else "succeeded"
        if recommendations:
            status = "succeeded"
        run_row.status = status
        run_row.advisor_output_json = _json_dump(output)
        run_row.warnings_json = _json_dump(warnings)
        run_row.notes_json = _json_dump(notes)
        run_row.finished_at = utcnow()
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.advisor.run",
            message="Reaction optimization advisor run completed.",
            entity_type="reaction_optimization_advisor_run",
            entity_id=run_row.id,
            metadata={"project_id": project_id, "recommendation_count": len(recommendations)},
        )
        return _advisor_run_to_record(run_row)


def list_advisor_runs(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionOptimizationAdvisorRun]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionOptimizationAdvisorRunORM)
            .where(ReactionOptimizationAdvisorRunORM.reaction_project_id == project_id)
            .order_by(ReactionOptimizationAdvisorRunORM.id.desc())
        ).all()
        return [_advisor_run_to_record(row) for row in rows]


def get_advisor_run(
    session_factory: sessionmaker[Session],
    advisor_run_id: int,
) -> ReactionOptimizationAdvisorRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionOptimizationAdvisorRunORM, advisor_run_id)
        return _advisor_run_to_record(row) if row is not None else None


def review_advisor_run(
    session_factory: sessionmaker[Session],
    advisor_run_id: int,
    payload: ReactionAdvisorReviewRequest,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationAdvisorRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionOptimizationAdvisorRunORM, advisor_run_id)
        if row is None:
            return None
        metadata = _json_dict(row.metadata_json)
        metadata["review"] = {
            "reviewer_name": payload.reviewer_name or actor.email,
            "decision": payload.decision,
            "rationale": payload.rationale,
            "reviewed_at": utcnow().isoformat(),
            "metadata_json": payload.metadata_json,
        }
        row.metadata_json = _json_dump(metadata)
        _audit(
            session,
            actor=actor,
            event_type="reaction.advisor.review",
            message="Reaction advisor output reviewed.",
            entity_type="reaction_optimization_advisor_run",
            entity_id=row.id,
            metadata={"project_id": row.reaction_project_id, "decision": payload.decision},
        )
        return _advisor_run_to_record(row)


def create_recommendation_critique(
    session_factory: sessionmaker[Session],
    recommendation_id: int,
    payload: ReactionConditionCritiqueRequest,
    *,
    actor: ReactionActor,
) -> ReactionConditionCritique | None:
    with session_scope(session_factory) as session:
        recommendation = session.get(ReactionRecommendationORM, recommendation_id)
        if recommendation is None:
            return None
        project_id = recommendation.reaction_project_id
        _project_or_raise(session, project_id)
        context = _AdvisorContext(
            project=session.get(ReactionProjectORM, project_id),
            experiments=_project_experiments(session, project_id),
            variables=_project_variables(session, project_id),
            design_space=_latest_design_space(session, project_id),
            cost_profile=_latest_cost_profile(session, project_id),
            safety_profile=_latest_safety_profile(session, project_id),
            completed_count=sum(
                1 for item in _project_experiments(session, project_id) if item.status == "completed"
            ),
            outcome_variance=_outcome_variance(_project_experiments(session, project_id)),
        )
        advisor_run = None
        if payload.advisor_run_id is not None:
            advisor_run = session.get(ReactionOptimizationAdvisorRunORM, payload.advisor_run_id)
            if advisor_run is None or advisor_run.reaction_project_id != project_id:
                raise KeyError("Reaction advisor run not found.")
        recommendation_payload = _recommendation_payload(session, recommendation)
        critique = _build_critique_payload(
            context,
            recommendation_payload,
            advisor_run_id=advisor_run.id if advisor_run is not None else None,
        )
        row = _create_critique_row(
            session,
            project_id=project_id,
            recommendation_id=recommendation_id,
            advisor_run_id=advisor_run.id if advisor_run is not None else None,
            critique=critique,
            metadata={"source": "recommendation_critique", **payload.metadata_json},
        )
        _audit(
            session,
            actor=actor,
            event_type="reaction.advisor.critique",
            message="Reaction recommendation critique created.",
            entity_type="reaction_condition_critique",
            entity_id=row.id,
            metadata={"project_id": project_id, "recommendation_id": recommendation_id},
        )
        return _critique_to_record(row)


def get_recommendation_critique(
    session_factory: sessionmaker[Session],
    recommendation_id: int,
) -> ReactionConditionCritique | None:
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(ReactionConditionCritiqueORM)
            .where(ReactionConditionCritiqueORM.recommendation_id == recommendation_id)
            .order_by(ReactionConditionCritiqueORM.id.desc())
        )
        return _critique_to_record(row) if row is not None else None


def create_hypothesis(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionMechanisticHypothesisCreate,
    *,
    actor: ReactionActor,
) -> ReactionMechanisticHypothesis:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionMechanisticHypothesisORM(
            reaction_project_id=project_id,
            title=payload.title,
            hypothesis=payload.hypothesis,
            supporting_observations_json=_json_dump(payload.supporting_observations_json),
            contradicting_observations_json=_json_dump(payload.contradicting_observations_json),
            confidence_label=payload.confidence_label,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.mechanistic_hypothesis.create",
            message="Reaction mechanistic hypothesis created.",
            entity_type="reaction_mechanistic_hypothesis",
            entity_id=row.id,
            metadata={"project_id": project_id, "confidence_label": row.confidence_label},
        )
        return _hypothesis_to_record(row)


def list_hypotheses(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionMechanisticHypothesis]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionMechanisticHypothesisORM)
            .where(ReactionMechanisticHypothesisORM.reaction_project_id == project_id)
            .order_by(ReactionMechanisticHypothesisORM.id.desc())
        ).all()
        return [_hypothesis_to_record(row) for row in rows]


def patch_hypothesis(
    session_factory: sessionmaker[Session],
    hypothesis_id: int,
    payload: ReactionMechanisticHypothesisUpdate,
    *,
    actor: ReactionActor,
) -> ReactionMechanisticHypothesis | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionMechanisticHypothesisORM, hypothesis_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("title", "hypothesis", "confidence_label", "status"):
            if field in update and update[field] is not None:
                setattr(row, field, update[field])
        for field in (
            "supporting_observations_json",
            "contradicting_observations_json",
            "metadata_json",
        ):
            if field in update:
                setattr(row, field, _json_dump(update[field] if update[field] is not None else []))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.mechanistic_hypothesis.update",
            message="Reaction mechanistic hypothesis updated.",
            entity_type="reaction_mechanistic_hypothesis",
            entity_id=row.id,
            metadata={"project_id": row.reaction_project_id, "updated_fields": sorted(update)},
        )
        return _hypothesis_to_record(row)


def create_literature_prior(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionLiteraturePriorCreate,
    *,
    actor: ReactionActor,
) -> ReactionLiteraturePrior:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionLiteraturePriorORM(
            reaction_project_id=project_id,
            source_type=payload.source_type,
            title=payload.title,
            summary=payload.summary,
            citation=payload.citation,
            relevance_tags_json=_json_dump(payload.relevance_tags_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.literature_prior.create",
            message="Reaction literature prior created.",
            entity_type="reaction_literature_prior",
            entity_id=row.id,
            metadata={"project_id": project_id, "source_type": row.source_type},
        )
        return _literature_prior_to_record(row)


def list_literature_priors(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionLiteraturePrior]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionLiteraturePriorORM)
            .where(ReactionLiteraturePriorORM.reaction_project_id == project_id)
            .order_by(ReactionLiteraturePriorORM.id.desc())
        ).all()
        return [_literature_prior_to_record(row) for row in rows]


def compare_bo_advisor(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionOptimizationDebateRequest,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationDebate:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        bo_run = _resolve_bo_run(session, project_id, payload.bo_run_id)
        advisor_run = _resolve_advisor_run(session, project_id, payload.advisor_run_id)
        bo_summary = _bo_summary(session, bo_run) if bo_run is not None else {}
        advisor_summary = _json_dict(advisor_run.advisor_output_json) if advisor_run is not None else {}
        agreements, disagreements = _compare_bo_and_advisor(bo_summary, advisor_summary)
        final = _final_review_recommendation(disagreements)
        row = ReactionOptimizationDebateORM(
            reaction_project_id=project_id,
            bo_run_id=bo_run.id if bo_run is not None else None,
            advisor_run_id=advisor_run.id if advisor_run is not None else None,
            bo_summary_json=_json_dump(bo_summary),
            advisor_summary_json=_json_dump(advisor_summary),
            agreements_json=_json_dump(agreements),
            disagreements_json=_json_dump(disagreements),
            final_review_recommendation=final,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.advisor.compare_bo_llm",
            message="Reaction BO and advisor comparison created.",
            entity_type="reaction_optimization_debate",
            entity_id=row.id,
            metadata={"project_id": project_id, "bo_run_id": row.bo_run_id, "advisor_run_id": row.advisor_run_id},
        )
        return _debate_to_record(row)


def list_comparisons(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionOptimizationDebate]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionOptimizationDebateORM)
            .where(ReactionOptimizationDebateORM.reaction_project_id == project_id)
            .order_by(ReactionOptimizationDebateORM.id.desc())
        ).all()
        return [_debate_to_record(row) for row in rows]


class _AdvisorContext:
    def __init__(
        self,
        *,
        project: ReactionProjectORM | None,
        experiments: list[ReactionExperimentORM],
        variables: list[ReactionVariableORM],
        design_space: ReactionDesignSpaceORM | None,
        cost_profile: ReactionCostProfileORM | None,
        safety_profile: ReactionSafetyConstraintProfileORM | None,
        completed_count: int,
        outcome_variance: dict[str, float],
    ) -> None:
        self.project = project
        self.experiments = experiments
        self.variables = variables
        self.design_space = design_space
        self.cost_profile = cost_profile
        self.safety_profile = safety_profile
        self.completed_count = completed_count
        self.outcome_variance = outcome_variance
        self.observed_conditions = [_json_dict(row.conditions_json) for row in experiments]


def _build_critique_payload(
    context: _AdvisorContext,
    recommendation: dict[str, Any],
    *,
    advisor_run_id: int | None,
) -> dict[str, Any]:
    conditions = _condition_payload(recommendation)
    risk_flags: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    alternatives: list[dict[str, Any]] = []
    safety_status = str(recommendation.get("safety_status") or "unknown")
    label = str(recommendation.get("label") or "")
    uncertainty = _float_or_none(recommendation.get("uncertainty"))
    cost = _float_or_none(recommendation.get("estimated_cost"))
    duplicate = _is_duplicate_condition(conditions, context.observed_conditions)

    if context.completed_count < 5:
        risk_flags.append(_flag("insufficient_information", "medium", "Fewer than 5 completed experiments are available."))
        controls.append(_control("Add reviewed baseline and control reactions before scheduling suggested variants."))
    if safety_status == "blocked" or label == "safety_blocked":
        risk_flags.append(_flag("safety_violation", "high", "Safety status is blocked and requires review."))
        controls.append(_control("Do not schedule this condition unless safety constraints are revised by a human reviewer."))
    elif safety_status == "warning":
        risk_flags.append(_flag("safety_review", "medium", "Safety controls should be confirmed before review."))
    if uncertainty is not None and uncertainty >= 0.5:
        risk_flags.append(_flag("high_uncertainty", "medium", "Prediction uncertainty is high enough to require cautious review."))
        controls.append(_control("Consider a replicate or bracketed nearby condition to separate noise from trend."))
    high_cost, cost_limit = _high_cost(cost, context.cost_profile)
    if high_cost:
        risk_flags.append(_flag("high_cost", "medium", "Estimated cost is a potential concern."))
        alternatives.append(_alternative("Evaluate a lower-cost catalyst, ligand, or solvent variant before review."))
    unexplored = _unexplored_categorical_values(conditions, context)
    for name, value in unexplored:
        risk_flags.append(_flag("unexplored_categorical", "low", f"{name}={value!r} has limited direct history."))
    if _temperature_boundary(conditions, context):
        risk_flags.append(_flag("temperature_boundary", "medium", "Temperature lies at a configured or observed boundary."))
        controls.append(_control("Include a midpoint or neighboring temperature condition for context."))
    if duplicate:
        risk_flags.append(_flag("condition_duplication", "low", "Condition duplicates an existing experiment."))
        alternatives.append(_alternative("Modify one variable or use the run as a deliberate replicate/control."))
    if context.outcome_variance.get("yield_percent", 0.0) >= 15.0:
        risk_flags.append(_flag("outcome_variance", "medium", "Yield variance is high across completed experiments."))
        controls.append(_control("Use a replicate before treating small predicted differences as chemically meaningful."))
    if not _has_control_context(context):
        risk_flags.append(_flag("missing_control", "low", "No explicit control experiment was detected."))
        controls.append(_control("Add a negative or standard-condition control before relying on ranked suggestions."))

    critique_recommendation = _critique_recommendation(context.completed_count, safety_status, label, risk_flags)
    mechanistic = _mechanistic_rationale(conditions, risk_flags)
    practicality = _practicality_assessment(conditions, duplicate, unexplored)
    cost_text = _cost_assessment(cost, high_cost, cost_limit)
    safety_text = _safety_assessment(safety_status, risk_flags)
    return {
        "recommendation_id": recommendation.get("recommendation_id"),
        "advisor_run_id": advisor_run_id,
        "condition_summary_json": {
            "conditions_json": conditions,
            "predicted_score": recommendation.get("predicted_score"),
            "expected_improvement": recommendation.get("expected_improvement"),
            "uncertainty": uncertainty,
            "estimated_cost": cost,
            "safety_status": safety_status,
            "label": label,
        },
        "mechanistic_rationale": mechanistic,
        "practicality_assessment": practicality,
        "cost_assessment": cost_text,
        "safety_assessment": safety_text,
        "risk_flags_json": risk_flags,
        "suggested_controls_json": controls,
        "suggested_alternatives_json": alternatives,
        "recommendation": critique_recommendation,
    }


def _create_critique_row(
    session: Session,
    *,
    project_id: int,
    recommendation_id: int | None,
    advisor_run_id: int | None,
    critique: dict[str, Any],
    metadata: dict[str, Any],
) -> ReactionConditionCritiqueORM:
    row = ReactionConditionCritiqueORM(
        reaction_project_id=project_id,
        recommendation_id=recommendation_id,
        advisor_run_id=advisor_run_id,
        condition_summary_json=_json_dump(critique["condition_summary_json"]),
        mechanistic_rationale=critique["mechanistic_rationale"],
        practicality_assessment=critique["practicality_assessment"],
        cost_assessment=critique["cost_assessment"],
        safety_assessment=critique["safety_assessment"],
        risk_flags_json=_json_dump(critique["risk_flags_json"]),
        suggested_controls_json=_json_dump(critique["suggested_controls_json"]),
        suggested_alternatives_json=_json_dump(critique["suggested_alternatives_json"]),
        recommendation=critique["recommendation"],
        human_review_required=True,
        metadata_json=_json_dump({**metadata, "human_review_required": True}),
    )
    session.add(row)
    session.flush()
    return row


def _run_warnings(context: _AdvisorContext, recommendations: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if context.completed_count < 5:
        warnings.append("Insufficient information: fewer than 5 completed experiments are available.")
    if any(str(item.get("safety_status")) == "blocked" or item.get("label") == "safety_blocked" for item in recommendations):
        warnings.append("At least one BO recommendation is safety blocked; advisor will not suggest approval.")
    if any(_high_cost(_float_or_none(item.get("estimated_cost")), context.cost_profile)[0] for item in recommendations):
        warnings.append("At least one recommendation has a high-cost potential concern.")
    if any((_float_or_none(item.get("uncertainty")) or 0.0) >= 0.5 for item in recommendations):
        warnings.append("At least one recommendation carries high uncertainty and requires review.")
    if context.outcome_variance.get("yield_percent", 0.0) >= 15.0:
        warnings.append("Outcome variance is high; a replicate is suggested before interpreting small differences.")
    return warnings


def _advisor_hypotheses(context: _AdvisorContext, critiques: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    risk_types = {
        flag["type"]
        for critique in critiques
        for flag in critique.get("risk_flags", [])
        if isinstance(flag, dict) and "type" in flag
    }
    if "temperature_boundary" in risk_types:
        hypotheses.append(
            {
                "title": "Temperature sensitivity may be important",
                "hypothesis": "Boundary-temperature recommendations are plausible probes but should be bracketed by chemically reasonable controls.",
                "confidence_label": "speculative" if context.completed_count < 5 else "medium",
                "human_review_required": True,
            }
        )
    if "unexplored_categorical" in risk_types:
        hypotheses.append(
            {
                "title": "Unexplored categorical choice may shift selectivity",
                "hypothesis": "A new solvent, catalyst, ligand, or reagent category may change conversion and impurity formation; evidence is suggested rather than definitive.",
                "confidence_label": "speculative",
                "human_review_required": True,
            }
        )
    if not hypotheses:
        hypotheses.append(
            {
                "title": "Current recommendations need contextual review",
                "hypothesis": "Available BO suggestions are chemically reasonable only as review candidates; additional controls may clarify whether observed trends are robust.",
                "confidence_label": "low",
                "human_review_required": True,
            }
        )
    return hypotheses


def _agreements_and_disagreements(
    recommendations: list[dict[str, Any]],
    critiques: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    agreements: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    for recommendation, critique in zip(recommendations, critiques, strict=False):
        label = recommendation.get("label")
        rec_id = recommendation.get("recommendation_id")
        critique_rec = critique.get("recommendation")
        if label in {"high_expected_improvement", "cost_efficient_candidate"} and critique_rec == "accept_for_review":
            agreements.append({"recommendation_id": rec_id, "summary": "BO priority and advisor critique both support human review."})
        elif label == "safety_blocked" or critique_rec in {"reject_or_deprioritize", "modify_before_review", "insufficient_information"}:
            disagreements.append(
                {
                    "recommendation_id": rec_id,
                    "bo_label": label,
                    "advisor_recommendation": critique_rec,
                    "summary": "Advisor adds a review concern that should be resolved before scheduling.",
                }
            )
        else:
            agreements.append({"recommendation_id": rec_id, "summary": "Advisor found no hard contradiction, but review is still required."})
    return agreements, disagreements


def _compare_bo_and_advisor(
    bo_summary: dict[str, Any],
    advisor_summary: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recommendations = bo_summary.get("recommendations", [])
    critiques = advisor_summary.get("critiques", [])
    agreements, disagreements = _agreements_and_disagreements(
        recommendations if isinstance(recommendations, list) else [],
        critiques if isinstance(critiques, list) else [],
    )
    if not recommendations:
        disagreements.append({"summary": "No BO recommendations were available for comparison."})
    if not critiques:
        disagreements.append({"summary": "No advisor critiques were available for comparison."})
    return agreements, disagreements


def _advisor_recommendations(
    session: Session,
    project_id: int,
    bo_run: ReactionBayesianOptimizationRunORM | None,
    batch: ReactionRecommendationBatchORM | None,
) -> list[dict[str, Any]]:
    if batch is not None:
        recs = _json_list(batch.recommendations_json)
        return [item for item in recs if isinstance(item, dict)]
    if bo_run is not None:
        candidates = session.scalars(
            select(ReactionAcquisitionCandidateORM)
            .where(ReactionAcquisitionCandidateORM.bo_run_id == bo_run.id)
            .order_by(ReactionAcquisitionCandidateORM.rank.asc())
        ).all()
        return [_candidate_payload(row) for row in candidates]
    latest_bo = _resolve_bo_run(session, project_id, None)
    if latest_bo is not None:
        return _advisor_recommendations(session, project_id, latest_bo, None)
    rows = session.scalars(
        select(ReactionRecommendationORM)
        .where(ReactionRecommendationORM.reaction_project_id == project_id)
        .order_by(ReactionRecommendationORM.rank.asc(), ReactionRecommendationORM.id.asc())
        .limit(10)
    ).all()
    return [_recommendation_payload(session, row) for row in rows]


def _candidate_payload(row: ReactionAcquisitionCandidateORM) -> dict[str, Any]:
    metadata = _json_dict(row.metadata_json)
    return {
        "acquisition_candidate_id": row.id,
        "recommendation_id": metadata.get("recommendation_id"),
        "rank": row.rank,
        "conditions_json": _json_dict(row.conditions_json),
        "predicted_score": row.predicted_score,
        "expected_improvement": row.expected_improvement,
        "uncertainty": row.uncertainty,
        "estimated_cost": row.estimated_cost,
        "safety_status": row.safety_status,
        "acquisition_score": row.acquisition_score,
        "label": row.label,
        "rationale": row.rationale,
        "metadata_json": metadata,
    }


def _recommendation_payload(session: Session, row: ReactionRecommendationORM) -> dict[str, Any]:
    metadata = _json_dict(row.metadata_json)
    candidate = None
    candidate_id = metadata.get("acquisition_candidate_id")
    if candidate_id is not None:
        candidate = session.get(ReactionAcquisitionCandidateORM, int(candidate_id))
    if candidate is not None:
        payload = _candidate_payload(candidate)
        payload["recommendation_id"] = row.id
        return payload
    predicted = _json_dict(row.predicted_outcome_json)
    uncertainty = _json_dict(row.uncertainty_json)
    return {
        "recommendation_id": row.id,
        "rank": row.rank,
        "conditions_json": _json_dict(row.conditions_json),
        "predicted_score": predicted.get("predicted_score"),
        "expected_improvement": predicted.get("expected_improvement"),
        "uncertainty": uncertainty.get("uncertainty"),
        "estimated_cost": predicted.get("estimated_cost"),
        "safety_status": metadata.get("safety_status", "unknown"),
        "acquisition_score": predicted.get("acquisition_score"),
        "label": row.label,
        "rationale": row.rationale,
        "metadata_json": metadata,
    }


def _condition_payload(recommendation: dict[str, Any]) -> dict[str, Any]:
    conditions = recommendation.get("conditions_json")
    return conditions if isinstance(conditions, dict) else {}


def _critique_recommendation(
    completed_count: int,
    safety_status: str,
    label: str,
    risk_flags: list[dict[str, Any]],
) -> str:
    if completed_count < 5:
        return "insufficient_information"
    if safety_status == "blocked" or label == "safety_blocked":
        return "reject_or_deprioritize"
    high_or_medium = [flag for flag in risk_flags if flag.get("severity") in {"high", "medium"}]
    if high_or_medium:
        return "modify_before_review"
    return "accept_for_review"


def _mechanistic_rationale(conditions: dict[str, Any], risk_flags: list[dict[str, Any]]) -> str:
    names = ", ".join(sorted(str(key) for key in conditions)) or "the proposed condition"
    if any(flag.get("type") == "safety_violation" for flag in risk_flags):
        return f"{names} is not chemically reasonable to advance without safety review because a hard safety concern is present."
    if any(flag.get("type") == "insufficient_information" for flag in risk_flags):
        return f"{names} may be plausible, but there is insufficient information to separate mechanistic trend from sparse data."
    if any(flag.get("type") == "unexplored_categorical" for flag in risk_flags):
        return f"{names} is a suggested probe of categorical reaction effects; changes in solvent, catalyst, ligand, or reagent class may affect selectivity and impurity formation."
    return f"{names} is a plausible follow-up for review; the rationale is contextual rather than autonomous scheduling guidance."


def _practicality_assessment(
    conditions: dict[str, Any],
    duplicate: bool,
    unexplored: list[tuple[str, Any]],
) -> str:
    if duplicate:
        return "Condition duplicates existing work; it is practical mainly as a deliberate replicate or control."
    if unexplored:
        return "Condition includes an unexplored categorical choice and is practical only after inventory, setup, and review checks."
    if not conditions:
        return "Insufficient information is available to assess practicality."
    return "Condition appears practical for human review based on structured metadata, pending local feasibility checks."


def _cost_assessment(cost: float | None, high_cost: bool, cost_limit: float | None) -> str:
    if cost is None:
        return "No structured cost estimate is available; cost requires review."
    if high_cost:
        limit_text = f" against limit {cost_limit:g}" if cost_limit is not None else ""
        return f"Estimated cost {cost:g}{limit_text} is a potential concern."
    return f"Estimated cost {cost:g} does not trigger the configured high-cost warning."


def _safety_assessment(safety_status: str, risk_flags: list[dict[str, Any]]) -> str:
    if safety_status == "blocked":
        return "Safety status is blocked; advisor does not recommend approval."
    if safety_status == "warning":
        return "Safety status carries a warning and requires review of controls."
    if any(flag.get("type") == "safety_violation" for flag in risk_flags):
        return "Safety concern is present and must be resolved before scheduling."
    if safety_status == "allowed":
        return "Safety status is allowed in the current profile, but human review remains required."
    return "Safety status is unknown and requires review."


def _high_cost(cost: float | None, cost_profile: ReactionCostProfileORM | None) -> tuple[bool, float | None]:
    if cost is None:
        return False, cost_profile.max_cost_per_experiment if cost_profile is not None else None
    limit = cost_profile.max_cost_per_experiment if cost_profile is not None else None
    if limit is not None:
        return cost > limit, limit
    return cost >= 100.0, None


def _unexplored_categorical_values(
    conditions: dict[str, Any],
    context: _AdvisorContext,
) -> list[tuple[str, Any]]:
    categorical_names = {
        variable.name
        for variable in context.variables
        if variable.variable_type == "categorical"
    }
    if context.design_space is not None:
        categorical_names.update(_json_dict(context.design_space.categorical_variables_json))
    observed_by_name: dict[str, set[str]] = {name: set() for name in categorical_names}
    for observed in context.observed_conditions:
        for name in categorical_names:
            if name in observed:
                observed_by_name.setdefault(name, set()).add(str(observed[name]))
    unexplored: list[tuple[str, Any]] = []
    for name in categorical_names:
        if name in conditions and str(conditions[name]) not in observed_by_name.get(name, set()):
            unexplored.append((name, conditions[name]))
    return unexplored


def _temperature_boundary(conditions: dict[str, Any], context: _AdvisorContext) -> bool:
    temperature = _first_numeric_condition(conditions, ("temperature_c", "temperature", "temp_c"))
    if temperature is None:
        return False
    bounds: list[tuple[float, float]] = []
    for variable in context.variables:
        if variable.variable_type == "numeric" and "temp" in variable.name.lower():
            if variable.min_value is not None and variable.max_value is not None:
                bounds.append((variable.min_value, variable.max_value))
    if context.design_space is not None:
        for name, spec in _json_dict(context.design_space.numeric_variables_json).items():
            if "temp" not in str(name).lower():
                continue
            values = _numeric_values(spec)
            if values:
                bounds.append((min(values), max(values)))
    for low, high in bounds:
        if abs(temperature - low) < 1e-9 or abs(temperature - high) < 1e-9:
            return True
    return False


def _is_duplicate_condition(conditions: dict[str, Any], observed_conditions: list[dict[str, Any]]) -> bool:
    key = _condition_key(conditions)
    return any(_condition_key(item) == key for item in observed_conditions)


def _has_control_context(context: _AdvisorContext) -> bool:
    for row in context.experiments:
        haystack = f"{row.experiment_code} {row.conditions_json} {row.metadata_json}".lower()
        if "control" in haystack or "blank" in haystack:
            return True
    return False


def _outcome_variance(experiments: list[ReactionExperimentORM]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for row in experiments:
        if row.status != "completed":
            continue
        outcome = _json_dict(row.outcome_json)
        for field in ("yield_percent", "selectivity_percent", "impurity_percent", "conversion_percent"):
            value = _float_or_none(outcome.get(field))
            if value is not None:
                values.setdefault(field, []).append(value)
    return {field: round(_std(items), 6) for field, items in values.items()}


def _input_summary(
    *,
    project: ReactionProjectORM,
    variables: list[ReactionVariableORM],
    experiments: list[ReactionExperimentORM],
    objective_profile: ReactionObjectiveProfileORM | None,
    cost_profile: ReactionCostProfileORM | None,
    safety_profile: ReactionSafetyConstraintProfileORM | None,
    bo_run: ReactionBayesianOptimizationRunORM | None,
    batch: ReactionRecommendationBatchORM | None,
    recommendation_count: int,
) -> dict[str, Any]:
    completed = [row for row in experiments if row.status == "completed"]
    return {
        "project": {"id": project.id, "name": project.name, "objective": project.objective},
        "variable_count": len(variables),
        "experiment_count": len(experiments),
        "completed_experiment_count": len(completed),
        "objective_profile": _profile_ref(objective_profile, "objective_type"),
        "cost_profile": _profile_ref(cost_profile),
        "safety_profile": _profile_ref(safety_profile),
        "bo_run_id": bo_run.id if bo_run is not None else None,
        "recommendation_batch_id": batch.id if batch is not None else None,
        "recommendation_count": recommendation_count,
    }


def _profile_ref(row: Any | None, label_field: str | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    output = {"id": row.id}
    if label_field is not None:
        output[label_field] = getattr(row, label_field)
    return output


def _bo_summary(session: Session, row: ReactionBayesianOptimizationRunORM) -> dict[str, Any]:
    candidates = session.scalars(
        select(ReactionAcquisitionCandidateORM)
        .where(ReactionAcquisitionCandidateORM.bo_run_id == row.id)
        .order_by(ReactionAcquisitionCandidateORM.rank.asc())
    ).all()
    return {
        "bo_run_id": row.id,
        "algorithm": row.algorithm,
        "cost_aware": row.cost_aware,
        "safety_aware": row.safety_aware,
        "recommendations": [_candidate_payload(candidate) for candidate in candidates],
        "diagnostics": _json_dict(row.diagnostics_json),
    }


def _final_review_recommendation(disagreements: list[dict[str, Any]]) -> str:
    if disagreements:
        return "modify_before_review: advisor identified potential concerns that require review."
    return "accept_for_review: BO and advisor summaries are aligned, with human review still required."


def _collect_unique(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        values = item.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            marker = _condition_key(value if isinstance(value, dict) else {"value": value})
            if marker not in seen:
                seen.add(marker)
                output.append(value if isinstance(value, dict) else {"value": value})
    return output


def _flag(flag_type: str, severity: str, message: str) -> dict[str, Any]:
    return {"type": flag_type, "severity": severity, "message": message}


def _control(description: str) -> dict[str, Any]:
    return {"description": description, "human_review_required": True}


def _alternative(description: str) -> dict[str, Any]:
    return {"description": description, "human_review_required": True}


def _resolve_bo_run(
    session: Session,
    project_id: int,
    bo_run_id: int | None,
) -> ReactionBayesianOptimizationRunORM | None:
    if bo_run_id is not None:
        row = session.get(ReactionBayesianOptimizationRunORM, bo_run_id)
        if row is None or row.reaction_project_id != project_id:
            raise KeyError("Reaction Bayesian optimization run not found.")
        return row
    return session.scalar(
        select(ReactionBayesianOptimizationRunORM)
        .where(ReactionBayesianOptimizationRunORM.reaction_project_id == project_id)
        .order_by(ReactionBayesianOptimizationRunORM.id.desc())
    )


def _resolve_batch(
    session: Session,
    project_id: int,
    batch_id: int | None,
) -> ReactionRecommendationBatchORM | None:
    if batch_id is None:
        return None
    row = session.get(ReactionRecommendationBatchORM, batch_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction recommendation batch not found.")
    return row


def _resolve_advisor_run(
    session: Session,
    project_id: int,
    advisor_run_id: int | None,
) -> ReactionOptimizationAdvisorRunORM | None:
    if advisor_run_id is not None:
        row = session.get(ReactionOptimizationAdvisorRunORM, advisor_run_id)
        if row is None or row.reaction_project_id != project_id:
            raise KeyError("Reaction advisor run not found.")
        return row
    return session.scalar(
        select(ReactionOptimizationAdvisorRunORM)
        .where(ReactionOptimizationAdvisorRunORM.reaction_project_id == project_id)
        .order_by(ReactionOptimizationAdvisorRunORM.id.desc())
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


def _latest_safety_profile(session: Session, project_id: int) -> ReactionSafetyConstraintProfileORM | None:
    return session.scalar(
        select(ReactionSafetyConstraintProfileORM)
        .where(ReactionSafetyConstraintProfileORM.reaction_project_id == project_id)
        .order_by(ReactionSafetyConstraintProfileORM.id.desc())
    )


def _latest_design_space(session: Session, project_id: int) -> ReactionDesignSpaceORM | None:
    return session.scalar(
        select(ReactionDesignSpaceORM)
        .where(ReactionDesignSpaceORM.reaction_project_id == project_id)
        .order_by(ReactionDesignSpaceORM.id.desc())
    )


def _advisor_run_to_record(row: ReactionOptimizationAdvisorRunORM) -> ReactionOptimizationAdvisorRun:
    output = _json_dict(row.advisor_output_json)
    warnings = [str(item) for item in _json_list(row.warnings_json)]
    notes = [str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE]
    metadata = _json_dict(row.metadata_json)
    return ReactionOptimizationAdvisorRun(
        id=row.id,
        advisor_run_id=row.id,
        reaction_project_id=row.reaction_project_id,
        bo_run_id=row.bo_run_id,
        recommendation_batch_id=row.recommendation_batch_id,
        status=row.status,  # type: ignore[arg-type]
        advisor_mode=row.advisor_mode,  # type: ignore[arg-type]
        input_summary_json=_json_dict(row.input_summary_json),
        advisor_output_json=output,
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=metadata,
        recommendation_count=int(output.get("recommendation_count") or 0),
        critiques=output.get("critiques", []) if isinstance(output.get("critiques"), list) else [],
        hypotheses=output.get("hypotheses", []) if isinstance(output.get("hypotheses"), list) else [],
        agreements=output.get("agreements", []) if isinstance(output.get("agreements"), list) else [],
        disagreements=output.get("disagreements", []) if isinstance(output.get("disagreements"), list) else [],
        suggested_controls=output.get("suggested_controls", []) if isinstance(output.get("suggested_controls"), list) else [],
        suggested_alternatives=output.get("suggested_alternatives", []) if isinstance(output.get("suggested_alternatives"), list) else [],
        warnings=warnings,
        notes=notes,
        human_review_required=True,
        metadata=metadata,
    )


def _critique_to_record(row: ReactionConditionCritiqueORM) -> ReactionConditionCritique:
    risk_flags = _json_list(row.risk_flags_json)
    controls = _json_list(row.suggested_controls_json)
    alternatives = _json_list(row.suggested_alternatives_json)
    return ReactionConditionCritique(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        recommendation_id=row.recommendation_id,
        advisor_run_id=row.advisor_run_id,
        condition_summary_json=_json_dict(row.condition_summary_json),
        mechanistic_rationale=row.mechanistic_rationale,
        practicality_assessment=row.practicality_assessment,
        cost_assessment=row.cost_assessment,
        safety_assessment=row.safety_assessment,
        risk_flags_json=[item for item in risk_flags if isinstance(item, dict)],
        suggested_controls_json=[item for item in controls if isinstance(item, dict)],
        suggested_alternatives_json=[item for item in alternatives if isinstance(item, dict)],
        recommendation=row.recommendation,  # type: ignore[arg-type]
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        risk_flags=[item for item in risk_flags if isinstance(item, dict)],
        suggested_controls=[item for item in controls if isinstance(item, dict)],
        suggested_alternatives=[item for item in alternatives if isinstance(item, dict)],
    )


def _hypothesis_to_record(row: ReactionMechanisticHypothesisORM) -> ReactionMechanisticHypothesis:
    return ReactionMechanisticHypothesis(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        title=row.title,
        hypothesis=row.hypothesis,
        supporting_observations_json=_json_value(row.supporting_observations_json) or [],
        contradicting_observations_json=_json_value(row.contradicting_observations_json) or [],
        confidence_label=row.confidence_label,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _literature_prior_to_record(row: ReactionLiteraturePriorORM) -> ReactionLiteraturePrior:
    return ReactionLiteraturePrior(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        source_type=row.source_type,  # type: ignore[arg-type]
        title=row.title,
        summary=row.summary,
        citation=row.citation,
        relevance_tags_json=_json_value(row.relevance_tags_json) or [],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _debate_to_record(row: ReactionOptimizationDebateORM) -> ReactionOptimizationDebate:
    agreements = [item for item in _json_list(row.agreements_json) if isinstance(item, dict)]
    disagreements = [item for item in _json_list(row.disagreements_json) if isinstance(item, dict)]
    return ReactionOptimizationDebate(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        bo_run_id=row.bo_run_id,
        advisor_run_id=row.advisor_run_id,
        bo_summary_json=_json_dict(row.bo_summary_json),
        advisor_summary_json=_json_dict(row.advisor_summary_json),
        agreements_json=agreements,
        disagreements_json=disagreements,
        final_review_recommendation=row.final_review_recommendation,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        agreements=agreements,
        disagreements=disagreements,
        human_review_required=True,
    )


def _first_numeric_condition(conditions: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    lower_map = {str(key).lower(): value for key, value in conditions.items()}
    for key in keys:
        value = _float_or_none(lower_map.get(key))
        if value is not None:
            return value
    return None


def _numeric_values(spec: Any) -> list[float]:
    if isinstance(spec, list):
        return sorted({value for item in spec if (value := _float_or_none(item)) is not None})
    if isinstance(spec, dict):
        if isinstance(spec.get("values"), list):
            return _numeric_values(spec["values"])
        low = _float_or_none(spec.get("min", spec.get("min_value")))
        high = _float_or_none(spec.get("max", spec.get("max_value")))
        if low is not None and high is not None:
            return [low, high]
    return []


def _condition_key(conditions: dict[str, Any]) -> str:
    return json.dumps(conditions, sort_keys=True, separators=(",", ":"), default=str)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


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
