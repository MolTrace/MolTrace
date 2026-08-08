"""Held-out shift-accuracy evaluation (B5).

Why held-out, specifically
--------------------------
The HOSE knowledge base is built *from* NMRShiftDB2. Scoring the predictor on
NMRShiftDB2 molecules that are already in that table measures memorisation, not
accuracy — every atom finds its own reference and the error goes to ~0. That
number would be both excellent and meaningless, and it is exactly the
data-leakage failure the deployment gate exists to catch.

So the split is **by molecule**, deterministic, and the tests below pin the two
properties that make the resulting number honest:

1. train and test never share a molecule;
2. the split is stable across runs, so a reported figure can be reproduced.

What is actually measured
-------------------------
Not just MAE. MAE alone hides the failures that matter, so the report carries the
error *distribution* (median, p90, p95, max), the **coverage** (what fraction of
atoms found a real environment rather than the element prior), and a
**calibration** table — because the predictor's reported σ is what DP4 and the
verifier's significance mapping both consume. A σ that does not predict the
actual error makes every downstream probability arithmetic without evidence,
however good the headline MAE looks.
"""

from __future__ import annotations

import math

import pytest

from moltrace.spectroscopy.eval.shift_accuracy import (
    ShiftAccuracyReport,
    evaluate_shift_accuracy,
    split_records,
)

# Two tiny molecules with hand-written assignments. Deliberately synthetic: these
# tests pin the evaluation machinery, not the science.
ETHANOL = {
    "smiles": "CCO",
    "assignments": [
        {"atom_index": 0, "nucleus": "13C", "shift_ppm": 18.2},
        {"atom_index": 1, "nucleus": "13C", "shift_ppm": 58.4},
    ],
}
PROPANOL = {
    "smiles": "CCCO",
    "assignments": [
        {"atom_index": 0, "nucleus": "13C", "shift_ppm": 10.2},
        {"atom_index": 1, "nucleus": "13C", "shift_ppm": 25.8},
        {"atom_index": 2, "nucleus": "13C", "shift_ppm": 64.5},
    ],
}
BUTANOL = {
    "smiles": "CCCCO",
    "assignments": [
        {"atom_index": 0, "nucleus": "13C", "shift_ppm": 13.9},
        {"atom_index": 1, "nucleus": "13C", "shift_ppm": 19.1},
        {"atom_index": 2, "nucleus": "13C", "shift_ppm": 34.9},
        {"atom_index": 3, "nucleus": "13C", "shift_ppm": 62.6},
    ],
}
CORPUS = [ETHANOL, PROPANOL, BUTANOL]


# --------------------------------------------------------------------------- #
# The split is what makes the number honest
# --------------------------------------------------------------------------- #
def test_split_shares_no_molecule_between_train_and_test():
    """Leakage here would make the reported error meaninglessly good."""

    train, test = split_records(CORPUS * 20, test_fraction=0.3)
    assert train and test

    def key(record):
        return record.get("molblock") or record.get("smiles")

    assert not (set(map(key, train)) & set(map(key, test))), (
        "a molecule appears in both splits — the reported error would be memorisation"
    )


def test_split_is_deterministic_so_a_number_can_be_reproduced():
    """A benchmark you cannot re-run is not a benchmark."""

    a_train, a_test = split_records(CORPUS * 20, test_fraction=0.3)
    b_train, b_test = split_records(CORPUS * 20, test_fraction=0.3)
    assert [r["smiles"] for r in a_test] == [r["smiles"] for r in b_test]
    assert len(a_train) == len(b_train)


def _distinct_corpus(n: int) -> list[dict]:
    """``n`` distinct linear alcohols, so the split has something to divide.

    Repeating a handful of molecules would not exercise the fraction at all: all
    copies of a molecule land on the same side by design, so with three distinct
    structures the achievable test fraction is quantised to thirds.
    """

    return [
        {
            "smiles": "C" * (i + 2) + "O",
            "assignments": [
                {"atom_index": 0, "nucleus": "13C", "shift_ppm": 14.0 + 0.1 * i},
                {"atom_index": 1, "nucleus": "13C", "shift_ppm": 60.0 + 0.1 * i},
            ],
        }
        for i in range(n)
    ]


def test_split_respects_the_requested_fraction_approximately():
    records = _distinct_corpus(200)
    _train, test = split_records(records, test_fraction=0.25)
    # Hash-based assignment, so approximate rather than exact.
    assert 0.15 < len(test) / len(records) < 0.35


def test_empty_test_split_refuses_rather_than_reporting_nothing():
    with pytest.raises(ValueError, match="test split"):
        evaluate_shift_accuracy(train=CORPUS, test=[])


# --------------------------------------------------------------------------- #
# What the report must contain
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def report() -> ShiftAccuracyReport:
    train, test = split_records(CORPUS * 30, test_fraction=0.34)
    return evaluate_shift_accuracy(train=train, test=test)


def test_report_carries_the_distribution_not_only_the_mean(report):
    """MAE hides the tail, and the tail is where a wrong structure gets confirmed."""

    stats = report.per_nucleus["13C"]
    for field in ("mae_ppm", "median_ae_ppm", "p90_ae_ppm", "p95_ae_ppm", "max_ae_ppm"):
        assert field in stats, f"missing {field}"
        assert math.isfinite(stats[field])
    assert stats["median_ae_ppm"] <= stats["p90_ae_ppm"] <= stats["max_ae_ppm"]


def test_report_carries_coverage(report):
    """An error computed only over matched atoms would flatter a sparse table."""

    stats = report.per_nucleus["13C"]
    assert 0.0 <= stats["coverage"] <= 1.0
    assert stats["n_atoms"] > 0
    assert stats["n_matched"] + stats["n_element_prior"] == stats["n_atoms"]


def test_report_carries_a_calibration_table(report):
    """The reported sigma is what DP4 and the verifier consume; it must be checked."""

    assert report.calibration, "no calibration bins produced"
    for row in report.calibration:
        assert {"sigma_bin", "n", "mean_sigma_ppm", "mean_abs_error_ppm"} <= set(row)
        assert row["n"] > 0


def test_report_is_json_serialisable(report):
    """It has to land in a metric record, not just a terminal."""

    import json

    payload = json.loads(json.dumps(report.as_dict()))
    assert payload["per_nucleus"]["13C"]["n_atoms"] > 0
    assert "n_train_molecules" in payload and "n_test_molecules" in payload


def test_matched_predictions_beat_the_element_prior(report):
    """The whole premise: a matched environment is better than an element average.

    If this ever fails, the HOSE lookup is not adding information and the
    knowledge base is decorative.
    """

    stats = report.per_nucleus["13C"]
    if stats["n_matched"] == 0 or stats["n_element_prior"] == 0:
        pytest.skip(
            "this split has no matched atoms or no element-prior atoms, so there is "
            "nothing to compare — see the dedicated mixed-coverage case below"
        )
    assert stats["matched_mae_ppm"] < stats["element_prior_mae_ppm"], (
        f"matched MAE {stats['matched_mae_ppm']:.2f} is not better than the element "
        f"prior's {stats['element_prior_mae_ppm']:.2f} — the lookup adds nothing"
    )


def test_matched_beats_element_prior_on_a_mixed_coverage_split():
    """The premise, tested where it can actually be observed.

    Constructed so the test split contains both kinds of atom: alcohols whose
    environments the training table has seen, plus a fluorinated molecule whose
    carbons it has not, which must fall back to the element average.
    """

    train = _distinct_corpus(80)
    test = [
        {
            "smiles": "CCCCCCO",  # environments the alcohols cover
            "assignments": [
                {"atom_index": 0, "nucleus": "13C", "shift_ppm": 14.0},
                {"atom_index": 1, "nucleus": "13C", "shift_ppm": 60.2},
            ],
        },
        {
            "smiles": "FC(F)(F)c1ccccc1",  # nothing like it in training
            "assignments": [
                {"atom_index": 1, "nucleus": "13C", "shift_ppm": 124.5},
                {"atom_index": 5, "nucleus": "13C", "shift_ppm": 128.9},
            ],
        },
    ]

    report = evaluate_shift_accuracy(train=train, test=test)
    stats = report.per_nucleus["13C"]
    assert stats["n_matched"] > 0 and stats["n_element_prior"] > 0, (
        f"needed both kinds of atom; got matched={stats['n_matched']}, "
        f"prior={stats['n_element_prior']}"
    )
    assert stats["matched_mae_ppm"] < stats["element_prior_mae_ppm"], (
        f"matched MAE {stats['matched_mae_ppm']:.2f} is not better than the element "
        f"prior's {stats['element_prior_mae_ppm']:.2f} — the lookup adds nothing"
    )


def test_evaluation_does_not_consult_the_test_molecules_own_shifts(report):
    """Sanity: a perfect score would mean the test data leaked into the table."""

    stats = report.per_nucleus["13C"]
    assert stats["mae_ppm"] > 0.0, (
        "zero error on held-out data means the test molecules were in the training "
        "knowledge base"
    )
