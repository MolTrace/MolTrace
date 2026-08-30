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
# Re-baselined 2026-08-30, and the strictness moved rather than removed. Fixing the
# seeded linewidth (`peak_widths` was measuring at a contour BELOW the baseline for
# 85.7% of peaks; worst seed 761x the width the trace has) changes which peaks the
# classifier can believe, and this coarse binary rate fell by exactly ONE compound of
# nineteen: 0.4211 -> 0.3684, a 5.3% move on a rate whose own standard error is 11.3%.
#
# It would be cheap and wrong to simply lower this and call the change shipped, so the
# two gates below were ADDED in the same commit. They pin the direct measures -- did we
# find the curated shifts, could the classifier believe the peaks -- which the coarse
# count proxy only approximates, and BOTH FAIL on the pre-fix code:
#
#   quantity                     pre-fix   after    new ceiling   verdict
#   unmatched curated shifts        78       68          72       pre-fix FAILS
#   peaks classified artifact       55       36          42       pre-fix FAILS
#   curated shifts matched          22       25          --       +3
#
# So the suite is strictly harder to pass than it was, not easier.
_MIN_COMPOUND_WITHIN_MANIFEST_TOL_RATE_FLOOR = 0.35

#: Curated reference shifts the detector failed to match, summed over the corpus.
#: Observed 68 after the linewidth-seed fix, against 78 before it. The 10-shift
#: improvement is spread over seven compounds rather than carried by one -- removing
#: any single fixture leaves 54-68 -- so the 4 of headroom here is a margin, not a
#: fixture's worth of slack.
_MAX_UNMATCHED_REFERENCE_PPM = 72

#: Peaks the classifier could not place, summed over the corpus. An artifact is a peak
#: it declined to believe, and the seeded width was a reason it declined: correcting the
#: width moved 19 of these into compound (+14) and impurity (+6). Observed 36 against 55
#: before; LOO 25-36.
_MAX_ARTIFACT_PEAKS = 42
_MAX_MEDIAN_ABS_COMPOUND_DELTA_FLOOR = 4.0
# Environment-based metric is the semantically correct primary gate per the
# Phase 10 FE A/B finding: NMRShiftDB2 counts environments (one entry per
# distinct H/C atom), not multiplet lines.  After Phase 20 tuned the
# default 1H cluster_j_hz from 20 Hz -> 30 Hz, the baseline became
# 60% within-tol / median 2 -- meeting the strict promotion-gate
# median-delta target.  Floors track that.
_MIN_COMPOUND_ENV_WITHIN_MANIFEST_TOL_RATE_FLOOR = 0.55
_MAX_MEDIAN_ABS_COMPOUND_ENV_DELTA_FLOOR = 3.0

# Direction and ratio floors, added 2026-08-27 (report v2).
#
# Every floor above is an absolute-value median or a within-tolerance rate, so none of
# them can distinguish picking too many lines from picking too few. A change that traded
# over-picking for under-picking would have scored as an improvement on all of them.
#
# Measured on the 19-fixture corpus at level 2, per-detector
# (moltrace.spectroscopy.peaks.gsd -- the harness does not exercise nmrcheck.gsd):
#
#   stage                     median   p90    max     what it is
#   raw total picks            3.00x   5.00x  32.00x  the detector, before classification
#   after classification       1.20x   3.20x   7.00x  compound lines only
#   after clustering           1.14x   1.60x   7.00x  environments -- what analysis consumes
#
#   signed median delta: total +17, compound +1, environment +1
#   over/under/exact:    total 18/1/0, compound 12/5/2, environment 11/7/1
#
# So the documented "3-7x over-pick" is real and reproducible, but it describes the RAW
# detector. Classification and clustering remove most of it, and the stage that feeds
# analysis sits at 1.14x. Tightening the detector to chase 3x would push a stage that is
# already near-centred into systematic under-picking, which is why these bounds are
# two-sided rather than ceilings.
#
# Bounds come from the measured leave-one-out spread, not from round numbers, and were
# calibrated against a specific adversarial case: mirroring every signed delta about zero
# (a change that trades over-picking for under-picking) must FAIL. A first draft of these
# bounds used comfortable-looking margins -- ratio [0.85, 1.45], signed [-1.0, 3.0] -- and
# the mirrored case passed all three, which is the whole defect reproduced inside the fix.
#
#   quantity                   observed   leave-one-out spread   mirrored case
#   raw total ratio median       3.000          0.464                 --
#   env ratio median             1.143          0.009               0.86  -> must fail
#   env signed median delta      1.0            0.0                -1.0   -> must fail
#
# The env median is stable to nine thousandths under removal of any single fixture, so a
# band of 0.14 below and 0.21 above observed is already ~15x any plausible wiggle.
_MAX_RAW_TOTAL_RATIO_MEDIAN = 3.6            # observed 3.00, LOO spread 0.46
_ENV_RATIO_MEDIAN_BOUNDS = (1.00, 1.35)      # observed 1.143, LOO spread 0.009
_ENV_SIGNED_MEDIAN_DELTA_BOUNDS = (0.0, 3.0)  # observed +1; 0 is ideal, negative is the trade

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

    # DIRECT MEASURES, added when the coarse count rate above was re-baselined. A
    # count landing inside a tolerance is a proxy for finding the right chemistry;
    # these two are the thing itself, and they are what stop the proxy being relaxed
    # into meaninglessness.
    rows = report["rows"]
    unmatched = sum(int(row.get("reference_ppm_unmatched_count") or 0) for row in rows)
    assert unmatched <= _MAX_UNMATCHED_REFERENCE_PPM, (
        f"{unmatched} curated reference shifts went unmatched, above the ceiling of "
        f"{_MAX_UNMATCHED_REFERENCE_PPM}. The detector is finding less of the "
        "chemistry the manifest says is there."
    )

    artifacts = sum(
        int((row.get("category_counts") or {}).get("artifact", 0)) for row in rows
    )
    assert artifacts <= _MAX_ARTIFACT_PEAKS, (
        f"{artifacts} peaks were classified as artifact, above the ceiling of "
        f"{_MAX_ARTIFACT_PEAKS}. The classifier is declining to believe peaks it "
        "previously placed."
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

    # --- Direction and ratio (report v2) --------------------------------- #
    # A truncated pick is a floor, not a measurement, and every count downstream of it
    # inherits that -- so the ratios below would stop meaning anything.
    assert summary["peak_cap_saturated_count"] == 0, (
        f"{summary['peak_cap_saturated_count']} fixture(s) hit the level-{DEFAULT_LEVEL} "
        f"cap of {summary['peak_cap']} picks; their counts are floors, not measurements"
    )

    raw_median = summary["over_pick_ratio"]["all"]["raw_total"]["median"]
    assert raw_median is not None and raw_median <= _MAX_RAW_TOTAL_RATIO_MEDIAN, (
        f"Raw detector picked {raw_median:.2f}x the expected line count, above "
        f"{_MAX_RAW_TOTAL_RATIO_MEDIAN}x"
    )

    # Two-sided. This is the stage analysis consumes, and under-picking a real resonance
    # is not an improvement over over-picking a spurious one -- it is the worse error,
    # because a missing line cannot be filtered downstream.
    env_ratio = summary["over_pick_ratio"]["all"]["after_clustering"]["median"]
    low, high = _ENV_RATIO_MEDIAN_BOUNDS
    assert env_ratio is not None and low <= env_ratio <= high, (
        f"Environment pick ratio {env_ratio:.2f}x left the band [{low}, {high}] -- "
        f"{'under' if env_ratio is not None and env_ratio < low else 'over'}-picking"
    )

    env_signed = summary["direction"]["compound_environment_count"]["median_signed"]
    low, high = _ENV_SIGNED_MEDIAN_DELTA_BOUNDS
    assert env_signed is not None and low <= env_signed <= high, (
        f"Signed median environment delta {env_signed} left the band [{low}, {high}]; "
        f"over={summary['direction']['compound_environment_count']['over_count']} "
        f"under={summary['direction']['compound_environment_count']['under_count']}"
    )


@pytest.mark.slow
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


def _within(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


def test_the_direction_bounds_reject_an_over_for_under_trade() -> None:
    """The bounds must fail the case they exist for, not merely pass today.

    Absolute-value medians cannot see direction: mirroring every signed delta about zero
    leaves ``median_abs_compound_environment_count_delta`` bit-identical, so every v1 floor
    scores the mirrored detector exactly as it scores this one. These are the numbers that
    mirrored run produces, and the bounds must reject them.

    Under-picking is the worse failure of the two. A spurious line can be filtered
    downstream; a resonance that was never picked cannot be recovered.
    """

    # Measured on the 19-fixture corpus, then mirrored (see the table above).
    assert _within(1.1429, _ENV_RATIO_MEDIAN_BOUNDS), "today's ratio must pass"
    assert _within(1.0, _ENV_SIGNED_MEDIAN_DELTA_BOUNDS), "today's signed median must pass"

    assert not _within(0.8571, _ENV_RATIO_MEDIAN_BOUNDS), (
        "a detector under-picking by the same margin it currently over-picks must fail"
    )
    assert not _within(-1.0, _ENV_SIGNED_MEDIAN_DELTA_BOUNDS), (
        "a signed median of -1 is systematic under-picking and must fail"
    )
