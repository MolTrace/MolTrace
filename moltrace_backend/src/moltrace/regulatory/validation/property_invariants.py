"""ICH invariants for property-based testing (Prompt 21, Phase 7).

Each invariant is a pure assertion that must hold for *all* valid inputs — a guideline property the
deterministic engine can never violate (e.g. a permitted concentration scales inversely with dose, a
class label is always in the valid enum, the cumulative-risk verdict uses a strict ``< 1`` rule).
These functions are fuzzed by Hypothesis in the test suite AND run over a fixed deterministic grid
here, so the GAMP 5 CSV package can record a reproducible property-test result.
"""

from __future__ import annotations

from dataclasses import dataclass

from moltrace.regulatory.impurities import (
    calculate_concentration_limit,
    calculate_cumulative_risk,
    calculate_q3ab_thresholds,
    classify_cpca,
    classify_m7,
    get_element_pde,
)

__all__ = [
    "InvariantResult",
    "InvariantViolation",
    "assert_cpca_category_valid",
    "assert_cpca_cumulative_strict_rule",
    "assert_m7_class_valid",
    "assert_q3ab_thresholds_well_formed",
    "assert_q3d_class_valid",
    "assert_q3d_permitted_inverse_monotonic_in_dose",
    "run_property_invariants",
]

_EPS = 1e-9
_Q3D_CLASSES = frozenset({"1", "2A", "2B", "3"})
# Elements with an encoded oral PDE (ICH Q3D Table A.2.1 subset).
_Q3D_ELEMENTS = ("As", "Cd", "Pb", "Hg", "Co", "Ni", "V")
# Valid structures for the structure-based classifiers (Hypothesis cannot synthesise valid SMILES).
_VALID_SMILES = (
    "CN(C)N=O",  # NDMA
    "CCN(CC)N=O",  # NDEA
    "O=NN(C)Cc1ccccc1",  # NMBzA
    "O=NN(C(C)(C)C)C(C)(C)C",  # di-tert-butyl nitrosamine
    "Nc1ccccc1",  # aniline
    "CCOS(=O)(=O)C",  # EMS
)


class InvariantViolation(AssertionError):
    """Raised when an ICH invariant does not hold for some valid input."""


@dataclass(frozen=True)
class InvariantResult:
    """The deterministic-grid outcome for one invariant."""

    name: str
    cases: int
    passed: bool
    failures: tuple[str, ...]


# --------------------------------------------------------------------------- #
# Invariant assertions (raise InvariantViolation on failure)
# --------------------------------------------------------------------------- #
def assert_q3ab_thresholds_well_formed(daily_dose_g: float, substance_type: str) -> None:
    """Q3A/B threshold percents are in (0, 100]; qualification is never stricter than reporting."""

    t = calculate_q3ab_thresholds(daily_dose_g, substance_type)
    for name, th in (
        ("reporting", t.reporting_threshold),
        ("identification", t.identification_threshold),
        ("qualification", t.qualification_threshold),
    ):
        p = th.effective_percent
        if not (0.0 < p <= 100.0):
            raise InvariantViolation(
                f"{substance_type}@{daily_dose_g}g {name} effective_percent={p} not in (0,100]"
            )
    if t.qualification_threshold.effective_percent < t.reporting_threshold.effective_percent - _EPS:
        raise InvariantViolation(
            f"{substance_type}@{daily_dose_g}g qualification < reporting "
            f"({t.qualification_threshold.effective_percent} < "
            f"{t.reporting_threshold.effective_percent})"
        )


def assert_q3d_permitted_inverse_monotonic_in_dose(
    element: str, route: str, lo_dose: float, hi_dose: float
) -> None:
    """Q3D permitted concentration (ppm) is non-increasing as dose increases (PDE/dose)."""

    if lo_dose >= hi_dose:
        return
    lo = calculate_concentration_limit(element, route, lo_dose)
    hi = calculate_concentration_limit(element, route, hi_dose)
    if lo.permitted_concentration_ppm is None or hi.permitted_concentration_ppm is None:
        return
    if hi.permitted_concentration_ppm > lo.permitted_concentration_ppm + _EPS:
        raise InvariantViolation(
            f"Q3D {element}/{route}: permitted({hi_dose})={hi.permitted_concentration_ppm} > "
            f"permitted({lo_dose})={lo.permitted_concentration_ppm} (not inverse-monotonic)"
        )


def assert_q3d_class_valid(element: str, route: str) -> None:
    """A Q3D element's class is always one of the four guideline classes."""

    pde = get_element_pde(element, route)
    if pde.element_class not in _Q3D_CLASSES:
        raise InvariantViolation(
            f"Q3D {element}: class {pde.element_class!r} not in {sorted(_Q3D_CLASSES)}"
        )


def assert_m7_class_valid(smiles: str) -> None:
    """An ICH M7 class is always an integer in [1, 5]."""

    cls = classify_m7(smiles).m7_class
    if cls not in {1, 2, 3, 4, 5}:
        raise InvariantViolation(f"M7 {smiles}: class {cls!r} not in 1..5")


def assert_cpca_category_valid(smiles: str) -> None:
    """A CPCA potency category is always an integer in [1, 5]."""

    cat = classify_cpca(smiles).category
    if cat not in {1, 2, 3, 4, 5}:
        raise InvariantViolation(f"CPCA {smiles}: category {cat!r} not in 1..5")


def assert_cpca_cumulative_strict_rule(smiles: str, measured_ng_per_day: float) -> None:
    """The FDA Rev-2 cumulative-risk verdict uses the strict rule: passes iff total ratio < 1.0."""

    result = calculate_cumulative_risk([(smiles, measured_ng_per_day)], authority="FDA")
    if result.passes != (result.total_risk_ratio < 1.0):
        raise InvariantViolation(
            f"CPCA cumulative {smiles}@{measured_ng_per_day}: passes={result.passes} but "
            f"ratio={result.total_risk_ratio} (rule is strict < 1.0)"
        )


# --------------------------------------------------------------------------- #
# Deterministic grid runner (reproducible evidence for the CSV package)
# --------------------------------------------------------------------------- #
def run_property_invariants() -> list[InvariantResult]:
    """Run every invariant over a fixed deterministic grid; returns a result per invariant."""

    doses = (0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
    measured = (5.0, 26.5, 100.0, 1500.0)

    grids: list[tuple[str, object, list[tuple]]] = [
        (
            "q3ab_thresholds_well_formed",
            assert_q3ab_thresholds_well_formed,
            [(d, s) for d in doses for s in ("drug_substance", "drug_product")],
        ),
        (
            "q3d_permitted_inverse_monotonic_in_dose",
            assert_q3d_permitted_inverse_monotonic_in_dose,
            [(e, "oral", lo, hi) for e in _Q3D_ELEMENTS for lo, hi in ((0.5, 1.0), (1.0, 2.0))],
        ),
        ("q3d_class_valid", assert_q3d_class_valid, [(e, "oral") for e in _Q3D_ELEMENTS]),
        ("m7_class_valid", assert_m7_class_valid, [(s,) for s in _VALID_SMILES]),
        ("cpca_category_valid", assert_cpca_category_valid, [(s,) for s in _VALID_SMILES[:4]]),
        (
            "cpca_cumulative_strict_rule",
            assert_cpca_cumulative_strict_rule,
            [(s, m) for s in _VALID_SMILES[:4] for m in measured],
        ),
    ]

    results: list[InvariantResult] = []
    for name, fn, cases in grids:
        failures: list[str] = []
        for case in cases:
            try:
                fn(*case)
            except InvariantViolation as exc:
                failures.append(str(exc))
        results.append(
            InvariantResult(
                name=name, cases=len(cases), passed=not failures, failures=tuple(failures)
            )
        )
    return results
