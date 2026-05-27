"""Fixture-validation gate for the Prompt 3 GSD sidecar.

Two tests share the same harness output:

* ``test_prompt3_gsd_harness_smoke_and_baseline_floor`` is a ``current_state``
  gate that always must pass.  It (a) proves the harness loads every curated
  fixture without raising, and (b) enforces a regression floor at the current
  observed metrics so any change that makes the sidecar materially worse than
  today fails the test suite.
* ``test_prompt3_gsd_meets_promotion_gate`` carries the strict Prompt 3 spec
  thresholds (95% solvent detect, median compound peak-count delta <= 2) and
  is marked ``xfail`` until the sidecar tuning closes the gap.  The day the
  test starts passing, remove the ``xfail`` and it becomes an enforced gate
  for the SpectraCheck promotion.

Both tests use the curated NMRShiftDB2 manifest under
``tests/fixtures/nmrshiftdb2/expected/nmrshiftdb2_bruker_20.json``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmrcheck.gsd_prompt3_validation import DEFAULT_LEVEL, run_all

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

# Regression floors -- intentionally a few percentage points below the values
# we just observed so harmless run-to-run wiggle from any numerical change
# in scipy/lmfit doesn't break the gate, but a real degradation does.
# Bumped 2026-05-27 after Phase 3a/3b tuning improved baseline.
_MIN_OK_FIXTURES = 20
_MIN_SOLVENT_DETECT_RATE_FLOOR = 0.92
_MIN_COMPOUND_WITHIN_MANIFEST_TOL_RATE_FLOOR = 0.40
_MAX_MEDIAN_ABS_COMPOUND_DELTA_FLOOR = 4.0

# Strict Prompt 3 promotion targets.
_PROMOTION_MIN_SOLVENT_DETECT_RATE = 0.95
_PROMOTION_MAX_MEDIAN_ABS_COMPOUND_DELTA = 2.0


@pytest.mark.current_state
def test_prompt3_gsd_harness_smoke_and_baseline_floor() -> None:
    report = run_all(_FIXTURES_ROOT, level=DEFAULT_LEVEL)
    summary = report["summary"]

    # Smoke: every fixture must be processed without raising.
    assert summary["fixture_count"] >= _MIN_OK_FIXTURES, (
        f"Fixture corpus shrunk: only {summary['fixture_count']} fixtures "
        f"loaded from the bundle."
    )
    assert summary["ok_count"] == summary["fixture_count"], (
        "At least one fixture failed during harness execution: "
        f"{[row['error'] for row in report['rows'] if row['row_status'] == 'error']}"
    )

    # Regression floor: solvent detect rate where reference shift is known.
    if summary["fixtures_with_solvent_reference"]:
        rate = summary["solvent_detect_rate"]
        assert rate is not None and rate >= _MIN_SOLVENT_DETECT_RATE_FLOOR, (
            f"Solvent detect rate {rate:.2%} fell below floor "
            f"{_MIN_SOLVENT_DETECT_RATE_FLOOR:.0%} "
            f"({summary['solvent_detected_count']}/"
            f"{summary['fixtures_with_solvent_reference']})"
        )

    # Regression floor: compound-only peak count vs manifest tolerance.
    compound_rate = summary["compound_peak_count_within_manifest_tol_rate"]
    assert (
        compound_rate is not None
        and compound_rate >= _MIN_COMPOUND_WITHIN_MANIFEST_TOL_RATE_FLOOR
    ), (
        f"Compound peak-count-within-manifest-tol rate {compound_rate:.2%} "
        f"fell below floor {_MIN_COMPOUND_WITHIN_MANIFEST_TOL_RATE_FLOOR:.0%}"
    )

    # Regression floor: median absolute compound peak count delta.
    median_delta = summary["median_abs_compound_peak_count_delta"]
    assert (
        median_delta is not None
        and median_delta <= _MAX_MEDIAN_ABS_COMPOUND_DELTA_FLOOR
    ), (
        f"Median absolute compound peak count delta {median_delta} exceeded "
        f"floor {_MAX_MEDIAN_ABS_COMPOUND_DELTA_FLOOR}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Prompt 3 sidecar promotion gate: 95% solvent detect and median "
        "compound peak-count delta <= 2 on NMRShiftDB2 corpus. Current "
        "baseline ~66.7%/median 4 -- requires sidecar tuning before xfail "
        "is removed and this becomes the SpectraCheck-promotion gate."
    ),
)
def test_prompt3_gsd_meets_promotion_gate() -> None:
    report = run_all(_FIXTURES_ROOT, level=DEFAULT_LEVEL)
    summary = report["summary"]

    solvent_rate = summary["solvent_detect_rate"]
    assert (
        solvent_rate is not None
        and solvent_rate >= _PROMOTION_MIN_SOLVENT_DETECT_RATE
    ), (
        f"Solvent detect rate {solvent_rate} below promotion gate "
        f"{_PROMOTION_MIN_SOLVENT_DETECT_RATE:.0%}"
    )

    median_delta = summary["median_abs_compound_peak_count_delta"]
    assert (
        median_delta is not None
        and median_delta <= _PROMOTION_MAX_MEDIAN_ABS_COMPOUND_DELTA
    ), (
        f"Median abs compound count delta {median_delta} above promotion "
        f"gate {_PROMOTION_MAX_MEDIAN_ABS_COMPOUND_DELTA}"
    )
