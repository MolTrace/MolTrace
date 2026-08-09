"""An HSQC score has to know what the structure predicts, not just what was found.

C1 measured the defect: `dimension_possible` counted **observed** cross peaks, so
the denominator was whatever the spectrum happened to contain. Withholding five
of seven ibuprofen correlations scored *higher* than showing all seven (0.8218 vs
0.8047), and `missing_reference_count` -- a field named for exactly this --
reported 0 in every case.

That matters most for HSQC. A quaternary carbon legitimately has no one-bond
correlation, but a **protonated** carbon with none is evidence against the
structure, and with an observed-peak denominator that evidence is unreachable.
It matters more still because `candidate.py:101` feeds this score into candidate
comparison at weight 0.14, multiplied by a per-class prior that reaches **1.50
for carbohydrates** -- the class where 2D is closest to mandatory.

What this module pins is the expectation side:

* expected one-bond correlations come from the STRUCTURE, via the predictor's
  per-atom `attached_h` and `atom_index`;
* **symmetry-equivalent atoms collapse to one expected correlation.** Ibuprofen
  has ten protonated carbons but its two isopropyl methyls, and each aromatic
  pair, are equivalent -- a real HSQC shows about seven cross peaks, not ten.
  Counting atoms rather than distinct environments would make the denominator
  systematically too large and every real spectrum look incomplete, which is the
  same "allocation, not measurement" error the 1D integration apportionment had;
* quaternary carbons are **excluded from the denominator**, not counted as
  misses. Their absence is expected, and scoring them as failures would penalise
  every correct structure.
"""

from __future__ import annotations

import pytest

from nmrcheck.nmr2d_expected import expected_hsqc_correlations

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
ETHANOL = "CCO"
BENZENE = "c1ccccc1"


class TestExpectationsComeFromTheStructure:
    def test_a_protonated_carbon_predicts_a_correlation(self) -> None:
        expected = expected_hsqc_correlations(ETHANOL)
        assert expected, "ethanol predicts no HSQC correlations at all"
        # CH3 and CH2 are distinct; the OH proton is not carbon-bound.
        assert len(expected) == 2, f"expected CH3 + CH2, got {expected}"

    def test_quaternary_carbons_are_not_expected_and_not_misses(self) -> None:
        """Their absence is correct, so they must not enter the denominator."""
        expected = expected_hsqc_correlations(IBUPROFEN)
        # ibuprofen's COOH carbon and both substituted ring carbons have no H
        assert all(c.attached_h > 0 for c in expected), (
            "a carbon with no attached hydrogen was listed as an expected correlation"
        )

    def test_symmetry_equivalent_atoms_collapse(self) -> None:
        """Ten protonated carbons, ~seven distinct environments.

        The two isopropyl methyls are equivalent, and so is each aromatic CH
        pair. Counting atoms would inflate the denominator by three and make a
        complete spectrum look 70 % covered.
        """
        expected = expected_hsqc_correlations(IBUPROFEN)
        assert 6 <= len(expected) <= 8, (
            f"expected ~7 distinct environments for ibuprofen, got {len(expected)}: "
            f"{[(round(c.proton_ppm, 2), round(c.carbon_ppm, 1)) for c in expected]}"
        )

    def test_benzene_is_one_environment_not_six(self) -> None:
        expected = expected_hsqc_correlations(BENZENE)
        assert len(expected) == 1, (
            f"benzene's six equivalent CH should collapse to one, got {len(expected)}"
        )

    def test_each_expectation_carries_both_shifts(self) -> None:
        """A correlation is a PAIR. One shift is not a 2D expectation."""
        for c in expected_hsqc_correlations(IBUPROFEN):
            assert c.proton_ppm is not None and c.carbon_ppm is not None
            assert c.attached_h >= 1


class TestTheDenominatorNoLongerDependsOnWhatWasFound:
    """The C1 defect, asserted directly."""

    def test_expectations_do_not_change_with_the_observation(self) -> None:
        """Same structure, same expectations — the spectrum cannot move them."""
        a = expected_hsqc_correlations(IBUPROFEN)
        b = expected_hsqc_correlations(IBUPROFEN)
        assert len(a) == len(b)
        assert [(round(c.proton_ppm, 3), round(c.carbon_ppm, 3)) for c in a] == [
            (round(c.proton_ppm, 3), round(c.carbon_ppm, 3)) for c in b
        ]

    def test_an_unparseable_structure_yields_nothing_rather_than_guessing(self) -> None:
        """No structure means no expectation, not an empty-but-confident one.

        The caller must be able to tell "nothing expected because there is no
        structure" from "nothing expected because the structure has no CH".
        """
        assert expected_hsqc_correlations("not a smiles") == []
        assert expected_hsqc_correlations(None) == []

    def test_a_structure_with_no_ch_is_distinguishable_from_a_failure(self) -> None:
        """CCl4 has carbons and no C-H: legitimately zero expected correlations."""
        assert expected_hsqc_correlations("ClC(Cl)(Cl)Cl") == []


class TestCoverageIsReportable:
    """What C4 exists to make possible."""

    @pytest.mark.parametrize(
        ("observed_pairs", "want_found", "want_missing"),
        [
            ([(0.95, 14.0), (1.55, 35.0)], 2, None),   # partial
            ([], 0, None),                              # nothing observed
        ],
    )
    def test_found_and_missing_are_both_computable(
        self, observed_pairs, want_found, want_missing
    ) -> None:
        from nmrcheck.nmr2d_expected import match_expected_correlations

        expected = expected_hsqc_correlations(IBUPROFEN)
        result = match_expected_correlations(
            expected, observed_pairs, proton_tolerance_ppm=0.3, carbon_tolerance_ppm=4.0
        )
        assert result.expected_count == len(expected)
        assert result.matched_count == want_found
        assert result.missing_count == len(expected) - want_found
        assert result.expected_count > 0, "the denominator must not be the observed count"

    def test_missing_count_is_nonzero_when_correlations_are_absent(self) -> None:
        """The C1 headline: this reported 0 while six of seven were missing."""
        from nmrcheck.nmr2d_expected import match_expected_correlations

        expected = expected_hsqc_correlations(IBUPROFEN)
        result = match_expected_correlations(
            expected, [(7.20, 129.0)], proton_tolerance_ppm=0.3, carbon_tolerance_ppm=4.0
        )
        assert result.missing_count >= 5, (
            f"only {result.missing_count} missing out of {result.expected_count} "
            "expected when a single correlation was observed"
        )

    def test_coverage_falls_as_correlations_go_missing(self) -> None:
        """Monotonicity — the property C1 measured as violated (0.8218 > 0.8047)."""
        from nmrcheck.nmr2d_expected import match_expected_correlations

        expected = expected_hsqc_correlations(IBUPROFEN)
        all_pairs = [(c.proton_ppm, c.carbon_ppm) for c in expected]
        full = match_expected_correlations(
            expected, all_pairs, proton_tolerance_ppm=0.3, carbon_tolerance_ppm=4.0
        )
        half = match_expected_correlations(
            expected, all_pairs[:2], proton_tolerance_ppm=0.3, carbon_tolerance_ppm=4.0
        )
        assert full.coverage > half.coverage, (
            f"coverage did not fall when correlations were withheld: "
            f"{full.coverage} vs {half.coverage}"
        )
        assert full.coverage == pytest.approx(1.0)
