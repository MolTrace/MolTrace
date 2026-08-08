"""The three-way split conformal needs, and the trap it exists to avoid.

Conformal calibration must be fitted on molecules disjoint from *both* the training
data and the split coverage is scored on. The obvious way to get there — call
``split_records`` twice — silently returns an empty calibration set, because the
split is a deterministic function of the molecule hash and every held-out record
already sits below the first threshold.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.eval.shift_accuracy import (
    split_records,
    split_records_three_way,
)

_RECORDS = [{"smiles": f"C{'C' * (i % 17)}O{i}", "assignments": []} for i in range(4000)]


def test_recursive_splitting_is_the_trap_this_replaces() -> None:
    """Documents the failure mode: re-splitting a held-out set collapses it."""

    _train, held_out = split_records(_RECORDS, test_fraction=0.20)
    assert held_out, "precondition: the first split produced a held-out set"

    calibration, evaluation = split_records(held_out, test_fraction=0.50)
    assert calibration == [], (
        "re-splitting with the same hash is expected to put everything on one side; "
        "if this ever passes, the trap has changed and the docstring is stale"
    )
    assert len(evaluation) == len(held_out)


def test_the_three_bands_are_disjoint_and_exhaustive() -> None:
    train, calibration, test = split_records_three_way(_RECORDS)
    assert len(train) + len(calibration) + len(test) == len(_RECORDS)

    def keys(records: list) -> set[str]:
        return {r["smiles"] for r in records}

    assert not keys(train) & keys(calibration)
    assert not keys(train) & keys(test)
    assert not keys(calibration) & keys(test)


def test_every_band_is_non_empty_at_the_defaults() -> None:
    train, calibration, test = split_records_three_way(_RECORDS)
    assert train and calibration and test
    # ~80/10/10, allowing for hash granularity on this sample size.
    assert 0.05 < len(calibration) / len(_RECORDS) < 0.16
    assert 0.05 < len(test) / len(_RECORDS) < 0.16


def test_the_split_is_deterministic_and_order_independent() -> None:
    a = split_records_three_way(_RECORDS)
    b = split_records_three_way(list(reversed(_RECORDS)))
    for left, right in zip(a, b, strict=True):
        assert {r["smiles"] for r in left} == {r["smiles"] for r in right}


def test_a_molecule_never_straddles_two_bands() -> None:
    """Records sharing a molecule must land together, or the holdout leaks."""

    duplicated = [dict(r) for r in _RECORDS] + [dict(r) for r in _RECORDS]
    train, calibration, test = split_records_three_way(duplicated)
    for band in (train, calibration, test):
        counts: dict[str, int] = {}
        for record in band:
            counts[record["smiles"]] = counts.get(record["smiles"], 0) + 1
        assert all(c == 2 for c in counts.values()), "a duplicate pair was split apart"


def test_the_test_band_matches_the_two_way_split() -> None:
    """Same hash, same threshold: the held-out set does not move when calibration is carved out."""

    _train, two_way_test = split_records(_RECORDS, test_fraction=0.10)
    _t, _c, three_way_test = split_records_three_way(_RECORDS, test_fraction=0.10)
    assert {r["smiles"] for r in two_way_test} == {r["smiles"] for r in three_way_test}


@pytest.mark.parametrize(
    ("calibration_fraction", "test_fraction"),
    [(0.0, 0.1), (1.0, 0.1), (0.1, 0.0), (0.1, 1.0), (0.6, 0.5)],
)
def test_impossible_fractions_are_refused(
    calibration_fraction: float, test_fraction: float
) -> None:
    with pytest.raises(ValueError):
        split_records_three_way(
            _RECORDS,
            calibration_fraction=calibration_fraction,
            test_fraction=test_fraction,
        )
