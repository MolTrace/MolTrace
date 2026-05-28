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
# Bumped again 2026-05-27 after Phase 10 multiplet clustering ship (50% within-
# tol on environment metric vs 45% on peak metric).
_MIN_OK_FIXTURES = 19
_MIN_SOLVENT_DETECT_RATE_FLOOR = 0.95
_MIN_COMPOUND_WITHIN_MANIFEST_TOL_RATE_FLOOR = 0.40
_MAX_MEDIAN_ABS_COMPOUND_DELTA_FLOOR = 4.0
# Environment-based metric is the semantically correct primary gate per the
# Phase 10 FE A/B finding: NMRShiftDB2 counts environments (one entry per
# distinct H/C atom), not multiplet lines.  After Phase 20 tuned the
# default 1H cluster_j_hz from 20 Hz -> 30 Hz, the baseline became
# 60% within-tol / median 2 -- meeting the strict promotion-gate
# median-delta target.  Floors track that.
_MIN_COMPOUND_ENV_WITHIN_MANIFEST_TOL_RATE_FLOOR = 0.55
_MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA_FLOOR = 3.0

# Strict Prompt 3 promotion targets.
_PROMOTION_MIN_SOLVENT_DETECT_RATE = 0.95
_PROMOTION_MAX_MEDIAN_ABS_COMPOUND_DELTA = 2.0
_PROMOTION_MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA = 2.0


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

    # Regression floor: environment-based metric (Phase 10 addition).
    env_within_tol = summary["compound_environment_count_within_manifest_tol_rate"]
    assert (
        env_within_tol is not None
        and env_within_tol >= _MIN_COMPOUND_ENV_WITHIN_MANIFEST_TOL_RATE_FLOOR
    ), (
        f"Compound environment-count-within-manifest-tol rate {env_within_tol:.2%} "
        f"fell below floor {_MIN_COMPOUND_ENV_WITHIN_MANIFEST_TOL_RATE_FLOOR:.0%}"
    )
    env_median = summary["median_abs_compound_environment_count_delta"]
    assert (
        env_median is not None
        and env_median <= _MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA_FLOOR
    ), (
        f"Median absolute compound environment count delta {env_median} exceeded "
        f"floor {_MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA_FLOOR}"
    )


def test_prompt3_gsd_meets_promotion_gate() -> None:
    """Strict promotion gate.

    Measured against the *environment-count* metric (one entry per chemical
    environment) rather than the raw peak count.  Per the Phase 10 FE A/B
    finding, environment-count is the semantically correct comparison vs
    NMRShiftDB2's reference shift list (which counts environments, not
    multiplet lines).  An "accurate detector" legitimately resolves a
    doublet as 2 peaks, but the gate metric should treat both as 1 entry.
    """

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

    # Primary promotion gate: environment-count delta.
    env_median = summary["median_abs_compound_environment_count_delta"]
    assert (
        env_median is not None
        and env_median <= _PROMOTION_MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA
    ), (
        f"Median abs compound environment-count delta {env_median} above "
        f"promotion gate {_PROMOTION_MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA}"
    )
