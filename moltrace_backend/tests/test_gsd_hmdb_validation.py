"""Fixture-validation gate for the Prompt 3 GSD sidecar on the real HMDB corpus.

Two tests share the harness:

* ``test_gsd_hmdb_harness_smoke`` (``current_state``, default) — runs the
  harness over the first 5 HMDB fixtures (~15 s) and asserts the end-to-end
  pipeline still works: parses raw FIDs, picks peaks, normalises solvents, and
  produces well-formed report rows.  This is the fast smoke that runs on every
  pytest invocation.
* ``test_gsd_hmdb_harness_full_pass`` (opt-in ``slow`` marker) — runs the
  harness over all 100 curated HMDB fixtures (~4 min) and gates parseable_rate
  and solvent_detect_rate against floors at the most recent observed values
  minus margin.  Excluded from the default suite via the ``slow`` marker; run
  with ``pytest -m slow``.

We intentionally do NOT gate on per-peak-count delta against the HMDB peak
list because HMDB's ``distinct-peaks`` is curator-dependent (1 to 190 peaks
per fixture in the curated 100-fixture subset) and does not represent a
ground-truth peak count.  The semantically meaningful HMDB-corpus signals are
parseability and solvent auto-detection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmrcheck.gsd_hmdb_validation import DEFAULT_LEVEL, run_all

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

# Smoke test: small subset, every row must process without raising.
_SMOKE_LIMIT = 5

# Full-pass gate floors.  Set ~2 percentage points below the most recent
# observed values so harmless run-to-run wiggle from any scipy/lmfit
# numerical change does not break the gate, but a real degradation does.
#
# Observed 2026-05-28 on the full 100-fixture HMDB corpus at level=2 with
# the Phase 27 depth-8 dataset-root walker:
#   parseable_rate                       0.95   (95/100 fixtures parse cleanly)
#   solvent_detect_rate                  0.93   (53/57 fixtures with a solvent
#                                                reference auto-detect the
#                                                expected solvent peak)
_FULL_PARSEABLE_RATE_FLOOR = 0.93
_FULL_SOLVENT_DETECT_RATE_FLOOR = 0.90


@pytest.mark.current_state
def test_gsd_hmdb_harness_smoke() -> None:
    """Fast smoke: harness loads + processes the first 5 HMDB fixtures."""
    report = run_all(_FIXTURES_ROOT, level=DEFAULT_LEVEL, limit=_SMOKE_LIMIT)
    summary = report["summary"]

    assert summary["fixture_count"] == _SMOKE_LIMIT, (
        f"Smoke expected {_SMOKE_LIMIT} fixtures, got {summary['fixture_count']}"
    )
    assert summary["ok_count"] + summary["error_count"] == summary["fixture_count"], (
        "Row count accounting mismatch"
    )

    # Every OK row must carry the canonical schema fields.
    required = {
        "fixture_id",
        "hmdb_id",
        "spectrum_id",
        "nucleus",
        "vendor",
        "row_status",
        "prompt_peak_count",
        "prompt_compound_peak_count",
        "prompt_environment_count",
        "prompt_compound_environment_count",
    }
    for row in report["rows"]:
        missing = required - row.keys()
        assert not missing, f"Row {row.get('fixture_id')} missing fields: {missing}"


@pytest.mark.slow
def test_gsd_hmdb_harness_full_pass() -> None:
    """Full-pass gate: run all 100 fixtures and enforce parseable + solvent floors.

    Excluded from the default test run via the ``slow`` marker because it
    takes ~4 minutes.  Run explicitly with ``pytest -m slow``.
    """
    report = run_all(_FIXTURES_ROOT, level=DEFAULT_LEVEL)
    summary = report["summary"]

    parseable = summary["parseable_rate"]
    assert parseable is not None and parseable >= _FULL_PARSEABLE_RATE_FLOOR, (
        f"HMDB parseable_rate {parseable:.2%} fell below floor "
        f"{_FULL_PARSEABLE_RATE_FLOOR:.0%} "
        f"({summary['ok_count']}/{summary['fixture_count']})"
    )

    if summary["fixtures_with_solvent_reference"]:
        solvent = summary["solvent_detect_rate"]
        assert (
            solvent is not None and solvent >= _FULL_SOLVENT_DETECT_RATE_FLOOR
        ), (
            f"HMDB solvent_detect_rate {solvent:.2%} fell below floor "
            f"{_FULL_SOLVENT_DETECT_RATE_FLOOR:.0%} "
            f"({summary['solvent_detected_count']}/"
            f"{summary['fixtures_with_solvent_reference']})"
        )
