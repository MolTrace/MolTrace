"""Phase 39 — accuracy gate for the opt-in Karplus vicinal-3J refinement.

Drives the Week-40 multiplet J-coupling predictor with ``use_karplus=True``
over a hand-curated literature corpus (``tests/fixtures/
karplus_jcoupling_corpus/karplus_jcoupling_corpus_v1.json``) and locks in the
measured semi-quantitative accuracy so a future detector / conformer-pipeline
regression breaks loudly.  See ``src/nmrcheck/karplus_validation.py`` for the
harness.

The corpus is 8 molecules split into two scientific buckets:

* ``locked_diaxial`` — covalently/rigidly locked rings (trans-decalin, the
  beta-D-pyranoses, myo-inositol) where a diaxial coupling SHOULD be
  recovered (~9-11 Hz).
* ``mobile_averaged`` / ``acyclic_averaged`` — freely flipping rings and
  acyclic chains (cyclohexane, cis-decalin, n-butane, ethanol) where the
  coupling SHOULD collapse to the rotamer/ring-flip average (~6.5-7.5 Hz).

The headline claim the gate protects is the **discrimination**: every locked
system produces a larger maximum vicinal coupling than every mobile system.

Measured baseline (RDKit ETKDGv3 + MMFF, fixed seed 0xC0FFEE, 12 conformers):
    within_tol_rate          : 1.00  (8/8)
    mean_abs_error_hz        : 0.44
    median_abs_error_hz      : 0.26
    max_abs_error_hz         : 1.41  (beta-D-galactose — generic-Karplus
                                      electronegativity blind spot)
    mean_locked_predicted    : 9.50 Hz   (min 8.49)
    mean_mobile_predicted    : 6.90 Hz   (max 7.14)
    locked-vs-mobile sep     : 1.35 Hz   (clean separation)

Floors sit comfortably below the measured values so harmless cross-version
RDKit numerical wiggle doesn't break the gate, but a real degradation
(e.g. losing the conformer ensemble, or a Karplus-constant regression) does.
This is a semi-quantitative discrimination gate, NOT a sub-Hz prediction
claim — the per-entry tolerances (1.5-2.5 Hz) already encode that the generic
three-term Karplus relation caps near 10.26 Hz and omits Haasnoot-Altona
electronegativity corrections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmrcheck.karplus_validation import (
    DEFAULT_BUNDLE_FILENAME,
    LOCKED_KIND,
    run_all,
)

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

# --- regression floors (well below the measured baseline above) ---
_MIN_FIXTURE_COUNT = 8
_MIN_WITHIN_TOL_RATE = 0.75          # measured 1.00
_MAX_MEAN_ABS_ERROR_HZ = 1.5         # measured 0.44
_MAX_MEDIAN_ABS_ERROR_HZ = 1.0       # measured 0.26
_MAX_MAX_ABS_ERROR_HZ = 2.5          # measured 1.41
_MIN_MEAN_LOCKED_PREDICTED_HZ = 8.5  # measured 9.50
_MAX_MEAN_MOBILE_PREDICTED_HZ = 7.8  # measured 6.90
_MIN_LOCKED_MINUS_MOBILE_MEAN_HZ = 1.5  # measured 2.60


@pytest.mark.current_state
def test_karplus_corpus_smoke_and_accuracy_floor() -> None:
    """Every fixture runs cleanly + the measured accuracy baseline holds."""

    report = run_all(_FIXTURES_ROOT)
    summary = report["summary"]

    assert summary["fixture_count"] >= _MIN_FIXTURE_COUNT, (
        f"Karplus corpus shrunk to {summary['fixture_count']} fixtures "
        f"(floor {_MIN_FIXTURE_COUNT})."
    )
    assert summary["ok_count"] == summary["fixture_count"], (
        "At least one fixture errored during harness execution: "
        f"{[(row['fixture_id'], row['error']) for row in report['rows'] if row['row_status'] == 'error']}"
    )

    within_rate = summary["within_tol_rate"]
    assert within_rate is not None and within_rate >= _MIN_WITHIN_TOL_RATE, (
        f"within-tol rate {within_rate:.2%} fell below floor "
        f"{_MIN_WITHIN_TOL_RATE:.0%}"
    )

    mae = summary["mean_abs_error_hz"]
    assert mae is not None and mae <= _MAX_MEAN_ABS_ERROR_HZ, (
        f"mean abs error {mae} Hz exceeded floor {_MAX_MEAN_ABS_ERROR_HZ} Hz"
    )

    median_ae = summary["median_abs_error_hz"]
    assert median_ae is not None and median_ae <= _MAX_MEDIAN_ABS_ERROR_HZ, (
        f"median abs error {median_ae} Hz exceeded floor "
        f"{_MAX_MEDIAN_ABS_ERROR_HZ} Hz"
    )

    max_ae = summary["max_abs_error_hz"]
    assert max_ae is not None and max_ae <= _MAX_MAX_ABS_ERROR_HZ, (
        f"max abs error {max_ae} Hz exceeded floor {_MAX_MAX_ABS_ERROR_HZ} Hz"
    )


@pytest.mark.current_state
def test_karplus_locked_vs_mobile_discrimination() -> None:
    """Locked diaxial systems recover a larger coupling than mobile ones."""

    report = run_all(_FIXTURES_ROOT)
    summary = report["summary"]

    assert summary["locked_count"] >= 3, "Need >=3 locked anchors for the claim."
    assert summary["mobile_count"] >= 3, "Need >=3 mobile controls for the claim."

    mean_locked = summary["mean_locked_predicted_max_hz"]
    mean_mobile = summary["mean_mobile_predicted_max_hz"]
    assert mean_locked is not None and mean_locked >= _MIN_MEAN_LOCKED_PREDICTED_HZ, (
        f"mean locked predicted max {mean_locked} Hz fell below floor "
        f"{_MIN_MEAN_LOCKED_PREDICTED_HZ} Hz"
    )
    assert mean_mobile is not None and mean_mobile <= _MAX_MEAN_MOBILE_PREDICTED_HZ, (
        f"mean mobile predicted max {mean_mobile} Hz exceeded floor "
        f"{_MAX_MEAN_MOBILE_PREDICTED_HZ} Hz"
    )
    assert (mean_locked - mean_mobile) >= _MIN_LOCKED_MINUS_MOBILE_MEAN_HZ, (
        f"locked-minus-mobile mean gap {(mean_locked - mean_mobile):.2f} Hz "
        f"fell below floor {_MIN_LOCKED_MINUS_MOBILE_MEAN_HZ} Hz"
    )

    # Headline: clean separation — every locked system > every mobile system.
    min_locked = summary["min_locked_predicted_max_hz"]
    max_mobile = summary["max_mobile_predicted_max_hz"]
    assert summary["clean_locked_vs_mobile_separation"] is True, (
        f"locked-vs-mobile separation collapsed: min(locked)={min_locked} "
        f"is not strictly above max(mobile)={max_mobile}"
    )
    assert min_locked is not None and max_mobile is not None and min_locked > max_mobile


def test_karplus_trans_vs_cis_decalin_diastereomer_split() -> None:
    """The rigid trans isomer recovers a diaxial the mobile cis one cannot."""

    report = run_all(_FIXTURES_ROOT)
    by_id = {row["fixture_id"]: row for row in report["rows"]}
    trans = by_id["trans_decalin"]
    cis = by_id["cis_decalin"]
    assert trans["row_status"] == "ok" and cis["row_status"] == "ok"
    assert trans["predicted_max_vicinal_j_hz"] is not None
    assert cis["predicted_max_vicinal_j_hz"] is not None
    # trans-decalin is covalently locked (no ring flip) -> large diaxial;
    # cis-decalin interconverts -> averaged. The gap should be substantial.
    assert (
        trans["predicted_max_vicinal_j_hz"] - cis["predicted_max_vicinal_j_hz"]
    ) >= 2.0, (
        "trans-/cis-decalin diaxial discrimination collapsed: "
        f"trans={trans['predicted_max_vicinal_j_hz']} "
        f"cis={cis['predicted_max_vicinal_j_hz']}"
    )


def test_karplus_harness_is_deterministic() -> None:
    """Fixed seed => byte-identical predicted maxima across repeated runs."""

    first = {r["fixture_id"]: r["predicted_max_vicinal_j_hz"] for r in run_all(_FIXTURES_ROOT)["rows"]}
    second = {r["fixture_id"]: r["predicted_max_vicinal_j_hz"] for r in run_all(_FIXTURES_ROOT)["rows"]}
    assert first == second, f"Karplus harness non-deterministic: {first} != {second}"


def test_karplus_row_shape_is_stable() -> None:
    """Structural smoke: each row carries the documented keys + types."""

    report = run_all(_FIXTURES_ROOT, bundle_filename=DEFAULT_BUNDLE_FILENAME)
    for row in report["rows"]:
        for key in (
            "fixture_id", "compound_name", "smiles", "kind", "row_status",
            "expected_max_vicinal_j_hz", "tolerance_hz",
            "predicted_max_vicinal_j_hz", "abs_error_hz", "within_tol",
            "karplus_coupling_count",
        ):
            assert key in row, f"Row missing {key!r}: {row.get('fixture_id')}"
        assert row["kind"] in {LOCKED_KIND, "mobile_averaged", "acyclic_averaged"}
        if row["row_status"] == "ok":
            assert isinstance(row["predicted_max_vicinal_j_hz"], float)
            assert isinstance(row["within_tol"], bool)
            assert row["karplus_coupling_count"] >= 1
