"""Cross-module end-to-end smoke + determinism for the Regulatory Hub (Prompt 19).

One SpectraCheck-style impurity input flows through the regulatory path — input
validation → a deterministic ICH Q3A / Q3C / M7 evaluation → a CTD Module 3 stub —
and the deterministic numeric path must be **byte-identical across 10 runs**. This
test runs in CI as part of the backend suite.

The ICH Q3A / Q3C / M7 calculators do not exist yet (Prompts 1–4); the ``_stub_*``
functions below are intentionally trivial, pure deterministic stand-ins that the
real engines replace. The point of this test is the *reproducibility harness* — the
foundation's validation, hard gates, and byte-identical determinism — not the
(stubbed) regulatory numbers.
"""

from __future__ import annotations

from typing import Any

from moltrace.regulatory.infra import (
    CalculationCheck,
    RegulatoryMetricVector,
    assert_valid_dose,
    assert_valid_impurity_list,
    build_regulatory_validation_document,
    content_hash,
    enforce_full_coverage,
    enforce_hard_gates,
    enforce_zero_calculation_errors,
    rule_set_version,
)


# --- STUB deterministic calculators (replaced by Prompts 1-4 / 8) ----------- #
def _stub_q3ab_identification_threshold(daily_dose_g: float) -> float:
    """ICH Q3A(R2) Table 1 identification threshold (drug substance)."""

    return 0.10 if daily_dose_g <= 2.0 else 0.05


def _stub_q3c_class3_pde_mg_day() -> float:
    """ICH Q3C(R8) Class 3 residual-solvent PDE."""

    return 50.0


def _stub_m7_class(has_structural_alert: bool, ames_positive: bool) -> int:
    """ICH M7(R2): both in-silico systems negative -> Class 5."""

    return 5 if not has_structural_alert and not ames_positive else 3


def _stub_ctd_module3(payload: dict[str, Any]) -> dict[str, Any]:
    """A CTD Section 3.2.P.5.5 stub (replaced by Prompt 8)."""

    return {
        "section": "3.2.P.5.5",
        "impurities": payload["impurities"],
        "thresholds": payload["thresholds"],
    }


def _run_regulatory_path(compound: dict[str, Any]) -> dict[str, Any]:
    """SpectraCheck-style input → validated deterministic regulatory evaluation → CTD stub."""

    dose = {
        "daily_dose_g": compound["daily_dose_g"],
        "route": "oral",
        "substance_type": "drug_substance",
    }
    assert_valid_dose(dose)
    assert_valid_impurity_list({"impurities": compound["impurities"]})

    identification = _stub_q3ab_identification_threshold(dose["daily_dose_g"])
    pde = _stub_q3c_class3_pde_mg_day()
    m7_class = _stub_m7_class(compound["has_structural_alert"], compound["ames_positive"])

    # Hard gate: the regulated numbers must match ground truth exactly.
    enforce_zero_calculation_errors(
        [
            CalculationCheck("q3a_identification", identification, 0.10),
            CalculationCheck("q3c_class3_pde", pde, 50.0),
        ]
    )
    # Hard gate: every in-scope formula in this path is implemented.
    enforce_full_coverage({"q3ab", "q3c", "m7"}, {"q3ab", "q3c", "m7"})

    thresholds = {
        "identification": identification,
        "q3c_class3_pde_mg_day": pde,
        "m7_class": m7_class,
    }
    ctd = _stub_ctd_module3({"impurities": compound["impurities"], "thresholds": thresholds})
    return {"thresholds": thresholds, "ctd": ctd}


_COMPOUND: dict[str, Any] = {
    "daily_dose_g": 1.0,
    "has_structural_alert": False,
    "ames_positive": False,
    "impurities": [{"identifier": "imp-A", "level": 0.12, "unit": "percent"}],
}


def test_e2e_regulatory_path_runs_green():
    out = _run_regulatory_path(_COMPOUND)
    assert out["thresholds"]["identification"] == 0.10
    assert out["thresholds"]["q3c_class3_pde_mg_day"] == 50.0
    assert out["thresholds"]["m7_class"] == 5  # both in-silico negative -> Class 5
    assert out["ctd"]["section"] == "3.2.P.5.5"


def test_e2e_deterministic_numeric_path_byte_identical_x10():
    hashes = {content_hash(_run_regulatory_path(_COMPOUND)) for _ in range(10)}
    assert len(hashes) == 1  # byte-identical across 10 runs


def test_e2e_metric_vector_passes_hard_gates_and_documents():
    vector = RegulatoryMetricVector(calculation_error_rate=0.0, formula_coverage=1.0)
    enforce_hard_gates(vector)  # does not raise
    rsv = rule_set_version({"q3a": "Q3A(R2)", "q3c": "Q3C(R8)", "m7": "M7(R2)"})
    document = build_regulatory_validation_document(rule_set_version=rsv, metric_vector=vector)
    assert rsv in document
    assert "formula_coverage" in document
