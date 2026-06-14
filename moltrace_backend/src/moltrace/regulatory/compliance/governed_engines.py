"""Annex 22 governance bound to every Prompt 4–8 regulatory decision (Prompt 12 finalization).

EU GMP Draft Annex 22 requires every AI-assisted regulatory decision to be documented, explainable,
hash-chained for tamper evidence, risk-tiered, and — for high-risk — gated behind human review.
Prompt 12 mandates the wrapper be applied to ALL functions in Prompts 4–8. This module provides a
**governed counterpart** for each of those decision functions, built with
:func:`with_annex22_governance`, so a caller gets full governance by calling ``governed_*`` instead
of the bare engine. The deterministic engines themselves are NOT decorated (their bare callables
stay zero-overhead and return their result objects directly, as the deterministic-first router,
the worked-example validation suite, and the API all rely on).

A completeness gate — :func:`assert_full_p4_p8_governance` — fails the build if any P4–P8 decision
lacks a governed binding, so the wrap can never silently regress.

Annex 22 is in DRAFT (July 2025); this is decision-support governance, never an 'Annex 22 compliant'
claim (see the wrapper's ``DRAFT_DISCLAIMER``).

P4–P8 coverage:
* Prompt 4 — ICH M7 mutagenic-impurity classifier (``classify_m7``); risk is high for a mutagenic
  class (1–3), low otherwise.
* Prompt 5 — FDA CPCA nitrosamine classifier (``classify_cpca``) + cumulative-risk verdict
  (``calculate_cumulative_risk``); high-risk.
* Prompt 6 — ICH Q6A specification builder (``build_specification``); high-risk (QA sign-off).
* Prompt 7 — FDA OOS investigation workflow (``run_oos_investigation``); high-risk (batch
  disposition is the quality unit's call).
* Prompt 8 — CTD Module 3 generators (``generate_3s3_impurities_drug_substance``,
  ``generate_3p5_impurities``); medium-risk drafts for regulatory-affairs review.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from moltrace.regulatory.compliance.annex22_wrapper import (
    DecisionMeta,
    GovernedResult,
    with_annex22_governance,
)
from moltrace.regulatory.ctd.module3_generator import (
    generate_3p5_impurities,
    generate_3s3_impurities_drug_substance,
)
from moltrace.regulatory.impurities import (
    calculate_cumulative_risk,
    classify_cpca,
    classify_m7,
)
from moltrace.regulatory.infra import content_hash
from moltrace.regulatory.quality.oos_investigation import run_oos_investigation
from moltrace.regulatory.specifications.q6a_builder import build_specification

__all__ = [
    "Annex22GovernanceError",
    "GOVERNED_ENGINES",
    "REQUIRED_P4_P8_DECISIONS",
    "assert_full_p4_p8_governance",
    "governed_build_specification",
    "governed_calculate_cumulative_risk",
    "governed_classify_cpca",
    "governed_classify_m7",
    "governed_engine",
    "governed_generate_3p5_impurities",
    "governed_generate_3s3_impurities_drug_substance",
    "governed_run_oos_investigation",
    "ungoverned_p4_p8",
]


class Annex22GovernanceError(RuntimeError):
    """Raised when a P4–P8 decision function lacks an Annex 22 governed binding."""


def _model_version(result: Any) -> str:
    """A stable version string for the decision: rule_set_version, else a content hash."""

    rule_set_version = getattr(result, "rule_set_version", None)
    if rule_set_version:
        return str(rule_set_version)
    content_hasher = getattr(result, "content_hash", None)
    if callable(content_hasher):
        return str(content_hasher())
    if hasattr(result, "as_dict"):
        return content_hash(result.as_dict())
    return "unversioned"


def _output(result: Any) -> dict[str, Any]:
    return result.as_dict() if hasattr(result, "as_dict") else {"value": str(result)}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


# --------------------------------------------------------------------------- #
# Per-engine extracts — feature_attribution carries the real decision drivers
# (Annex 22 explainability), confidence is 1.0 (deterministic rule engines).
# --------------------------------------------------------------------------- #
def _m7_extract(fn, result, args, kwargs) -> DecisionMeta:
    return DecisionMeta(
        model_name="ich_m7_classifier",
        model_version=_model_version(result),
        output=_output(result),
        confidence=1.0,
        feature_attribution={
            "m7_class": result.m7_class,
            "in_silico_concordance": result.in_silico_concordance,
            "structural_alerts": list(result.structural_alerts),
            "coc_flag": result.coc_flag,
            "ttc_ug_per_day": result.ttc_ug_per_day,
        },
        regulatory_basis=result.regulatory_basis,
    )


def _m7_risk(result: Any) -> str:
    """ICH M7 criticality: a mutagenic class (1–3) is high-risk; class 4–5 is low."""

    return "high" if result.m7_class in (1, 2, 3) else "low"


def _cpca_extract(fn, result, args, kwargs) -> DecisionMeta:
    return DecisionMeta(
        model_name="fda_cpca_classifier",
        model_version=_model_version(result),
        output=_output(result),
        confidence=1.0,
        feature_attribution={
            "category": result.category,
            "ai_limit_ng_per_day": result.ai_limit_ng_per_day,
            "activating_features": list(result.activating_features),
            "deactivating_features": list(result.deactivating_features),
            "coc_flag": result.coc_flag,
        },
        regulatory_basis=result.regulatory_basis,
    )


def _cumulative_extract(
    fn, result, args, kwargs
) -> DecisionMeta:
    return DecisionMeta(
        model_name="fda_cpca_cumulative_risk",
        model_version=_model_version(result),
        output=_output(result),
        confidence=1.0,
        feature_attribution={
            "total_risk_ratio": result.total_risk_ratio,
            "passes": result.passes,
            "n_components": len(result.components),
        },
        regulatory_basis=result.regulatory_basis,
    )


def _spec_extract(fn, result, args, kwargs) -> DecisionMeta:
    return DecisionMeta(
        model_name="ich_q6a_specification_builder",
        model_version=_model_version(result),
        output=_output(result),
        confidence=1.0,
        feature_attribution={
            "substance_name": result.substance_name,
            "dosage_form": result.dosage_form,
            "parameters": [p.parameter for p in result.parameters],
        },
        regulatory_basis="ICH Q6A",
    )


def _oos_extract(fn, result, args, kwargs) -> DecisionMeta:
    return DecisionMeta(
        model_name="fda_oos_investigation",
        model_version=_model_version(result),
        output=_output(result),
        confidence=1.0,
        feature_attribution={
            "final_decision": _enum_value(result.final_decision),
            "investigation_id": result.investigation_id,
            "regulatory_actions": [_enum_value(a) for a in result.regulatory_actions],
            "qa_review_status": result.qa_review_status,
        },
        regulatory_basis=result.guidance_basis,
    )


def _ctd_extract(fn, result, args, kwargs) -> DecisionMeta:
    return DecisionMeta(
        model_name="ctd_module3_generator",
        model_version=_model_version(result),
        output=_output(result),
        confidence=1.0,
        feature_attribution={
            "section_number": result.section_number,
            "m4q_reference": result.m4q_reference,
            "is_draft": result.is_draft,
            "n_subsections": len(result.subsections),
        },
        regulatory_basis=result.m4q_reference,
    )


# --------------------------------------------------------------------------- #
# Governed bindings — with_annex22_governance applied to every P4–P8 function
# --------------------------------------------------------------------------- #
governed_classify_m7 = with_annex22_governance(
    decision_type="m7_classification", extract=_m7_extract, risk_fn=_m7_risk
)(classify_m7)

governed_classify_cpca = with_annex22_governance(
    "high", decision_type="cpca_classification", extract=_cpca_extract
)(classify_cpca)

governed_calculate_cumulative_risk = with_annex22_governance(
    "high", decision_type="cpca_cumulative_risk", extract=_cumulative_extract
)(calculate_cumulative_risk)

governed_build_specification = with_annex22_governance(
    "high", decision_type="q6a_specification", extract=_spec_extract
)(build_specification)

governed_run_oos_investigation = with_annex22_governance(
    "high", decision_type="oos_investigation", extract=_oos_extract
)(run_oos_investigation)

governed_generate_3s3_impurities_drug_substance = with_annex22_governance(
    "medium", decision_type="ctd_module3_3s3", extract=_ctd_extract
)(generate_3s3_impurities_drug_substance)

governed_generate_3p5_impurities = with_annex22_governance(
    "medium", decision_type="ctd_module3_3p5", extract=_ctd_extract
)(generate_3p5_impurities)


#: The P4–P8 decision functions that MUST carry an Annex 22 governed binding.
REQUIRED_P4_P8_DECISIONS: dict[str, str] = {
    "m7_classification": "Prompt 4 — ICH M7 mutagenic-impurity classifier",
    "cpca_classification": "Prompt 5 — FDA CPCA nitrosamine classifier",
    "cpca_cumulative_risk": "Prompt 5 — nitrosamine cumulative-risk verdict",
    "q6a_specification": "Prompt 6 — ICH Q6A specification builder",
    "oos_investigation": "Prompt 7 — FDA OOS investigation workflow",
    "ctd_module3_3s3": "Prompt 8 — CTD 3.2.S.3.2 drug-substance impurities",
    "ctd_module3_3p5": "Prompt 8 — CTD 3.2.P.5.5/.6 product impurities",
}

#: decision_type -> governed callable (returns a GovernedResult).
GOVERNED_ENGINES: dict[str, Callable[..., GovernedResult]] = {
    "m7_classification": governed_classify_m7,
    "cpca_classification": governed_classify_cpca,
    "cpca_cumulative_risk": governed_calculate_cumulative_risk,
    "q6a_specification": governed_build_specification,
    "oos_investigation": governed_run_oos_investigation,
    "ctd_module3_3s3": governed_generate_3s3_impurities_drug_substance,
    "ctd_module3_3p5": governed_generate_3p5_impurities,
}


def governed_engine(decision_type: str) -> Callable[..., GovernedResult]:
    """Look up the governed callable for a decision type."""

    try:
        return GOVERNED_ENGINES[decision_type]
    except KeyError:
        raise Annex22GovernanceError(
            f"no governed engine for decision_type {decision_type!r}"
        ) from None


def ungoverned_p4_p8(
    registry: Mapping[str, Callable[..., GovernedResult]] | None = None,
) -> list[str]:
    """Required P4–P8 decision types that have no governed binding in ``registry`` (sorted)."""

    reg = GOVERNED_ENGINES if registry is None else registry
    return sorted(decision for decision in REQUIRED_P4_P8_DECISIONS if decision not in reg)


def assert_full_p4_p8_governance(
    registry: Mapping[str, Callable[..., GovernedResult]] | None = None,
) -> None:
    """Raise unless EVERY P4–P8 decision function has an Annex 22 governed binding."""

    missing = ungoverned_p4_p8(registry)
    if missing:
        raise Annex22GovernanceError(
            "P4–P8 decision functions without an Annex 22 governed binding: "
            + ", ".join(f"{d} ({REQUIRED_P4_P8_DECISIONS[d]})" for d in missing)
        )
