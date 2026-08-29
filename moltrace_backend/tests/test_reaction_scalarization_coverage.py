"""A missing analytical field must not read as a bad result.

``_score_outcome`` summed every weighted term with a missing value imputed as zero -- and for
impurity as ``100.0 - (impurity or 100.0)``, i.e. an unmeasured impurity scored as the WORST
possible impurity. The weights were not renormalised, so the score fell purely because fewer
fields were recorded.

Measured on the default multi-objective weights (yield .45 / selectivity .25 / impurity .20 /
conversion .10): a run recording only a 90 % yield scored **40.5**, while a fully-recorded
mediocre run (60/70/5/65) scored **70.0**. The surrogate trains on these numbers, so it was
being taught that fewer analytical fields means worse chemistry, and ``y_best`` inherited it.

The Pareto path already states the correct principle in a comment -- "an incomplete objective
vector cannot be placed on the front" -- and DROPS incomplete rows. So the same experiment was
dropped from the front and ranked-and-penalised in the scalar: two paths, one dataset, opposite
treatment.

Renormalising rather than dropping, because dominance and a weighted mean are different
questions. A Pareto front genuinely needs every dimension to compare vectors; a weighted mean
over the fields present is a legitimate estimate of the same quantity with more variance, and
BO campaigns have too few experiments to discard rows. The variance is disclosed rather than
hidden: coverage rides with the score and the run warns per experiment.
"""

from __future__ import annotations

import pytest

from nmrcheck.reaction_bo import _score_outcome

_WEIGHTS = {"yield": 0.45, "selectivity": 0.25, "impurity": 0.20, "conversion": 0.10}


def _score(outcome: dict) -> float:
    scored = _score_outcome(outcome, "multi_objective", _WEIGHTS)
    assert scored is not None
    return scored.score if hasattr(scored, "score") else scored


def test_a_partial_record_is_not_penalised_for_what_it_did_not_measure() -> None:
    # 90 % yield, nothing else recorded. Scored on yield alone it is a 90.
    assert _score({"yield_percent": 90.0}) == pytest.approx(90.0)


def test_an_excellent_partial_run_outranks_a_mediocre_complete_one() -> None:
    """The ordering the old imputation inverted."""

    partial_excellent = _score({"yield_percent": 90.0})
    complete_mediocre = _score(
        {
            "yield_percent": 60.0,
            "selectivity_percent": 70.0,
            "impurity_percent": 5.0,
            "conversion_percent": 65.0,
        }
    )
    assert partial_excellent > complete_mediocre, (
        f"a 90 % yield scored {partial_excellent} against {complete_mediocre} for a mediocre "
        "run that merely recorded more fields"
    )


def test_a_complete_record_is_unchanged() -> None:
    """Renormalisation must be a no-op when every weighted field is present."""

    outcome = {
        "yield_percent": 60.0,
        "selectivity_percent": 70.0,
        "impurity_percent": 5.0,
        "conversion_percent": 65.0,
    }
    expected = 60.0 * 0.45 + 70.0 * 0.25 + (100.0 - 5.0) * 0.20 + 65.0 * 0.10
    assert _score(outcome) == pytest.approx(expected)


def test_an_unmeasured_impurity_is_not_scored_as_the_worst_impurity() -> None:
    """The sharpest case: absence read as the worst possible measurement."""

    with_impurity = _score({"yield_percent": 80.0, "impurity_percent": 0.0})
    without_impurity = _score({"yield_percent": 80.0})
    # Not measuring impurity must not cost the run anything; measuring it at 0 % is the best
    # possible impurity and may raise the score, never the reverse.
    assert without_impurity <= with_impurity + 1e-9
    assert without_impurity == pytest.approx(80.0)


def test_coverage_travels_with_the_score() -> None:
    """A score from one of four fields is not as firm as one from four; say so."""

    partial = _score_outcome({"yield_percent": 90.0}, "multi_objective", _WEIGHTS)
    complete = _score_outcome(
        {
            "yield_percent": 60.0,
            "selectivity_percent": 70.0,
            "impurity_percent": 5.0,
            "conversion_percent": 65.0,
        },
        "multi_objective",
        _WEIGHTS,
    )
    assert partial is not None and complete is not None
    assert complete.coverage == pytest.approx(1.0)
    assert partial.coverage == pytest.approx(0.45)  # yield's share of the weight budget
    assert set(partial.missing_fields) == {
        "selectivity_percent",
        "impurity_percent",
        "conversion_percent",
    }
    assert complete.missing_fields == ()
