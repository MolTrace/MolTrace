"""Unit tests for the new peak_categorization module."""

from __future__ import annotations

from nmrcheck.chemistry import structure_summary_from_smiles
from nmrcheck.models import PredictedNMRPeak, StructureSummary
from nmrcheck.peak_categorization import (
    build_impurity_candidates,
    build_labile_hydrogen_summary,
    build_peak_category_summary,
    build_predicted_vs_observed,
    build_proton_inventory,
    categorize_peak,
    enrich_peaks,
)


def _structure(labile: int = 0, total: int = 6) -> StructureSummary:
    # Real-but-minimal structure summary for ethanol-style values.
    return StructureSummary(
        smiles="CCO",
        formula="C2H6O",
        molecular_weight=46.0,
        total_hydrogens=total,
        labile_hydrogens=labile,
        non_labile_hydrogens=max(0, total - labile),
        aromatic_protons=0,
        aliphatic_protons=max(0, total - labile),
        aromatic_atom_count=0,
    )


class TestCategorizePeak:
    def test_aromatic_window_labelled_aromatic_alkene(self) -> None:
        result = categorize_peak(nucleus="1H", shift_ppm=7.25, multiplicity="m", solvent=None)
        assert result["category"] == "aromatic_alkene"
        assert "6–9 ppm" in result["category_reason"]
        assert result["labile_hint"] is False

    def test_aliphatic_window_labelled_aliphatic(self) -> None:
        result = categorize_peak(nucleus="1H", shift_ppm=1.25, multiplicity="t", solvent=None)
        assert result["category"] == "aliphatic"
        assert result["labile_hint"] is False

    def test_broad_high_field_singlet_flagged_labile(self) -> None:
        result = categorize_peak(
            nucleus="1H",
            shift_ppm=11.5,
            multiplicity="br s",
            solvent=None,
            structure=_structure(labile=1),
        )
        assert result["labile_hint"] is True
        # High-field broad signal overrides the carboxylic-acid label.
        assert result["category"] == "labile_OH_NH_SH"
        assert result["category_reason"]

    def test_solvent_match_overrides_chemical_region(self) -> None:
        # CDCl3 residual H at ~7.26 ppm should win over the aromatic region label.
        result = categorize_peak(nucleus="1H", shift_ppm=7.26, multiplicity="s", solvent="CDCl3")
        assert result["category"] == "solvent"
        assert result["solvent_hit"] is not None
        assert result["category_reason"].startswith("Falls inside a known residual-solvent")

    def test_carbon13_aromatic_window(self) -> None:
        # 140 ppm is in the aromatic/alkene window but not in the embedded
        # 13C impurity library (128 ppm hits benzene CH, 150 hits pyridine).
        result = categorize_peak(nucleus="13C", shift_ppm=140.0, multiplicity=None, solvent=None)
        assert result["category"] == "aromatic_alkene"
        assert "110–160 ppm" in result["category_reason"]

    def test_carbon13_carbonyl_window(self) -> None:
        # 200 ppm is in the ketone/aldehyde window without an impurity match.
        result = categorize_peak(nucleus="13C", shift_ppm=200.0, multiplicity=None, solvent=None)
        assert result["category"] == "carbonyl"


class TestEnrichPeaks:
    def test_returns_new_dicts_with_extra_keys(self) -> None:
        peaks = [
            {"shift_ppm": 7.25, "multiplicity": "m", "integration_h": 5.0, "j_values_hz": []},
            {"shift_ppm": 1.25, "multiplicity": "t", "integration_h": 3.0, "j_values_hz": [7.0]},
        ]
        enriched = enrich_peaks(peaks=peaks, nucleus="1H", solvent="CDCl3")
        assert len(enriched) == 2
        # Original keys preserved
        assert enriched[0]["shift_ppm"] == 7.25
        assert enriched[0]["integration_h"] == 5.0
        # New keys present
        assert enriched[0]["category"] in {"aromatic_alkene", "solvent"}
        assert "chemical_region" in enriched[0]
        assert "labile_hint" in enriched[0]
        assert "category_reason" in enriched[0]

    def test_skips_peaks_without_numeric_shift(self) -> None:
        peaks = [{"shift_ppm": "junk", "multiplicity": "s", "integration_h": 1.0}]
        enriched = enrich_peaks(peaks=peaks, nucleus="1H", solvent=None)
        assert enriched[0]["shift_ppm"] == "junk"
        assert "category" not in enriched[0]


class TestSummaries:
    def test_peak_category_summary_counts_per_category(self) -> None:
        peaks = [
            {"category": "aromatic_alkene"},
            {"category": "aromatic_alkene"},
            {"category": "aliphatic"},
        ]
        summary = build_peak_category_summary(peaks)
        assert summary == {"aromatic_alkene": 2, "aliphatic": 1}

    def test_impurity_candidates_from_peaks(self) -> None:
        peaks = [
            {
                "shift_ppm": 1.55,
                "integration_h": 0.3,
                "impurity_match": {
                    "label": "water (CDCl3)",
                    "expected_ppm": 1.56,
                    "observed_ppm": 1.55,
                    "delta_ppm": 0.01,
                    "kind": "water",
                },
            },
            {"shift_ppm": 7.25, "integration_h": 5.0, "impurity_match": None},
        ]
        candidates = build_impurity_candidates(peaks=peaks)
        assert len(candidates) == 1
        assert candidates[0]["shift_ppm"] == 1.55
        assert candidates[0]["library_match"]["label"] == "water (CDCl3)"

    def test_impurity_candidates_uses_metadata_when_present(self) -> None:
        metadata = [{"shift_ppm": 0.1, "integration_h": 0.2, "score": 5, "reason": "trace"}]
        candidates = build_impurity_candidates(peaks=[], metadata_candidates=metadata)
        assert candidates == [
            {
                "shift_ppm": 0.1,
                "integration_h": 0.2,
                "reason": "trace",
                "score": 5,
                "library_match": None,
            }
        ]

    def test_labile_hydrogen_summary_notes_d2o_exchange(self) -> None:
        peaks = [
            {"shift_ppm": 1.5, "labile_hint": False, "integration_h": 3.0},
        ]
        summary = build_labile_hydrogen_summary(
            peaks=peaks,
            structure=_structure(labile=1),
            solvent="D2O",
        )
        assert summary["expected_labile_h"] == 1
        assert summary["observed_labile_candidates"] == []
        assert any("D2O" in note for note in summary["notes"])
        assert summary["confidence"] == 0.0

    def test_labile_hydrogen_summary_with_observed_candidate(self) -> None:
        peaks = [
            {
                "shift_ppm": 11.0,
                "labile_hint": True,
                "multiplicity": "br s",
                "integration_h": 1.0,
                "category_reason": "broad/downfield",
            }
        ]
        summary = build_labile_hydrogen_summary(
            peaks=peaks,
            structure=_structure(labile=1),
            solvent="CDCl3",
        )
        assert len(summary["observed_labile_candidates"]) == 1
        assert summary["confidence"] == 1.0


class TestPredictedVsObserved:
    def test_greedy_match_within_tolerance(self) -> None:
        predicted = [
            PredictedNMRPeak(nucleus="1H", shift_ppm=7.25, uncertainty_ppm=0.1, atom_index=1, attached_h=1, carbon_type=None, environment="aromatic"),
            PredictedNMRPeak(nucleus="1H", shift_ppm=1.30, uncertainty_ppm=0.05, atom_index=2, attached_h=3, carbon_type=None, environment="methyl"),
        ]
        observed = [
            {"shift_ppm": 7.26, "multiplicity": "m", "integration_h": 5.0},
            {"shift_ppm": 1.25, "multiplicity": "t", "integration_h": 3.0},
        ]
        rows = build_predicted_vs_observed(
            predicted_peaks=predicted,
            observed_peaks=observed,
            nucleus="1H",
        )
        matched = [r for r in rows if r["status"] == "matched"]
        assert len(matched) == 2
        # Check that nearest pairing wins
        aromatic = next(r for r in matched if r["predicted_environment"] == "aromatic")
        assert abs(aromatic["delta_ppm"] - 0.01) < 1e-6

    def test_unmatched_predicted_flagged(self) -> None:
        predicted = [
            PredictedNMRPeak(nucleus="1H", shift_ppm=9.5, uncertainty_ppm=0.1, atom_index=1, attached_h=1, carbon_type=None, environment="aldehyde"),
        ]
        observed = [{"shift_ppm": 1.25, "multiplicity": "t", "integration_h": 3.0}]
        rows = build_predicted_vs_observed(
            predicted_peaks=predicted,
            observed_peaks=observed,
            nucleus="1H",
        )
        statuses = sorted(r["status"] for r in rows)
        assert statuses == ["unmatched_observed", "unmatched_predicted"]

    def test_filters_wrong_nucleus(self) -> None:
        predicted = [
            PredictedNMRPeak(nucleus="13C", shift_ppm=128.0, uncertainty_ppm=2.0, atom_index=1, attached_h=None, carbon_type=None, environment=None),
        ]
        observed = [{"shift_ppm": 7.25, "multiplicity": "m", "integration_h": 5.0}]
        rows = build_predicted_vs_observed(
            predicted_peaks=predicted,
            observed_peaks=observed,
            nucleus="1H",
        )
        # Only the observed peak should show up because the predicted is 13C.
        assert len(rows) == 1
        assert rows[0]["status"] == "unmatched_observed"


# ──────────────────────────────────────────────────────────────────────────────
# Per-element labile-H subset detection + proton inventory aggregator
# ──────────────────────────────────────────────────────────────────────────────


class TestPerElementLabileSubset:
    """The labile-H summary must declare the EXACT element subset present in
    the SMILES (OH only / OH+NH / OH+NH+SH / NH-only / …) rather than the
    legacy generic ``(OH/NH/SH)`` placeholder."""

    def test_ethanol_emits_oh_only_subset(self) -> None:
        # Ethanol: one OH, no NH, no SH.
        structure = structure_summary_from_smiles("CCO")
        assert structure.oh_hydrogen_count == 1
        assert structure.nh_hydrogen_count == 0
        assert structure.sh_hydrogen_count == 0

        summary = build_labile_hydrogen_summary(
            peaks=[],
            structure=structure,
            solvent="CDCl3",
        )
        assert summary["labile_subset"] == "OH"
        assert summary["expected_oh_h"] == 1
        assert summary["expected_nh_h"] == 0
        assert summary["expected_sh_h"] == 0
        joined_notes = " ".join(summary["notes"])
        assert "(OH)" in joined_notes
        assert "(OH/NH" not in joined_notes  # must NOT be the generic placeholder
        assert "1 OH" in joined_notes

    def test_aniline_emits_nh_only_subset(self) -> None:
        # Aniline: 2 NH (primary amine), 0 OH, 0 SH.
        structure = structure_summary_from_smiles("Nc1ccccc1")
        assert structure.oh_hydrogen_count == 0
        assert structure.nh_hydrogen_count == 2
        assert structure.sh_hydrogen_count == 0

        summary = build_labile_hydrogen_summary(
            peaks=[],
            structure=structure,
            solvent="CDCl3",
        )
        assert summary["labile_subset"] == "NH"
        joined_notes = " ".join(summary["notes"])
        assert "(NH)" in joined_notes
        assert "2 NH" in joined_notes

    def test_serine_emits_oh_and_nh_subset(self) -> None:
        # L-Serine: 1 NH (NH2 → 2), 1 sidechain OH, 1 carboxylic-acid OH = 2 OH.
        # Total: 2 OH + 2 NH; zero SH.
        structure = structure_summary_from_smiles("OC[C@@H](N)C(=O)O")
        assert structure.oh_hydrogen_count == 2
        assert structure.nh_hydrogen_count == 2
        assert structure.sh_hydrogen_count == 0

        summary = build_labile_hydrogen_summary(
            peaks=[],
            structure=structure,
            solvent="CDCl3",
        )
        assert summary["labile_subset"] == "OH/NH"
        joined_notes = " ".join(summary["notes"])
        assert "(OH/NH)" in joined_notes
        assert "(OH/NH/SH)" not in joined_notes

    def test_cysteine_emits_oh_nh_sh_subset(self) -> None:
        # L-Cysteine: 1 OH (carboxyl COOH), 2 NH (NH2), 1 SH (thiol).
        # The carbonyl =O carries no H — only the hydroxyl O of the COOH does.
        structure = structure_summary_from_smiles("SC[C@@H](N)C(=O)O")
        assert structure.oh_hydrogen_count == 1
        assert structure.nh_hydrogen_count == 2
        assert structure.sh_hydrogen_count == 1

        summary = build_labile_hydrogen_summary(
            peaks=[],
            structure=structure,
            solvent="CDCl3",
        )
        assert summary["labile_subset"] == "OH/NH/SH"
        joined_notes = " ".join(summary["notes"])
        assert "(OH/NH/SH)" in joined_notes
        assert "1 SH" in joined_notes

    def test_thiophenol_emits_sh_only_subset(self) -> None:
        # Thiophenol: 1 SH, no OH or NH.
        structure = structure_summary_from_smiles("Sc1ccccc1")
        assert structure.oh_hydrogen_count == 0
        assert structure.nh_hydrogen_count == 0
        assert structure.sh_hydrogen_count == 1

        summary = build_labile_hydrogen_summary(
            peaks=[],
            structure=structure,
            solvent="CDCl3",
        )
        assert summary["labile_subset"] == "SH"
        joined_notes = " ".join(summary["notes"])
        assert "(SH)" in joined_notes
        assert "(OH" not in joined_notes
        assert "(NH" not in joined_notes

    def test_per_element_sums_to_total_labile(self) -> None:
        # The three per-element counts must always sum to total labile_hydrogens
        # for any neutral structure (O+N+S H atoms).
        for smiles in ("CCO", "Nc1ccccc1", "Sc1ccccc1", "OC[C@@H](N)C(=O)O", "SC[C@@H](N)C(=O)O"):
            structure = structure_summary_from_smiles(smiles)
            element_total = (
                structure.oh_hydrogen_count
                + structure.nh_hydrogen_count
                + structure.sh_hydrogen_count
            )
            assert element_total == structure.labile_hydrogens, (
                f"{smiles}: OH+NH+SH ({element_total}) != labile_hydrogens "
                f"({structure.labile_hydrogens})"
            )


class TestProtonInventoryAggregator:
    """`build_proton_inventory` aggregates observed-vs-expected proton counts
    by chemical class and flags meaningful integration deltas."""

    def test_empty_dict_for_carbon13_runs(self) -> None:
        result = build_proton_inventory(peaks=[], structure=None, nucleus="13C")
        assert result == {}

    def test_observed_buckets_from_categorised_peaks(self) -> None:
        peaks = [
            {"category": "aromatic_alkene", "integration_h": 5.0},
            {"category": "aliphatic", "integration_h": 3.0},
            {"category": "aliphatic", "integration_h": 2.0},
            {"category": "labile_OH_NH_SH", "integration_h": 1.0},
            # Solvent + impurity peaks excluded from the inventory totals.
            {"category": "solvent", "integration_h": 1.0},
            {"category": "impurity", "integration_h": 0.5},
        ]
        result = build_proton_inventory(peaks=peaks, structure=None, nucleus="1H")
        observed = result["observed"]
        assert observed["aromatic"] == 5.0
        assert observed["aliphatic"] == 5.0
        assert observed["labile"] == 1.0
        assert observed["total"] == 11.0
        assert observed["non_labile"] == 10.0
        # No structure → no expected/deltas block.
        assert result["expected"] == {}
        assert result["deltas"] == {}

    def test_expected_block_from_smiles_has_labile_subset(self) -> None:
        # L-Serine: structural expectation drives the expected block.
        structure = structure_summary_from_smiles("OC[C@@H](N)C(=O)O")
        result = build_proton_inventory(peaks=[], structure=structure, nucleus="1H")
        expected = result["expected"]
        assert expected["aromatic"] == 0
        assert expected["aliphatic"] == 3  # CH2 + CH
        assert expected["labile"] == 4  # 2 OH + 2 NH
        assert expected["oh"] == 2
        assert expected["nh"] == 2
        assert expected["sh"] == 0
        assert expected["labile_subset"] == "OH/NH"

    def test_warning_when_observed_exceeds_expected_aromatic(self) -> None:
        # Toluene: structure has 5 aromatic H + 3 aliphatic CH3 H. If observed
        # aromatic integration is 7 H, that's +2 H over expectation → warning.
        structure = structure_summary_from_smiles("Cc1ccccc1")
        peaks = [
            {"category": "aromatic_alkene", "integration_h": 7.0},
            {"category": "aliphatic", "integration_h": 3.0},
        ]
        result = build_proton_inventory(peaks=peaks, structure=structure, nucleus="1H")
        assert result["expected"]["aromatic"] == 5
        assert result["deltas"]["aromatic"] == 2.0
        assert any(
            "aromatic" in warning and "above" in warning for warning in result["warnings"]
        ), result["warnings"]

    def test_warning_when_labile_observed_below_expected(self) -> None:
        # Ethanol in CDCl3: expect 1 OH. If observed labile = 0, we should warn
        # the user that the OH integration might be suppressed.
        structure = structure_summary_from_smiles("CCO")
        peaks = [
            {"category": "aliphatic", "integration_h": 5.0},
        ]
        result = build_proton_inventory(peaks=peaks, structure=structure, nucleus="1H")
        assert result["deltas"]["labile"] == -1.0
        assert any(
            "labile" in warning and "below" in warning for warning in result["warnings"]
        ), result["warnings"]


# ──────────────────────────────────────────────────────────────────────────────
# Structure-aware anomeric ↔ olefinic disambiguation (the 4.4–6.0 ppm window)
#
# Real-world bug report (Tobramycin SMILES): peaks in the 4.4–6 ppm range
# were labelled "olefinic" even though tobramycin is fully saturated. The
# categoriser now consults the SMILES via ``StructureSummary.{olefinic_proton_count,
# anomeric_proton_count}`` to pick anomeric / olefinic / ambiguous.
# ──────────────────────────────────────────────────────────────────────────────


# Tobramycin: three aminosugar rings, saturated — anomeric H present, NO
# olefinic. This is the exact SMILES the user pasted in the bug report.
TOBRAMYCIN_SMILES = (
    "O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])"
    "[C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)"
    "[C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N"
)


class TestOlefinicAnomericCounts:
    """Structural detection that powers the 1H categoriser."""

    def test_tobramycin_has_anomeric_protons_and_zero_olefinic(self) -> None:
        # User's bug-report SMILES — tobramycin must register as a
        # carbohydrate-style structure with anomeric protons and no olefinic.
        structure = structure_summary_from_smiles(TOBRAMYCIN_SMILES)
        assert structure.olefinic_proton_count == 0, (
            f"Tobramycin should have zero olefinic protons; got {structure.olefinic_proton_count}"
        )
        assert structure.anomeric_proton_count > 0, (
            "Tobramycin's three aminosugar rings should produce >0 anomeric protons"
        )

    def test_styrene_has_olefinic_protons_and_zero_anomeric(self) -> None:
        # Styrene: vinyl-aromatic, the canonical olefinic case.
        structure = structure_summary_from_smiles("C=Cc1ccccc1")
        assert structure.olefinic_proton_count == 3  # =CH-CH2 (vinyl)
        assert structure.anomeric_proton_count == 0

    def test_simple_ether_is_not_anomeric(self) -> None:
        # Diethyl ether (CH3-CH2-O-CH2-CH3): each CH2 has one O neighbour, not
        # two — must NOT count as anomeric. False positives here would
        # mislabel every ether-bearing molecule.
        structure = structure_summary_from_smiles("CCOCC")
        assert structure.anomeric_proton_count == 0
        assert structure.olefinic_proton_count == 0

    def test_glucose_anomeric_count_is_one(self) -> None:
        # β-D-glucopyranose: exactly one anomeric carbon at C-1 (two O bonds:
        # ring O + anomeric OH), bearing one H.
        structure = structure_summary_from_smiles("OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O")
        assert structure.anomeric_proton_count == 1
        assert structure.olefinic_proton_count == 0

    def test_aromatic_protons_are_not_counted_as_olefinic(self) -> None:
        # Benzene: 6 aromatic H, 0 olefinic — aromatic doubles must be
        # excluded by the olefinic counter.
        structure = structure_summary_from_smiles("c1ccccc1")
        assert structure.olefinic_proton_count == 0
        assert structure.aromatic_protons == 6


class TestProtonCategoriserUsesStructure:
    """The 4.4–6.0 ppm window picks anomeric / olefinic / ambiguous based on
    what the SMILES carries."""

    def test_tobramycin_4_to_6_ppm_peak_is_anomeric_not_olefinic(self) -> None:
        # The exact regression for the user's bug report.
        structure = structure_summary_from_smiles(TOBRAMYCIN_SMILES)
        result = categorize_peak(
            nucleus="1H",
            shift_ppm=5.10,  # mid-range anomeric region
            multiplicity="d",
            solvent="D2O",
            structure=structure,
        )
        assert result["category"] == "anomeric"
        assert "olefinic" not in result["category_reason"].lower() or "no olefinic" in result["category_reason"].lower()
        assert "anomeric" in result["category_reason"].lower()

    def test_styrene_4_to_6_ppm_peak_is_olefinic(self) -> None:
        structure = structure_summary_from_smiles("C=Cc1ccccc1")
        result = categorize_peak(
            nucleus="1H",
            shift_ppm=5.20,
            multiplicity="d",
            solvent="CDCl3",
            structure=structure,
        )
        assert result["category"] == "olefinic"

    def test_no_structure_falls_back_to_anomeric_or_olefinic(self) -> None:
        # Without SMILES we cannot disambiguate — the category should be the
        # ambiguous bucket, NOT the legacy "olefinic" default which was
        # misleading for ~every carbohydrate sample.
        result = categorize_peak(
            nucleus="1H",
            shift_ppm=5.10,
            multiplicity="d",
            solvent="CDCl3",
            structure=None,
        )
        assert result["category"] == "anomeric_or_olefinic"
        assert "No SMILES" in result["category_reason"]

    def test_structure_with_both_motifs_returns_ambiguous(self) -> None:
        # An allyl glucoside: has anomeric H (sugar C1) AND olefinic H (CH2=CH-CH2-O-).
        # Without 2D NMR the categoriser cannot pick — falls back to ambiguous.
        structure = structure_summary_from_smiles(
            "C=CCO[C@H]1O[C@H](CO)[C@@H](O)[C@H](O)[C@@H]1O"
        )
        assert structure.olefinic_proton_count > 0
        assert structure.anomeric_proton_count > 0
        # 4.65 ppm avoids the nitromethane CH3 / water residual / methanol
        # impurity windows so we exercise the structure-aware classifier
        # rather than the impurity short-circuit.
        result = categorize_peak(
            nucleus="1H",
            shift_ppm=4.65,
            multiplicity="d",
            solvent="CDCl3",
            structure=structure,
        )
        assert result["category"] == "anomeric_or_olefinic"

    def test_interior_anomeric_window_resolves_to_anomeric_for_carbohydrate(
        self,
    ) -> None:
        # Verifies the structure-aware branch fires across the interior of the
        # 4.4–6.0 ppm window. The test shifts (5.10, 5.30, 5.65) all sit
        # ABOVE the D2O HOD residual window (4.55–5.05) and outside the
        # curated impurity library, so neither short-circuit fires and the
        # categoriser must consult the SMILES.
        structure = structure_summary_from_smiles(TOBRAMYCIN_SMILES)
        for shift in (5.10, 5.30, 5.65):
            result = categorize_peak(
                nucleus="1H",
                shift_ppm=shift,
                multiplicity="d",
                solvent="D2O",
                structure=structure,
            )
            assert result["category"] == "anomeric", f"shift={shift} → {result}"

    def test_solvent_hit_preempts_anomeric_assignment_d2o_hod(self) -> None:
        # In D2O the HOD residual spans 4.55–5.05 ppm, so a 4.80 ppm peak is
        # the water residual regardless of what the SMILES says. The solvent
        # short-circuit (existing behavior) must continue to win — preserving
        # this is important so the categoriser doesn't mislabel water as
        # an anomeric proton.
        structure = structure_summary_from_smiles(TOBRAMYCIN_SMILES)
        result = categorize_peak(
            nucleus="1H",
            shift_ppm=4.80,
            multiplicity="br s",
            solvent="D2O",
            structure=structure,
        )
        assert result["category"] == "solvent"


class TestAminoglycosideCarbohydrateRefinement:
    """Tobramycin-class aminoglycosides are saturated pseudo-trisaccharides.

    Their 1H NMR text can contain many signals in the broad anomeric/sugar
    region, but only two should be treated as anomeric for these derivatives;
    the rest belong to the sugar-backbone envelope unless solvent/impurity
    matching has already excluded them.
    """

    def test_tobramycin_enrichment_caps_anomeric_and_labels_sugar_backbone(self) -> None:
        structure = structure_summary_from_smiles(TOBRAMYCIN_SMILES)
        peaks = [
            {
                "shift_ppm": 5.18,
                "multiplicity": "d",
                "integration_h": 1.0,
                "pick_source": "nmr_text",
                "inventory_basis": "nmr_text",
            },
            {
                "shift_ppm": 4.96,
                "multiplicity": "d",
                "integration_h": 1.0,
                "pick_source": "nmr_text",
                "inventory_basis": "nmr_text",
            },
            {
                "shift_ppm": 4.58,
                "multiplicity": "m",
                "integration_h": 1.0,
                "pick_source": "nmr_text",
                "inventory_basis": "nmr_text",
            },
            {
                "shift_ppm": 4.12,
                "multiplicity": "m",
                "integration_h": 2.0,
                "pick_source": "nmr_text",
                "inventory_basis": "nmr_text",
            },
            {
                "shift_ppm": 3.21,
                "multiplicity": "m",
                "integration_h": 4.0,
                "pick_source": "nmr_text",
                "inventory_basis": "nmr_text",
            },
            {
                "shift_ppm": 2.72,
                "multiplicity": "m",
                "integration_h": 1.0,
                "pick_source": "nmr_text",
                "inventory_basis": "nmr_text",
            },
        ]

        enriched = enrich_peaks(
            peaks=peaks,
            nucleus="1H",
            solvent=None,
            structure=structure,
        )

        assert sum(peak["category"] == "anomeric" for peak in enriched) == 2
        by_shift = {round(float(peak["shift_ppm"]), 2): peak for peak in enriched}
        assert by_shift[5.18]["category"] == "anomeric"
        assert by_shift[4.96]["category"] == "anomeric"
        assert by_shift[4.58]["category"] == "carbohydrate_sugar"
        assert by_shift[4.12]["category"] == "carbohydrate_sugar"
        assert by_shift[3.21]["category"] == "carbohydrate_sugar"
        assert by_shift[2.72]["category"] == "nitrogen_adjacent"
        assert "Aminoglycoside" in by_shift[4.58]["category_reason"]

    def test_proton_inventory_includes_sugar_backbone_and_two_anomeric_expectation(
        self,
    ) -> None:
        structure = structure_summary_from_smiles(TOBRAMYCIN_SMILES)
        peaks = [
            {"category": "anomeric", "integration_h": 2.0},
            {"category": "carbohydrate_sugar", "integration_h": 8.0},
            {"category": "aliphatic", "integration_h": 1.0},
        ]

        result = build_proton_inventory(peaks=peaks, structure=structure, nucleus="1H")

        assert result["observed"]["anomeric_or_olefinic"] == 2.0
        assert result["observed"]["carbohydrate_sugar"] == 8.0
        # The aliphatic inventory includes sugar-backbone CH/CH2 protons so the
        # observed-vs-expected non-labile total still compares against structure.
        assert result["observed"]["aliphatic"] == 9.0
        assert result["expected"]["anomeric_or_olefinic"] == 2
        assert result["deltas"]["anomeric_or_olefinic"] == 0.0


class TestProtonInventoryBucketRename:
    """Inventory bucket key was renamed to ``anomeric_or_olefinic`` so the
    label matches what's now possible in the data."""

    def test_inventory_bucket_uses_new_name(self) -> None:
        peaks = [
            {"category": "anomeric", "integration_h": 1.0},
            {"category": "olefinic", "integration_h": 2.0},
            {"category": "anomeric_or_olefinic", "integration_h": 0.5},
        ]
        result = build_proton_inventory(peaks=peaks, structure=None, nucleus="1H")
        assert result["observed"]["anomeric_or_olefinic"] == 3.5
        assert "olefinic_vinylic" not in result["observed"]  # legacy key is gone
