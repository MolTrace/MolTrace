"""Unit tests for the new peak_categorization module."""

from __future__ import annotations

from nmrcheck.models import PredictedNMRPeak, StructureSummary
from nmrcheck.peak_categorization import (
    build_impurity_candidates,
    build_labile_hydrogen_summary,
    build_peak_category_summary,
    build_predicted_vs_observed,
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
