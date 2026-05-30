"""Phase 42 — scaled (n=18) corpus gate: the Boltzmann win holds, and sharpens.

Phase 41 proved on 8 molecules that Boltzmann conformer-population weighting
recovers the locked sugar diaxials and restores clean locked-vs-mobile
discrimination.  Phase 42 expands the literature corpus to **18 molecules**
(a separate ``karplus_jcoupling_corpus_v2.json`` — the Phase 39/40/41 gates keep
loading the byte-identical v1 bundle) and asks whether the win holds at scale.
It does, and the larger, harder corpus makes the case *sharper*: grading the
full {generic, haasnoot_altona} × {uniform, boltzmann} grid,

    method/weighting    within_tol  MAE    separation  clean
    generic/uniform        0.94     0.80     -0.64      False
    generic/boltzmann      1.00     0.57     +1.84      True
    haasnoot/uniform       0.83     1.15     -2.10      False
    haasnoot/boltzmann     0.78     1.29     -0.07      False

The headline this gate protects: **at n=18, generic/boltzmann is the ONLY one
of the four combinations that cleanly separates the locked diaxials from the
mobile systems** — and it does so with the best accuracy (within-tol 1.00, MAE
0.57 Hz).  Unweighted averaging now *fails* (several locked sugars, e.g.
β-D-quinovose, wash out to ~6.5 Hz — mobile-like — under the plain mean), and
the HLA relation loses even with Boltzmann weighting because its
electronegativity terms inflate the mobile couplings.  So the expanded corpus
is direct, measured evidence that **generic + Boltzmann** is the combination
worth standardising on (the prerequisite for any future default change).

The v2 corpus deliberately scopes 'mobile' to ring-flipping / pseudorotating
rings and SHORT freely-rotating chains: long n-alkanes (n-pentane, n-hexane)
are excluded with documented rationale because vacuum MMFF over-stabilises
their extended all-anti backbone, inflating the Boltzmann-weighted coupling by
a force-field/solvation limitation rather than a real locked geometry.
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
_V2_BUNDLE = "karplus_jcoupling_corpus_v2.json"

_NEW_LOCKED_SUGARS = [
    "methyl_beta_d_glucopyranoside",
    "methyl_beta_d_galactopyranoside",
    "beta_d_quinovose",
    "beta_d_mannopyranose",
    "beta_d_xylopyranose",
]


def _report(method: str, weighting: str) -> dict:
    return run_all(
        _FIXTURES_ROOT, method=method, weighting=weighting, bundle_filename=_V2_BUNDLE
    )


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


def test_v2_corpus_shape(gen_boltzmann: dict) -> None:
    """18 molecules, 9 locked / 9 mobile, all run cleanly."""

    s = gen_boltzmann["summary"]
    assert s["fixture_count"] == 18
    assert s["ok_count"] == 18, [
        (r["fixture_id"], r["error"])
        for r in gen_boltzmann["rows"]
        if r["row_status"] == "error"
    ]
    assert s["locked_count"] == 9
    assert s["mobile_count"] == 9


def test_generic_boltzmann_is_uniquely_clean_at_scale(
    gen_uniform: dict, gen_boltzmann: dict, hla_uniform: dict, hla_boltzmann: dict
) -> None:
    """Of the four combos, ONLY generic/boltzmann cleanly separates at n=18."""

    gb = gen_boltzmann["summary"]
    assert gb["clean_locked_vs_mobile_separation"] is True
    assert gb["locked_vs_mobile_separation_hz"] >= 1.0, (
        f"generic/boltzmann separation {gb['locked_vs_mobile_separation_hz']} "
        f"collapsed at scale (measured +1.84)"
    )

    # The other three are all well short of a clean +1 Hz separation (all measured
    # negative: -0.64, -2.10, -0.07).
    for other in (gen_uniform, hla_uniform, hla_boltzmann):
        sep = other["summary"]["locked_vs_mobile_separation_hz"]
        assert sep is not None and sep < 1.0
        assert sep < gb["locked_vs_mobile_separation_hz"]


def test_unweighted_averaging_fails_at_scale(
    gen_uniform: dict, gen_boltzmann: dict
) -> None:
    """The plain ensemble mean can no longer separate the harder corpus;
    Boltzmann weighting restores it by a wide margin."""

    gu = gen_uniform["summary"]
    gb = gen_boltzmann["summary"]

    # Unweighted loses molecules out of tolerance (locked sugars wash out).
    assert gu["within_tol_rate"] < 1.0  # measured 0.94
    # Boltzmann improves the separation by a wide, robust margin (measured +2.48).
    assert (
        gb["locked_vs_mobile_separation_hz"] - gu["locked_vs_mobile_separation_hz"]
    ) >= 1.5


def test_generic_boltzmann_is_the_most_accurate_at_scale(
    gen_uniform: dict, gen_boltzmann: dict, hla_uniform: dict, hla_boltzmann: dict
) -> None:
    gb = gen_boltzmann["summary"]
    assert gb["within_tol_rate"] >= 0.88          # measured 1.00
    assert gb["mean_abs_error_hz"] <= 0.9         # measured 0.57
    assert gb["min_locked_predicted_max_hz"] >= 9.0   # measured 9.92
    assert gb["max_mobile_predicted_max_hz"] <= 8.8   # measured 8.08
    # Best MAE of the four combinations.
    for other in (gen_uniform, hla_uniform, hla_boltzmann):
        assert gb["mean_abs_error_hz"] < other["summary"]["mean_abs_error_hz"]


def test_quinovose_shows_the_population_weighting_mechanism(
    gen_uniform: dict, gen_boltzmann: dict
) -> None:
    """β-D-quinovose is the corpus's cleanest single-molecule demonstration:
    a genuinely locked sugar whose diaxial WASHES OUT to a mobile-like ~6.5 Hz
    under the unweighted mean and is RESTORED to ~10 Hz by Boltzmann weighting."""

    uni = _by_id(gen_uniform)["beta_d_quinovose"]["predicted_max_vicinal_j_hz"]
    boltz = _by_id(gen_boltzmann)["beta_d_quinovose"]["predicted_max_vicinal_j_hz"]
    assert uni < 7.5, f"quinovose uniform {uni} unexpectedly high (measured 6.50)"
    assert boltz >= 9.0, f"quinovose boltzmann {boltz} did not recover (measured 10.25)"
    assert (boltz - uni) >= 2.0, f"quinovose recovery {(boltz - uni):.2f} Hz too small"


def test_new_locked_sugars_recover_under_boltzmann(gen_boltzmann: dict) -> None:
    """Every newly-added locked pyranose recovers a large diaxial (>= 9 Hz)."""

    rows = _by_id(gen_boltzmann)
    for fid in _NEW_LOCKED_SUGARS:
        j = rows[fid]["predicted_max_vicinal_j_hz"]
        assert j is not None and j >= 9.0, f"{fid} only recovered {j} Hz under Boltzmann"


def test_hla_still_loses_at_scale(
    gen_boltzmann: dict, hla_boltzmann: dict
) -> None:
    """Even Boltzmann-weighted, HLA does not separate at scale: its
    electronegativity terms inflate the mobile couplings, so generic wins."""

    gb = gen_boltzmann["summary"]
    hb = hla_boltzmann["summary"]
    assert gb["locked_vs_mobile_separation_hz"] > hb["locked_vs_mobile_separation_hz"]
    assert hb["max_mobile_predicted_max_hz"] > gb["max_mobile_predicted_max_hz"]


def test_v2_reports_weighting_tagged_and_deterministic(gen_boltzmann: dict) -> None:
    assert gen_boltzmann["summary"]["weighting"] == CONFORMER_WEIGHTING_BOLTZMANN
    assert gen_boltzmann["summary"]["method"] == KARPLUS_METHOD_GENERIC
    first = {r["fixture_id"]: r["predicted_max_vicinal_j_hz"] for r in gen_boltzmann["rows"]}
    second = {
        r["fixture_id"]: r["predicted_max_vicinal_j_hz"]
        for r in _report(KARPLUS_METHOD_GENERIC, CONFORMER_WEIGHTING_BOLTZMANN)["rows"]
    }
    assert first == second
