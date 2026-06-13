"""Prompt 17 zero-tolerance gates + Prompt 21 worked examples.

Worked examples are built up incrementally, one calculator at a time, with the zero-error gate
enforced from line one: SMILES -> ICH M7 + CPCA + Q3A/B thresholds, every regulated number checked
against guideline ground truth. Then the harness: evaluate() -> metric vector, the hard gates, the
dominance gate, gold-set checksum enforcement, and CI exit codes.

Ground-truth values are the guideline-traceable ones the engine unit tests already validate
(test_regulatory_q3ab/m7/cpca), reused here in the harness format so the worked examples are not
circular.
"""

from __future__ import annotations

import dataclasses

import pytest

from moltrace.regulatory.eval import (
    EvaluationBundle,
    GoldSet,
    GoldSetChecksumError,
    evaluate,
    gate,
    promotion_exit_code,
    validation_record,
)
from moltrace.regulatory.impurities import (
    calculate_q3ab_thresholds,
    classify_cpca,
    classify_m7,
)
from moltrace.regulatory.infra.eval import (
    CalculationCheck,
    HardGateError,
    RegulatoryMetricVector,
    calculation_error_rate,
    enforce_hard_gates,
    enforce_zero_calculation_errors,
)

# ICH Q3A(R2) Attachment 1 (drug substance): (dose_g, reporting%, identification%, qualification%)
Q3AB_WORKED = [
    (0.5, 0.05, 0.10, 0.15),
    (1.0, 0.05, 0.10, 0.10),  # qualification capped by the 1.0 mg/day absolute = 0.10%
    (2.0, 0.05, 0.05, 0.05),
]
# ICH M7(R2): SMILES -> expert-adjudicated class
M7_WORKED = [("NDMA", "CN(C)N=O", 2)]  # N-nitroso Cohort of Concern -> class 2
# FDA Nitrosamine Rev 2 / CPCA: SMILES -> (category, ai_limit_ng_per_day FDA or None)
CPCA_WORKED = [
    ("NMBzA", "O=NN(C)Cc1ccccc1", 1, 26.5),
    ("di-tert-butyl nitrosamine", "O=NN(C(C)(C)C)C(C)(C)C", 5, None),
]

_TOL = 1e-9  # guideline percents are exact to far more than this; tolerates only float ULP noise
REQUIRED_FORMULAS = ["q3ab_thresholds", "m7_classification", "cpca_classification"]


# --------------------------------------------------------------------------- #
# Worked examples, incrementally per calculator — zero-error gate from line one
# --------------------------------------------------------------------------- #
def _q3ab_checks() -> list[CalculationCheck]:
    checks: list[CalculationCheck] = []
    for dose, reporting, identification, qualification in Q3AB_WORKED:
        t = calculate_q3ab_thresholds(dose, "drug_substance")
        checks.append(
            CalculationCheck(f"q3ab_reporting@{dose}g", t.reporting_threshold.effective_percent, reporting, _TOL)
        )
        checks.append(
            CalculationCheck(
                f"q3ab_identification@{dose}g", t.identification_threshold.effective_percent, identification, _TOL
            )
        )
        checks.append(
            CalculationCheck(
                f"q3ab_qualification@{dose}g", t.qualification_threshold.effective_percent, qualification, _TOL
            )
        )
    return checks


def _cpca_ai_limit_checks() -> list[CalculationCheck]:
    checks: list[CalculationCheck] = []
    for name, smiles, _category, ai_limit in CPCA_WORKED:
        if ai_limit is None:
            continue
        c = classify_cpca(smiles)
        checks.append(CalculationCheck(f"cpca_ai_limit:{name}", c.ai_limit_ng_per_day, ai_limit, _TOL))
    return checks


def test_q3ab_threshold_worked_examples_are_zero_error() -> None:
    checks = _q3ab_checks()
    enforce_zero_calculation_errors(checks)  # raises HardGateError on any wrong number
    assert calculation_error_rate(checks) == 0.0


def test_m7_classification_worked_examples_match_expert() -> None:
    for _name, smiles, expected_class in M7_WORKED:
        assert classify_m7(smiles).m7_class == expected_class


def test_cpca_worked_examples_are_zero_error_and_correctly_classified() -> None:
    enforce_zero_calculation_errors(_cpca_ai_limit_checks())  # ai-limit is a regulated number
    for _name, smiles, expected_category, _ai in CPCA_WORKED:
        assert classify_cpca(smiles).category == expected_category


def test_smiles_to_full_m7_cpca_thresholds_report_is_zero_error() -> None:
    # SMILES -> ICH M7 + CPCA + thresholds, one combined regulated report with no calc errors.
    smiles = "CN(C)N=O"  # NDMA
    m7 = classify_m7(smiles)
    cpca = classify_cpca(smiles)
    thresholds = calculate_q3ab_thresholds(1.0, "drug_substance")
    report = {
        "smiles": smiles,
        "m7_class": m7.m7_class,
        "cpca_category": cpca.category,
        "cpca_ai_limit_ng_per_day": cpca.ai_limit_ng_per_day,
        "q3ab": {
            "reporting": thresholds.reporting_threshold.effective_percent,
            "identification": thresholds.identification_threshold.effective_percent,
            "qualification": thresholds.qualification_threshold.effective_percent,
        },
    }
    checks = [
        CalculationCheck("report_ai_limit", report["cpca_ai_limit_ng_per_day"], 26.5, _TOL),
        CalculationCheck("report_reporting", report["q3ab"]["reporting"], 0.05, _TOL),
        CalculationCheck("report_qualification", report["q3ab"]["qualification"], 0.10, _TOL),
    ]
    enforce_zero_calculation_errors(checks)
    assert report["m7_class"] == 2 and report["cpca_category"] == 1


# --------------------------------------------------------------------------- #
# The harness — evaluate() over the worked-example gold set + the hard gates
# --------------------------------------------------------------------------- #
def _gold_set() -> GoldSet:
    return GoldSet.freeze(
        "worked-examples-v1",
        {"q3ab": Q3AB_WORKED, "m7": M7_WORKED, "cpca": [c[:3] for c in CPCA_WORKED]},
    )


def _worked_bundle() -> EvaluationBundle:
    predicted = [classify_m7(s).m7_class for _n, s, _c in M7_WORKED] + [
        classify_cpca(s).category for _n, s, _cat, _ai in CPCA_WORKED
    ]
    expert = [c for _n, _s, c in M7_WORKED] + [cat for _n, _s, cat, _ai in CPCA_WORKED]
    return EvaluationBundle(
        gold_set=_gold_set(),
        required_formulas=REQUIRED_FORMULAS,
        implemented_formulas=REQUIRED_FORMULAS,
        calculation_checks=[*_q3ab_checks(), *_cpca_ai_limit_checks()],
        predicted_classes=predicted,
        expert_classes=expert,
        latencies_ms=[12.0, 18.0, 25.0, 40.0],
        versions={"engine": "test"},
    )


def test_evaluate_passes_hard_gates_on_correct_worked_examples() -> None:
    vector = evaluate(_worked_bundle(), timestamp="2026-06-12T00:00:00Z")
    assert vector.calculation_error_rate == 0.0
    assert vector.formula_coverage == 1.0
    assert vector.classification_accuracy == 1.0
    assert vector.latency_p50_ms is not None and vector.latency_p95_ms is not None
    assert vector.metadata["gold_checksum"].startswith("sha256:")
    enforce_hard_gates(vector)  # does not raise


def test_evaluate_refuses_on_gold_set_checksum_drift() -> None:
    bundle = _worked_bundle()
    # mutate the gold-set manifest after it was frozen
    tampered_gold = dataclasses.replace(bundle.gold_set, manifest={"q3ab": [(9.9, 9, 9, 9)]})
    tampered = dataclasses.replace(bundle, gold_set=tampered_gold)
    with pytest.raises(GoldSetChecksumError):
        evaluate(tampered)


def test_incomplete_coverage_fails_the_hard_gate() -> None:
    bundle = dataclasses.replace(_worked_bundle(), implemented_formulas=["q3ab_thresholds"])
    vector = evaluate(bundle)
    assert vector.formula_coverage < 1.0
    with pytest.raises(HardGateError):
        enforce_hard_gates(vector)


# --------------------------------------------------------------------------- #
# The dominance gate
# --------------------------------------------------------------------------- #
def _incumbent() -> RegulatoryMetricVector:
    return RegulatoryMetricVector(
        formula_coverage=1.0,
        calculation_error_rate=0.0,
        classification_accuracy=0.90,
        citation_correctness=0.95,
        hallucination_rate=0.05,
    )


def test_gate_promotes_a_strictly_better_candidate() -> None:
    candidate = dataclasses.replace(_incumbent(), classification_accuracy=0.95)  # strictly better
    passed, deltas = gate(candidate, _incumbent())
    assert passed is True
    assert any(d.metric == "classification_accuracy" and d.improved for d in deltas)
    assert all(not d.blocks for d in deltas)


def test_gate_requires_a_strict_improvement() -> None:
    # identical vectors -> dominates nothing -> not promotable
    passed, _ = gate(_incumbent(), _incumbent())
    assert passed is False


def test_calculation_error_is_a_hard_blocker_regardless_of_gains() -> None:
    candidate = dataclasses.replace(
        _incumbent(), calculation_error_rate=0.01, classification_accuracy=0.99
    )
    passed, deltas = gate(candidate, _incumbent())
    assert passed is False
    assert any(d.metric == "calculation_error_rate" and d.blocks for d in deltas)


def test_citation_regression_is_a_hard_blocker() -> None:
    candidate = dataclasses.replace(
        _incumbent(), citation_correctness=0.90, classification_accuracy=0.99
    )
    passed, deltas = gate(candidate, _incumbent())
    assert passed is False
    assert any(d.metric == "citation_correctness" and d.blocks for d in deltas)


def test_coverage_below_100_blocks_promotion() -> None:
    candidate = dataclasses.replace(
        _incumbent(), formula_coverage=0.99, classification_accuracy=0.99
    )
    passed, _ = gate(candidate, _incumbent())
    assert passed is False


def test_promotion_exit_code_and_validation_record() -> None:
    better = dataclasses.replace(_incumbent(), classification_accuracy=0.95)
    assert promotion_exit_code(better, _incumbent()) == 0
    assert promotion_exit_code(_incumbent(), _incumbent()) == 1  # no improvement

    record = validation_record(better, _incumbent())
    assert record["promotable"] is True
    assert record["blockers"] == []
    assert record["candidate_hash"].startswith("sha256:")
    assert any(d["metric"] == "classification_accuracy" for d in record["deltas"])
