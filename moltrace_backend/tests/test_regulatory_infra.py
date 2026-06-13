"""Unit tests for the Regentry Phase 0 foundation (Prompt 19, regulatory/infra).

Covers the acceptance criteria: every metric implemented + unit-tested with the two
zero-tolerance hard gates (calculation-error rate 0, formula coverage 100%);
content-addressed versioning of rule-sets/corpus/gold-sets; per-run tracking of the
metric vector + versions + git SHA; fail-loud schema validation of every structured
input; and the versioned GAMP 5 D11 / CSV validation-document skeleton.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.infra import (
    CalculationCheck,
    CitationCheck,
    ClaimCheck,
    DataValidationError,
    NarrativeReview,
    NativeRunStore,
    RegulatoryMetricVector,
    artifact_for,
    assert_valid_compound_record,
    assert_valid_corpus_document,
    assert_valid_dose,
    assert_valid_impurity_list,
    build_regulatory_validation_document,
    calculation_error_rate,
    citation_correctness,
    classification_accuracy,
    content_hash,
    enforce_full_coverage,
    enforce_hard_gates,
    enforce_zero_calculation_errors,
    formula_coverage,
    hallucination_rate,
    levenshtein,
    log_regulatory_run,
    mean_edit_distance,
    missing_formulas,
    narrative_acceptance_rate,
    needs_review_precision,
    normalized_edit_distance,
    regulatory_tracker,
    rule_set_version,
    validate_compound_record,
    validate_corpus_document,
    validate_dose,
    validate_impurity_list,
)
from moltrace.regulatory.infra.eval import HardGateError


# --------------------------------------------------------------------------- #
# Hard gate 1: calculation-error rate must be 0
# --------------------------------------------------------------------------- #
def test_calculation_error_rate_and_zero_gate():
    ok = [CalculationCheck("q3a_id", 0.10, 0.10), CalculationCheck("q3a_qual", 0.15, 0.15)]
    assert calculation_error_rate(ok) == 0.0
    enforce_zero_calculation_errors(ok)  # does not raise

    bad = ok + [CalculationCheck("q3c_pde", 4.1, 4.0)]
    assert calculation_error_rate(bad) == pytest.approx(1 / 3)
    with pytest.raises(HardGateError):
        enforce_zero_calculation_errors(bad)


def test_calculation_check_tolerance_is_absolute_and_exact_by_default():
    assert CalculationCheck("x", 0.10001, 0.10).is_error()  # exact by default
    assert not CalculationCheck("x", 1.004, 1.0, tolerance=0.01).is_error()
    assert CalculationCheck("x", 1.02, 1.0, tolerance=0.01).is_error()


# --------------------------------------------------------------------------- #
# Hard gate 2: formula coverage must be 100%
# --------------------------------------------------------------------------- #
def test_formula_coverage_and_full_gate():
    assert formula_coverage(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert formula_coverage(["a"], ["a", "b", "c"]) == pytest.approx(1 / 3)
    assert missing_formulas(["a"], ["a", "b", "c"]) == ["b", "c"]
    enforce_full_coverage(["a", "b"], ["a", "b"])  # does not raise
    with pytest.raises(HardGateError):
        enforce_full_coverage(["a"], ["a", "b"])


def test_enforce_hard_gates_requires_both_measured_and_satisfied():
    enforce_hard_gates(RegulatoryMetricVector(calculation_error_rate=0.0, formula_coverage=1.0))
    # unmeasured hard-gate metric fails loudly
    with pytest.raises(HardGateError):
        enforce_hard_gates(RegulatoryMetricVector(calculation_error_rate=0.0))
    # measured but failing
    with pytest.raises(HardGateError):
        enforce_hard_gates(RegulatoryMetricVector(calculation_error_rate=0.5, formula_coverage=1.0))
    with pytest.raises(HardGateError):
        enforce_hard_gates(RegulatoryMetricVector(calculation_error_rate=0.0, formula_coverage=0.9))


# --------------------------------------------------------------------------- #
# Quality metrics
# --------------------------------------------------------------------------- #
def test_classification_accuracy_vs_expert():
    acc = classification_accuracy(["1", "1", "2", "3"], ["1", "2", "2", "3"])
    assert acc.accuracy == pytest.approx(0.75)
    assert acc.n == 4
    assert 0.0 <= acc.macro_f1 <= 1.0


def test_citation_correctness_and_hallucination_rate():
    checks = [CitationCheck("a", "ICH M7", True), CitationCheck("b", "ICH M7", False)]
    assert citation_correctness(checks) == 0.5
    assert citation_correctness([]) == 1.0  # vacuously correct
    assert hallucination_rate([ClaimCheck("a", True), ClaimCheck("b", False)]) == 0.5
    assert hallucination_rate([]) == 0.0


def test_narrative_acceptance_and_edit_distance():
    assert narrative_acceptance_rate([NarrativeReview("x", "x"), NarrativeReview("y", "z")]) == 0.5
    assert levenshtein("kitten", "sitting") == 3
    assert normalized_edit_distance("abc", "abc") == 0.0
    assert mean_edit_distance([NarrativeReview("abc", "abd")]) == pytest.approx(1 / 3)


def test_needs_review_precision():
    # tp=1 (T,T), fp=1 (T,F), fn=1 (F,T)
    prf = needs_review_precision([True, True, False, False], [True, False, True, False])
    assert prf.precision == 0.5
    assert prf.recall == 0.5


def test_metric_vector_hash_is_deterministic():
    a = RegulatoryMetricVector(calculation_error_rate=0.0, formula_coverage=1.0, citation_correctness=1.0)
    b = RegulatoryMetricVector(calculation_error_rate=0.0, formula_coverage=1.0, citation_correctness=1.0)
    assert a.content_hash() == b.content_hash()
    assert a.content_hash().startswith("sha256:")
    assert a.hard_gates_pass is True


# --------------------------------------------------------------------------- #
# Versioning — content-addressed, no blobs in git
# --------------------------------------------------------------------------- #
def test_rule_set_version_is_content_addressed():
    rs = {"guideline": "ICH Q3C(R8)", "class3_pde_mg_day": 50}
    assert rule_set_version(rs) == rule_set_version(dict(rs))
    assert rule_set_version(rs) != rule_set_version({**rs, "class3_pde_mg_day": 51})
    assert rule_set_version(rs).startswith("sha256:")


def test_artifact_for_pins_identity_hash_with_provenance():
    art = artifact_for(
        "rule_set",
        {"a": 1},
        semver="1.0.0",
        source_guidance="ICH Q3C(R8)",
        effective_date="2021-01-01",
    )
    assert art.identity_hash == content_hash({"a": 1})
    assert art.kind == "rule_set"
    assert art.source_guidance == "ICH Q3C(R8)"


# --------------------------------------------------------------------------- #
# Tracking — every run logs metrics + versions + git SHA
# --------------------------------------------------------------------------- #
def test_log_regulatory_run_records_metrics_versions_and_git_sha(tmp_path):
    root = str(tmp_path / "runs")
    tracker = regulatory_tracker(tracking_root=root, backend="native")
    vector = RegulatoryMetricVector(
        calculation_error_rate=0.0, formula_coverage=1.0, classification_accuracy=0.95
    )
    run_id = log_regulatory_run(
        tracker,
        run_name="eval",
        metric_vector=vector,
        rule_set_version="sha256:rs",
        model_versions={"m7": "1.0.0"},
        corpus_version="sha256:corpus",
    )
    assert run_id

    store = NativeRunStore(root)
    assert run_id in store.list_runs("moltrace-regulatory")
    record = store.read("moltrace-regulatory", run_id)
    assert record["metrics"]["classification_accuracy"] == 0.95
    assert record["metrics"]["formula_coverage"] == 1.0
    assert record["params"]["rule_set_version"] == "sha256:rs"
    assert record["dataset_version"] == "sha256:corpus"
    assert record["git_sha"]  # provenance stamped


# --------------------------------------------------------------------------- #
# Validation — fail loudly on every structured input
# --------------------------------------------------------------------------- #
def test_validate_dose():
    assert validate_dose(
        {"daily_dose_g": 1.5, "route": "oral", "substance_type": "drug_substance"}
    ).success
    report = validate_dose({"daily_dose_g": -1, "route": "warp", "substance_type": "foo"})
    assert not report.success
    assert len(report.failures) == 3
    with pytest.raises(DataValidationError):
        assert_valid_dose({"daily_dose_g": 0})


def test_validate_compound_record():
    assert validate_compound_record({"smiles": "CCO", "name": "ethanol"}).success
    with pytest.raises(DataValidationError):
        assert_valid_compound_record({"smiles": ""})


def test_validate_impurity_list_spectracheck_handoff():
    good = {"impurities": [{"identifier": "imp-A", "level": 0.12, "unit": "percent"}]}
    assert validate_impurity_list(good).success
    bad = {"impurities": [{"identifier": "", "level": -1.0, "unit": "furlongs"}]}
    report = validate_impurity_list(bad)
    assert not report.success
    assert len(report.failures) >= 3  # identifier + level + unit
    assert not validate_impurity_list({"impurities": "not-a-list"}).success
    with pytest.raises(DataValidationError):
        assert_valid_impurity_list({"impurities": [{"identifier": "x", "level": "NaN", "unit": "ppm"}]})


def test_validate_corpus_document():
    good = {
        "source": "ICH",
        "document_id": "Q3C(R8)",
        "effective_date": "2021-03-01",
        "licence": "copyright-internal-cite-only",
        "content_hash": "sha256:abc",
        "text": "Class 3 PDE 50 mg/day ...",
    }
    assert validate_corpus_document(good).success
    with pytest.raises(DataValidationError):
        assert_valid_corpus_document(
            {"source": "", "document_id": "x", "effective_date": "not-a-date", "licence": "x"}
        )


# --------------------------------------------------------------------------- #
# GAMP 5 D11 / CSV validation-document skeleton — versioned + deterministic
# --------------------------------------------------------------------------- #
def test_gamp5_validation_document_versioned_and_deterministic():
    rsv = "sha256:rule-set-abc123"
    doc1 = build_regulatory_validation_document(rule_set_version=rsv)
    doc2 = build_regulatory_validation_document(rule_set_version=rsv)
    assert doc1 == doc2  # deterministic skeleton
    assert rsv in doc1  # pinned to the exact rule-set version (System Version)
    assert "Validation" in doc1
    assert "MolTrace Regentry" in doc1
    # decision-support framing present (no autonomous "compliant" claim about the product)
    assert "responsibility" in doc1.lower()


def test_gamp5_document_prefills_metric_vector_when_supplied():
    vector = RegulatoryMetricVector(calculation_error_rate=0.0, formula_coverage=1.0)
    doc = build_regulatory_validation_document(rule_set_version="sha256:x", metric_vector=vector)
    assert "Metric Vector" in doc
    assert "formula_coverage" in doc
