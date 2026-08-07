"""A numeric design-space variable the optimizer cannot parse must not pass silently.

`POST /reaction-projects/{id}/design-space` takes `numeric_variables_json` as a
free-form object, so any dict shape is accepted at 201. Only a few spellings are
actually understood by `_numeric_values_from_spec`: a bare list, `{"values": …}`,
`{"min"/"max"}`, `{"min_value"/"max_value"}`.

`{"low": 20, "high": 100}` — an entirely natural way to write a range — parsed
to **no values at all**, so the variable was dropped from the search domain.
With every variable dropped the candidate generator had nothing to enumerate and
the Bayesian optimizer evaluated exactly ONE point, recommended the worst region
of the space with `expected_improvement = 0.0`, and reported
`status: "succeeded"`.

Measured on a real loop before the fix: 14 well-spread observations, a healthy
`Matern(length_scale=0.378)` kernel, best observed 81.2 at T=70/cat=4.5 — and the
single recommendation was T=40/cat=1.0 at EI 0.0. Given the same data with a
DISCRETE design space the optimizer searched all 35 grid points and proposed
T=80/cat=5.0 at predicted 82.8, EI 3.18, beating the incumbent. The optimizer was
never the problem; the design space silently never reached it.

Two guards, because the first alone is not enough — some other spelling will
always be missed:

  1. `low`/`high` (and `lower`/`upper`) are understood.
  2. A numeric spec that yields no values is REPORTED, so an unparsed variable
     can never again be mistaken for a searched one.
"""

from __future__ import annotations

import pytest

from nmrcheck.reaction_bo import _numeric_values_from_spec


class TestRangeSpellings:
    """Every spelling a chemist might reasonably write for a range."""

    @pytest.mark.parametrize(
        "spec",
        [
            {"min": 20, "max": 100},
            {"min_value": 20, "max_value": 100},
            {"low": 20, "high": 100},
            {"lower": 20, "upper": 100},
        ],
        ids=["min/max", "min_value/max_value", "low/high", "lower/upper"],
    )
    def test_a_range_yields_searchable_values(self, spec: dict) -> None:
        values, (low, high) = _numeric_values_from_spec(spec)
        assert values, f"{spec} parsed to no values — the variable would be dropped"
        assert (low, high) == (20.0, 100.0)
        assert len(values) >= 3, f"a range should give at least low/mid/high, got {values}"

    def test_an_explicit_value_list_still_wins(self) -> None:
        values, rng = _numeric_values_from_spec([30, 40, 50])
        assert values == [30.0, 40.0, 50.0] and rng == (30.0, 50.0)

    def test_values_key_still_wins(self) -> None:
        values, _ = _numeric_values_from_spec({"values": [1.0, 2.0]})
        assert values == [1.0, 2.0]


class TestUnparseableSpecsAreVisible:
    """The second guard: silence is what turned a typo into a broken optimizer."""

    @pytest.mark.parametrize(
        "spec",
        [
            {"lo": 20, "hi": 100},          # not a recognised spelling
            {"from": 20, "to": 100},        # nor this
            {},                             # empty
            {"min": None, "max": None},     # present but unusable
            "not-a-spec",                   # wrong type entirely
        ],
        ids=["lo/hi", "from/to", "empty", "null-bounds", "string"],
    )
    def test_an_unparseable_spec_yields_nothing(self, spec) -> None:
        """Pins the behaviour the caller must be told about."""
        values, _ = _numeric_values_from_spec(spec)
        assert values == [], (
            f"{spec!r} now parses — if a new spelling was added, add it to the "
            "recognised list above too"
        )


def test_a_range_produces_a_grid_not_three_points() -> None:
    """Three points (low, mid, high) is too coarse to optimise over.

    The pre-fix behaviour returned exactly [low, midpoint, high]. Two such
    variables give a 3x3 = 9 point grid, which is a defensible minimum, but a
    real continuous variable deserves finer resolution before the acquisition
    function is asked to pick a winner.
    """
    values, _ = _numeric_values_from_spec({"low": 0.0, "high": 100.0})
    assert len(values) >= 5, (
        f"a continuous range gives only {len(values)} candidate levels: {values}. "
        "That is too coarse for the acquisition function to discriminate."
    )
    assert values[0] == 0.0 and values[-1] == 100.0, "the bounds must be included"
