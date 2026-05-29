"""Phase 40 — HONEST corpus gate for the opt-in Haasnoot-de Leeuw-Altona (HLA)
generalized Karplus refinement (``karplus_method='haasnoot_altona'``).

This is the deliberately candid companion to the Phase 39 generic-Karplus
accuracy gate (``test_phase39_karplus_validation.py``).  It drives the SAME
8-molecule literature vicinal-3J corpus through the method-aware harness under
*both* relations and locks in the measured truth:

    The Haasnoot-Altona relation is *per-conformer* more literature-faithful
    (it recovers the locked trans-decalin diaxial **above** the generic
    three-term ~10.26 Hz ceiling, toward the literature ~11 Hz), but under the
    existing **unweighted ETKDG conformer averaging** its wider dynamic range
    (0 -> ~14.7 Hz vs the generic 1.4 -> 10.26 Hz) AMPLIFIES averaging
    artefacts: mobile/averaged systems over-predict and the clean
    locked-vs-mobile discrimination COLLAPSES.

So HLA ships as a real, correct, tested capability (see
``test_phase40_haasnoot_altona.py`` for the equation-level proofs) AND a
credibility-building negative result that motivates Boltzmann-weighted
conformer populations (the Phase 41 work).  Generic stays the default and the
Phase 39 gate stays byte-identical.

Measured baseline (RDKit ETKDGv3 + MMFF, fixed seed, 12 conformers):

    metric                          generic        HLA
    within_tol_rate                    1.00       0.75
    mean_abs_error_hz                  0.44       1.19
    max_abs_error_hz                   1.41       2.37  (cyclohexane over-predicts)
    mean_locked_predicted_max_hz       9.50       9.64
    min_locked_predicted_max_hz        8.49       7.94  (beta-D-galactose)
    mean_mobile_predicted_max_hz       6.90       8.56
    max_mobile_predicted_max_hz        7.14       9.17  (cyclohexane)
    locked_vs_mobile_separation_hz    +1.35      -1.23
    clean_locked_vs_mobile_separation  True      False

    per-molecule max vicinal J (generic -> HLA):
        trans_decalin           10.05 -> 11.64  (+1.59  WIN: above 10.26 ceiling)
        beta_d_glucopyranose     9.59 ->  8.99  (-0.60)
        myo_inositol             9.85 ->  9.97  (+0.12)
        beta_d_galactopyranose   8.49 ->  7.94  (-0.55  sugar blind spot UNfixed)
        cyclohexane              7.14 ->  9.17  (+2.03  mobile balloons)
        cis_decalin              6.83 ->  8.15  (+1.32)
        n_butane                 7.12 ->  8.95  (+1.83)
        ethanol                  6.50 ->  7.97  (+1.47)

Floors/ceilings sit comfortably clear of the measured values so harmless
cross-version RDKit numerical wiggle doesn't break the gate, but a real
behaviour change (e.g. someone "fixes" HLA by clamping its range, or wires in
Boltzmann weighting — which is exactly the Phase 41 change that SHOULD update
this gate) breaks it loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmrcheck.jcoupling_prediction import (
    KARPLUS_CATEGORY_GENERIC,
    KARPLUS_CATEGORY_HAASNOOT_ALTONA,
    KARPLUS_METHOD_GENERIC,
    KARPLUS_METHOD_HAASNOOT_ALTONA,
)
from nmrcheck.karplus_validation import run_all

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def generic_report() -> dict:
    return run_all(_FIXTURES_ROOT, method=KARPLUS_METHOD_GENERIC)


@pytest.fixture(scope="module")
def hla_report() -> dict:
    return run_all(_FIXTURES_ROOT, method=KARPLUS_METHOD_HAASNOOT_ALTONA)


def _by_id(report: dict) -> dict[str, dict]:
    return {row["fixture_id"]: row for row in report["rows"]}


# --------------------------------------------------------------------------- #
# The WIN: per-conformer fidelity above the generic three-term ceiling.
# --------------------------------------------------------------------------- #
def test_hla_recovers_trans_decalin_diaxial_above_generic_ceiling(
    generic_report: dict, hla_report: dict
) -> None:
    """trans-decalin: HLA recovers the locked diaxial ABOVE the generic ceiling.

    The generic three-term relation caps near 10.26 Hz at 180 deg, so it
    under-recovers the covalently-locked trans-decalin diaxial (lit ~11 Hz).
    HLA's electronegativity/orientation terms widen the range and recover it.
    This is the genuine per-conformer capability HLA adds.
    """

    gen = _by_id(generic_report)["trans_decalin"]
    hla = _by_id(hla_report)["trans_decalin"]
    assert gen["row_status"] == "ok" and hla["row_status"] == "ok"

    gen_j = gen["predicted_max_vicinal_j_hz"]
    hla_j = hla["predicted_max_vicinal_j_hz"]

    # Generic sits at/under its ~10.26 Hz three-term ceiling (measured 10.05).
    assert gen_j <= 10.5, f"generic trans-decalin {gen_j} unexpectedly high"
    # HLA recovers a clearly larger diaxial, toward literature ~11 (measured 11.64).
    assert hla_j >= 10.8, (
        f"HLA trans-decalin {hla_j} did not clear the generic ceiling toward "
        f"literature ~11 Hz"
    )
    assert (hla_j - gen_j) >= 0.8, (
        f"HLA-vs-generic trans-decalin gain {(hla_j - gen_j):.2f} Hz collapsed "
        f"(measured +1.59)"
    )


def test_hla_keeps_locked_mean_high(hla_report: dict) -> None:
    """HLA does not destroy the locked anchors on average (mean stays ~>=9 Hz)."""

    mean_locked = hla_report["summary"]["mean_locked_predicted_max_hz"]
    assert mean_locked is not None and mean_locked >= 9.0, (
        f"HLA mean locked predicted max {mean_locked} Hz fell below 9.0 "
        f"(measured 9.64)"
    )


# --------------------------------------------------------------------------- #
# The HONEST negative: averaged discrimination collapses under HLA.
# --------------------------------------------------------------------------- #
def test_generic_clean_separates_but_hla_does_not(
    generic_report: dict, hla_report: dict
) -> None:
    """Headline honesty: generic clean-separates locked>mobile, HLA does NOT.

    Under unweighted ETKDG averaging, HLA's wider dynamic range amplifies the
    mobile-conformer contributions, so the clean locked-vs-mobile separation
    that the generic relation enjoys is LOST.  This is the result that
    motivates Boltzmann-weighted conformer populations (Phase 41).
    """

    gs = generic_report["summary"]
    hs = hla_report["summary"]

    # Generic: every locked system > every mobile system (the Phase 39 claim).
    assert gs["clean_locked_vs_mobile_separation"] is True
    assert gs["locked_vs_mobile_separation_hz"] is not None
    assert gs["locked_vs_mobile_separation_hz"] > 0  # measured +1.35

    # HLA: the separation collapses (and in fact inverts).
    assert hs["clean_locked_vs_mobile_separation"] is False, (
        "HLA unexpectedly preserved clean locked-vs-mobile separation — the "
        "Phase 41 Boltzmann-weighting motivation no longer holds; revisit this "
        "gate and the white-paper claim."
    )
    sep = hs["locked_vs_mobile_separation_hz"]
    assert sep is not None and sep < 0.0, (
        f"HLA locked-vs-mobile separation {sep} Hz should be negative "
        f"(measured -1.23)"
    )
    # Concretely: the smallest locked coupling sinks BELOW the largest mobile one.
    assert hs["min_locked_predicted_max_hz"] < hs["max_mobile_predicted_max_hz"]


def test_hla_overpredicts_mobile_systems(
    generic_report: dict, hla_report: dict
) -> None:
    """Mobile/averaged systems balloon under HLA (the source of the collapse)."""

    gs = generic_report["summary"]
    hs = hla_report["summary"]

    # A mobile system now over-predicts well above the ~7 Hz averaged regime
    # (measured max_mobile 9.17 = cyclohexane).
    assert hs["max_mobile_predicted_max_hz"] >= 8.0, (
        f"HLA max mobile {hs['max_mobile_predicted_max_hz']} Hz did not balloon "
        f"as measured (9.17)"
    )
    # The mobile MEAN rises markedly versus generic (measured 6.90 -> 8.56).
    assert hs["mean_mobile_predicted_max_hz"] >= 7.8
    assert (
        hs["mean_mobile_predicted_max_hz"] - gs["mean_mobile_predicted_max_hz"]
    ) >= 1.0, "HLA did not raise the mobile mean versus generic as measured"


def test_hla_amplifies_mobile_more_than_locked(
    generic_report: dict, hla_report: dict
) -> None:
    """The averaging-amplification fingerprint: mobile rises, locked barely moves.

    generic->HLA mean shift: locked +0.14 Hz, mobile +1.66 Hz.  The mechanism
    is that HLA's wider per-conformer range inflates the freely-rotating
    rotamer averages far more than the conformationally-pinned locked ones.
    """

    gs = generic_report["summary"]
    hs = hla_report["summary"]
    locked_rise = (
        hs["mean_locked_predicted_max_hz"] - gs["mean_locked_predicted_max_hz"]
    )
    mobile_rise = (
        hs["mean_mobile_predicted_max_hz"] - gs["mean_mobile_predicted_max_hz"]
    )
    assert (mobile_rise - locked_rise) >= 1.0, (
        f"Expected HLA to raise the mobile mean far more than the locked mean "
        f"(measured mobile +1.66 vs locked +0.14); got mobile {mobile_rise:+.2f} "
        f"locked {locked_rise:+.2f}"
    )


def test_hla_does_not_fix_galactose_sugar_blind_spot(
    generic_report: dict, hla_report: dict
) -> None:
    """The original Phase 40 premise, honestly negated.

    beta-D-galactose was the generic-Karplus worst case (predicted 8.49 vs
    literature ~9.9).  The hope was that HLA's electronegativity correction
    would raise it toward 9.9.  Under unweighted averaging it does the
    OPPOSITE (8.49 -> 7.94): the sugar blind spot is not a Karplus-form
    problem, it is a conformer-population-weighting problem -> Phase 41.
    """

    gen = _by_id(generic_report)["beta_d_galactopyranose"]
    hla = _by_id(hla_report)["beta_d_galactopyranose"]
    assert gen["row_status"] == "ok" and hla["row_status"] == "ok"

    expected = gen["expected_max_vicinal_j_hz"]  # ~9.90 literature
    gen_j = gen["predicted_max_vicinal_j_hz"]
    hla_j = hla["predicted_max_vicinal_j_hz"]

    # HLA does NOT lift galactose toward literature; it stays well below.
    assert hla_j < 8.5, (
        f"HLA galactose {hla_j} unexpectedly climbed (measured 7.94); if a "
        f"conformer-weighting change fixed this, update the Phase 41 narrative"
    )
    assert (expected - hla_j) >= 1.0, (
        f"HLA galactose {hla_j} is within 1 Hz of literature {expected}; the "
        f"sugar blind spot appears fixed — revisit the honest claim"
    )
    # And it is not an improvement over generic on this entry.
    assert hla_j <= gen_j + 0.05, (
        f"HLA galactose {hla_j} improved on generic {gen_j} — unexpected"
    )


def test_hla_within_tol_rate_drops_below_generic(
    generic_report: dict, hla_report: dict
) -> None:
    """Aggregate accuracy is WORSE under HLA on this averaged corpus."""

    gs = generic_report["summary"]
    hs = hla_report["summary"]

    assert gs["within_tol_rate"] == 1.0  # Phase 39 baseline
    assert hs["within_tol_rate"] is not None
    assert hs["within_tol_rate"] < gs["within_tol_rate"], (
        "HLA within-tol rate did not drop below generic — the honest negative "
        "result no longer holds"
    )
    assert hs["within_tol_rate"] <= 0.875, (
        f"HLA within-tol rate {hs['within_tol_rate']} unexpectedly high "
        f"(measured 0.75)"
    )
    # Mean absolute error rises too (measured 0.44 -> 1.19).
    assert hs["mean_abs_error_hz"] > gs["mean_abs_error_hz"]


# --------------------------------------------------------------------------- #
# Plumbing: method tagging + determinism.
# --------------------------------------------------------------------------- #
def test_reports_are_method_tagged(
    generic_report: dict, hla_report: dict
) -> None:
    """Each report records its method + the provenance category it graded."""

    gs = generic_report["summary"]
    hs = hla_report["summary"]
    assert gs["method"] == KARPLUS_METHOD_GENERIC
    assert gs["category"] == KARPLUS_CATEGORY_GENERIC
    assert hs["method"] == KARPLUS_METHOD_HAASNOOT_ALTONA
    assert hs["category"] == KARPLUS_CATEGORY_HAASNOOT_ALTONA

    # Rows carry the method too (CSV/JSON transparency).
    assert all(r["method"] == KARPLUS_METHOD_GENERIC for r in generic_report["rows"])
    assert all(
        r["method"] == KARPLUS_METHOD_HAASNOOT_ALTONA for r in hla_report["rows"]
    )


def test_hla_harness_is_deterministic() -> None:
    """Fixed seed => byte-identical HLA predicted maxima across repeated runs."""

    first = {
        r["fixture_id"]: r["predicted_max_vicinal_j_hz"]
        for r in run_all(_FIXTURES_ROOT, method=KARPLUS_METHOD_HAASNOOT_ALTONA)["rows"]
    }
    second = {
        r["fixture_id"]: r["predicted_max_vicinal_j_hz"]
        for r in run_all(_FIXTURES_ROOT, method=KARPLUS_METHOD_HAASNOOT_ALTONA)["rows"]
    }
    assert first == second, f"HLA harness non-deterministic: {first} != {second}"
