"""Phase 41 — measured corpus gate for Boltzmann conformer-population weighting.

The candid companion to the Phase 40 corpus gate
(``test_phase40_haasnoot_altona_corpus.py``), which locked the *negative*
result: under unweighted averaging neither the generic nor the HLA relation
recovered the locked-vs-mobile discrimination, and β-D-galactose stayed stuck
at ~8 Hz instead of its ~9.9 Hz literature value.  Phase 41 supplies the fix —
``karplus_conformer_weighting='boltzmann'`` — and this gate locks the measured
recovery, grading the SAME 8-molecule corpus across the full
{generic, haasnoot_altona} × {uniform, boltzmann} grid via the method/weighting-
aware harness.

Measured (RDKit ETKDGv3 + MMFF, fixed seed, 12 conformers):

    method/weighting    within_tol  separation  min_locked  max_mobile  clean
    generic/uniform        1.00       +1.35        8.49        7.14      True
    generic/boltzmann      1.00       +2.28        9.98        7.70      True
    haasnoot/uniform       0.75       -1.23        7.94        9.17      False
    haasnoot/boltzmann     0.75       +0.36       10.08        9.72      True

Headline results this gate protects:

1. **Boltzmann weighting fixes the sugar blind spot.**  β-D-galactose's
   diagnostic diaxial moves from 8.49 Hz (generic/uniform — the Phase 40 worst
   case) to ~10.1 Hz, on its ~9.9 Hz literature value, because the ground-state
   ⁴C₁ chair stops being diluted by high-energy ring-flipped conformers.

2. **Boltzmann weighting widens, not just preserves, the discrimination.**  The
   clean locked-vs-mobile separation grows from +1.35 Hz (generic/uniform) to
   +2.28 Hz (generic/boltzmann): locked systems tighten toward ~10 Hz while
   mobile systems stay in the ~7 Hz averaged regime.

3. **It also rescues the HLA collapse.**  The Phase 40 −1.23 Hz collapse under
   haasnoot/uniform becomes a clean +0.36 Hz separation under
   haasnoot/boltzmann.

4. **The simple relation + proper weighting wins.**  generic/boltzmann
   discriminates *better* than haasnoot/boltzmann (separation +2.28 vs +0.36;
   HLA inflates mobile couplings), so the electronegativity correction is not
   what the sugars needed — conformer-population weighting is.

The default weighting stays ``'uniform'``, so the Phase 39 and Phase 40 gates
remain byte-identical; this gate exercises the opt-in ``'boltzmann'`` path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmrcheck.jcoupling_prediction import (
    CONFORMER_WEIGHTING_BOLTZMANN,
    CONFORMER_WEIGHTING_UNIFORM,
    KARPLUS_METHOD_GENERIC,
    KARPLUS_METHOD_HAASNOOT_ALTONA,
)
from nmrcheck.karplus_validation import run_all

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def _report(method: str, weighting: str) -> dict:
    return run_all(_FIXTURES_ROOT, method=method, weighting=weighting)


@pytest.fixture(scope="module")
def gen_uniform() -> dict:
    return _report(KARPLUS_METHOD_GENERIC, CONFORMER_WEIGHTING_UNIFORM)


@pytest.fixture(scope="module")
def gen_boltzmann() -> dict:
    return _report(KARPLUS_METHOD_GENERIC, CONFORMER_WEIGHTING_BOLTZMANN)


@pytest.fixture(scope="module")
def hla_uniform() -> dict:
    return _report(KARPLUS_METHOD_HAASNOOT_ALTONA, CONFORMER_WEIGHTING_UNIFORM)


@pytest.fixture(scope="module")
def hla_boltzmann() -> dict:
    return _report(KARPLUS_METHOD_HAASNOOT_ALTONA, CONFORMER_WEIGHTING_BOLTZMANN)


def _by_id(report: dict) -> dict[str, dict]:
    return {row["fixture_id"]: row for row in report["rows"]}


# --------------------------------------------------------------------------- #
# 1. The sugar blind spot is fixed.
# --------------------------------------------------------------------------- #
def test_boltzmann_fixes_galactose_sugar_blind_spot(
    gen_uniform: dict, gen_boltzmann: dict
) -> None:
    """β-D-galactose: 8.49 Hz (uniform) -> ~10.1 Hz (boltzmann), onto lit ~9.9."""

    uni = _by_id(gen_uniform)["beta_d_galactopyranose"]
    boltz = _by_id(gen_boltzmann)["beta_d_galactopyranose"]
    assert uni["row_status"] == "ok" and boltz["row_status"] == "ok"

    uni_j = uni["predicted_max_vicinal_j_hz"]
    boltz_j = boltz["predicted_max_vicinal_j_hz"]
    expected = uni["expected_max_vicinal_j_hz"]  # ~9.90 literature

    assert uni_j < 9.0, f"uniform galactose {uni_j} not the Phase 40 blind spot (8.49)"
    assert boltz_j >= 9.5, f"Boltzmann galactose {boltz_j} did not reach the lit window"
    assert (boltz_j - uni_j) >= 1.0, f"Boltzmann gain {(boltz_j - uni_j):.2f} Hz too small"
    # And it now lands within ~1 Hz of the literature value it used to miss by 1.4.
    assert abs(boltz_j - expected) <= 1.0, (
        f"Boltzmann galactose {boltz_j} still far from literature {expected}"
    )


# --------------------------------------------------------------------------- #
# 2. Boltzmann widens the generic discrimination.
# --------------------------------------------------------------------------- #
def test_boltzmann_widens_generic_discrimination(
    gen_uniform: dict, gen_boltzmann: dict
) -> None:
    """generic/boltzmann clean-separates with a WIDER margin than generic/uniform."""

    us = gen_uniform["summary"]
    bs = gen_boltzmann["summary"]

    # Both clean; uniform is the byte-identical Phase 39 baseline (+1.35 Hz).
    assert us["clean_locked_vs_mobile_separation"] is True
    assert us["locked_vs_mobile_separation_hz"] == pytest.approx(1.35, abs=0.25)

    # Boltzmann keeps it clean and WIDENS the separation (measured +2.28).
    assert bs["clean_locked_vs_mobile_separation"] is True
    assert bs["locked_vs_mobile_separation_hz"] >= 1.6, (
        f"Boltzmann separation {bs['locked_vs_mobile_separation_hz']} did not exceed "
        f"the uniform baseline as measured (+2.28 vs +1.35)"
    )
    assert bs["locked_vs_mobile_separation_hz"] > us["locked_vs_mobile_separation_hz"]

    # Locked systems tighten toward ~10 Hz; mobile stays in the averaged regime.
    assert bs["min_locked_predicted_max_hz"] >= 9.0   # measured 9.98
    assert bs["max_mobile_predicted_max_hz"] <= 8.5   # measured 7.70
    # Accuracy does not regress (measured within-tol still 1.00, MAE still 0.44).
    assert bs["within_tol_rate"] >= 0.875
    assert bs["mean_abs_error_hz"] <= 1.0


# --------------------------------------------------------------------------- #
# 3. Boltzmann rescues the HLA collapse.
# --------------------------------------------------------------------------- #
def test_boltzmann_rescues_hla_collapse(
    hla_uniform: dict, hla_boltzmann: dict
) -> None:
    """haasnoot/uniform collapsed (-1.23); haasnoot/boltzmann recovers (+0.36)."""

    us = hla_uniform["summary"]
    bs = hla_boltzmann["summary"]

    # Phase 40 byte-identical collapse under uniform.
    assert us["clean_locked_vs_mobile_separation"] is False
    assert us["locked_vs_mobile_separation_hz"] < 0.0

    # Boltzmann recovers a clean separation.
    assert bs["clean_locked_vs_mobile_separation"] is True, (
        "Boltzmann weighting failed to rescue the HLA locked-vs-mobile collapse"
    )
    assert bs["locked_vs_mobile_separation_hz"] > us["locked_vs_mobile_separation_hz"]
    assert bs["min_locked_predicted_max_hz"] > bs["max_mobile_predicted_max_hz"]
    # The HLA sugar also recovers (measured 7.94 -> 10.08).
    gal = _by_id(hla_boltzmann)["beta_d_galactopyranose"]["predicted_max_vicinal_j_hz"]
    assert gal >= 9.5


# --------------------------------------------------------------------------- #
# 4. The simple relation + proper weighting wins.
# --------------------------------------------------------------------------- #
def test_generic_boltzmann_beats_hla_boltzmann(
    gen_boltzmann: dict, hla_boltzmann: dict
) -> None:
    """Once conformers are Boltzmann-weighted, the GENERIC relation discriminates
    better than the electronegativity-corrected HLA one — the sugar fix came
    from population weighting, not from a more elaborate Karplus form."""

    gs = gen_boltzmann["summary"]
    hs = hla_boltzmann["summary"]
    assert gs["locked_vs_mobile_separation_hz"] > hs["locked_vs_mobile_separation_hz"]
    # HLA still over-predicts mobile systems even when Boltzmann-weighted.
    assert hs["max_mobile_predicted_max_hz"] > gs["max_mobile_predicted_max_hz"]


# --------------------------------------------------------------------------- #
# Plumbing: reports are weighting-tagged + deterministic.
# --------------------------------------------------------------------------- #
def test_reports_are_weighting_tagged(
    gen_uniform: dict, gen_boltzmann: dict
) -> None:
    assert gen_uniform["summary"]["weighting"] == CONFORMER_WEIGHTING_UNIFORM
    assert gen_boltzmann["summary"]["weighting"] == CONFORMER_WEIGHTING_BOLTZMANN
    assert all(r["weighting"] == CONFORMER_WEIGHTING_UNIFORM for r in gen_uniform["rows"])
    assert all(
        r["weighting"] == CONFORMER_WEIGHTING_BOLTZMANN for r in gen_boltzmann["rows"]
    )


def test_boltzmann_corpus_is_deterministic() -> None:
    first = {
        r["fixture_id"]: r["predicted_max_vicinal_j_hz"]
        for r in _report(KARPLUS_METHOD_GENERIC, CONFORMER_WEIGHTING_BOLTZMANN)["rows"]
    }
    second = {
        r["fixture_id"]: r["predicted_max_vicinal_j_hz"]
        for r in _report(KARPLUS_METHOD_GENERIC, CONFORMER_WEIGHTING_BOLTZMANN)["rows"]
    }
    assert first == second
