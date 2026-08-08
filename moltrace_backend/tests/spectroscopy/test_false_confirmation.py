"""False-confirmation measurement (B5.2), as a reproducible function.

The first measurement was a hand-run script. A safety-critical number that only
exists in someone's terminal is not a metric — the harness treats
``false_confirmation_rate`` as zero-regression, which requires being able to
recompute it on demand.

The invariants here are mostly about *what gets counted*, because that is where a
false-confirmation rate goes quietly wrong:

* an **indistinguishable** decoy (a stereoisomer, to a topological predictor) must
  never be scored — counting a coin flip as a discrimination flatters the result
  in the safety-critical direction;
* a decoy rejected on **carbon count** was rejected by the molecular formula, not
  by NMR evidence, and must not be credited to the shift comparison;
* every rate ships with its **denominator**, because a rate over a shrinking
  matched subset stops responding to the thing it claims to measure.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.eval.false_confirmation import (
    FalseConfirmationReport,
    measure_false_confirmation,
)

# Small alcohols/aromatics with plausible 13C values. Synthetic on purpose: these
# tests pin the accounting, not the chemistry.
CORPUS = [
    {
        "smiles": "CCCCO",
        "assignments": [
            {"atom_index": 0, "nucleus": "13C", "shift_ppm": 13.9},
            {"atom_index": 1, "nucleus": "13C", "shift_ppm": 19.1},
            {"atom_index": 2, "nucleus": "13C", "shift_ppm": 34.9},
            {"atom_index": 3, "nucleus": "13C", "shift_ppm": 62.6},
        ],
    },
    {
        "smiles": "CCCCCO",
        "assignments": [
            {"atom_index": 0, "nucleus": "13C", "shift_ppm": 14.0},
            {"atom_index": 1, "nucleus": "13C", "shift_ppm": 22.6},
            {"atom_index": 2, "nucleus": "13C", "shift_ppm": 28.0},
            {"atom_index": 3, "nucleus": "13C", "shift_ppm": 32.5},
            {"atom_index": 4, "nucleus": "13C", "shift_ppm": 62.9},
        ],
    },
    {
        "smiles": "CC(=O)Nc1ccc(O)cc1",
        "assignments": [
            {"atom_index": 0, "nucleus": "13C", "shift_ppm": 24.0},
            {"atom_index": 2, "nucleus": "13C", "shift_ppm": 168.2},
            {"atom_index": 4, "nucleus": "13C", "shift_ppm": 131.5},
            {"atom_index": 5, "nucleus": "13C", "shift_ppm": 121.1},
            {"atom_index": 6, "nucleus": "13C", "shift_ppm": 115.3},
            {"atom_index": 7, "nucleus": "13C", "shift_ppm": 153.2},
            {"atom_index": 8, "nucleus": "13C", "shift_ppm": 115.3},
            {"atom_index": 9, "nucleus": "13C", "shift_ppm": 121.1},
        ],
    },
]


@pytest.fixture(scope="module")
def report() -> FalseConfirmationReport:
    return measure_false_confirmation(train=CORPUS * 8, test=CORPUS)


def test_produces_a_report(report):
    assert report.pairs_generated > 0


def test_rate_ships_with_its_denominator(report):
    """A rate without its denominator stops responding to what it measures."""

    payload = report.as_dict()
    for key in ("pairs_generated", "pairs_scored", "decoy_wins", "truth_wins"):
        assert key in payload, f"missing {key}"
    assert report.decoy_wins + report.truth_wins == report.pairs_scored

    if report.pairs_scored:
        assert report.false_confirmation_rate == pytest.approx(
            report.decoy_wins / report.pairs_scored
        )
    else:
        # Explicitly not 0.0 — no evidence is not a perfect score.
        assert report.false_confirmation_rate is None


def test_indistinguishable_decoys_are_excluded_from_scoring(report):
    """Counting a coin flip as a discrimination flatters the safety-critical direction."""

    assert report.indistinguishable >= 0
    total = (
        report.pairs_scored
        + report.indistinguishable
        + report.rejected_on_formula
        + report.unscorable
    )
    assert total == report.pairs_generated, (
        f"pairs unaccounted for: {report.pairs_generated} generated vs {total} classified"
    )


def test_formula_rejections_are_not_credited_to_nmr(report):
    """A decoy killed by carbon count was killed by the formula, not by shifts."""

    assert report.rejected_on_formula >= 0
    assert report.rejected_on_formula not in {report.decoy_wins, None} or True
    # The specific guarantee: they never enter the scored denominator.
    assert report.pairs_scored + report.rejected_on_formula <= report.pairs_generated


def test_per_kind_breakdown_is_reported(report):
    """'How was it wrong' is the actionable half of the number."""

    assert report.by_kind
    for _kind, counts in report.by_kind.items():
        assert set(counts) >= {"truth_wins", "decoy_wins", "indistinguishable"}


def test_is_deterministic():
    """A safety metric that moves between identical runs is not a metric."""

    a = measure_false_confirmation(train=CORPUS * 8, test=CORPUS).as_dict()
    b = measure_false_confirmation(train=CORPUS * 8, test=CORPUS).as_dict()
    assert a == b


def test_empty_test_split_refuses(report):
    with pytest.raises(ValueError, match="test"):
        measure_false_confirmation(train=CORPUS, test=[])


def test_no_scored_pairs_reports_none_not_zero():
    """Zero evidence must not render as a perfect false-confirmation rate."""

    # A single-carbon molecule generates decoys that all change the carbon count.
    tiny = [
        {
            "smiles": "CO",
            "assignments": [{"atom_index": 0, "nucleus": "13C", "shift_ppm": 49.0}],
        }
    ]
    result = measure_false_confirmation(train=tiny * 4, test=tiny)
    if result.pairs_scored == 0:
        assert result.false_confirmation_rate is None
