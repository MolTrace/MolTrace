import json
import math
import random
from pathlib import Path

import pytest

from nmrcheck.carbon13 import (
    Carbon13ParseError,
    analyze_carbon13_text,
    carbon13_peaks_from_shift_values,
    parse_carbon13_processed_spectrum,
    parse_carbon13_table,
    parse_carbon13_text,
    refine_carbon13_peaks_with_context,
    refine_carbon13_peaks_with_text_guidance,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "carbon13"


def _gaussian(x: float, center: float, width: float, amplitude: float) -> float:
    exponent = -((x - center) ** 2) / (2 * width**2)
    return amplitude * (2.718281828459045 ** exponent)


def test_ethanol_13c_text_analysis_matches_carbon_count() -> None:
    expected = json.loads((FIXTURE_DIR / "ethanol_expected.json").read_text())
    report = analyze_carbon13_text(
        "CCO",
        (FIXTURE_DIR / "ethanol_13c.txt").read_text(),
        solvent="CDCl3",
        sample_id="ethanol",
    )
    assert report.expected_carbon_atoms == expected["expected_carbon_atoms"]
    assert report.observed_carbon_signals == expected["observed_carbon_signals"]
    assert report.label == expected["label"]


def test_ethanol_13c_csv_flags_cdcl3_solvent_peak() -> None:
    preview = parse_carbon13_table(
        "ethanol_13c.csv",
        (FIXTURE_DIR / "ethanol_13c.csv").read_bytes(),
        solvent="CDCl3",
    )
    assert preview.observed_signal_count == 3
    assert any(peak.is_likely_solvent for peak in preview.peaks)


def test_carbon13_carbon_type_aliases_include_dept_apt_ambiguous_labels() -> None:
    preview = parse_carbon13_table(
        "type_aliases.csv",
        b"shift_ppm,carbon_type\n58.3,attached_h2\n18.2,CH/CH3\n101.2,CH2/C\n145.0,attached_h0\n",
        solvent="CDCl3",
    )

    assert [peak.carbon_type for peak in preview.peaks] == ["CH2", "CH_OR_CH3", "CH2_OR_C", "C"]


def test_glucose_like_13c_regions_include_anomeric_and_oxygenated() -> None:
    expected = json.loads((FIXTURE_DIR / "glucose_expected.json").read_text())
    peaks = parse_carbon13_text((FIXTURE_DIR / "glucose_13c.txt").read_text(), solvent="D2O")
    regions = {peak.region for peak in peaks}
    for region in expected["expected_regions"]:
        assert region in regions


def test_aminoglycoside_like_13c_detects_multiple_on_bearing_carbons() -> None:
    report = analyze_carbon13_text(
        "O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])[C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)[C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N",
        (FIXTURE_DIR / "aminoglycoside_like_13c.txt").read_text(),
        solvent="D2O",
    )
    assert any("O/N-bearing" in note for note in report.notes)
    assert any(
        item.region in {"oxygenated carbon", "nitrogen-bearing carbon"}
        for item in report.peaks
    )


def test_invalid_13c_text_rejected_when_it_is_1h_nmr() -> None:
    with pytest.raises(Carbon13ParseError):
        parse_carbon13_text((FIXTURE_DIR / "invalid_13c.txt").read_text(), solvent="CDCl3")


def test_invalid_13c_csv_rejected() -> None:
    with pytest.raises(Carbon13ParseError):
        parse_carbon13_table(
            "invalid_13c.csv",
            (FIXTURE_DIR / "invalid_13c.csv").read_bytes(),
            solvent="CDCl3",
        )


def test_carbon13_text_guidance_filters_detected_candidates_without_fabricating_missing() -> None:
    peaks = carbon13_peaks_from_shift_values(
        [(130.02, 10.0), (77.16, 100.0), (50.0, 2.0), (18.2, 8.0)],
        solvent="CDCl3",
    )

    refined, meta, notes = refine_carbon13_peaks_with_text_guidance(
        peaks,
        carbon13_text="13C NMR (126 MHz, CDCl3) δ 130.0, 40.0, 18.2",
        solvent="CDCl3",
    )

    non_solvent_shifts = [peak.shift_ppm for peak in refined if not peak.is_likely_solvent]
    assert non_solvent_shifts == [130.02, 18.2]
    assert all(abs(peak.shift_ppm - 40.0) > 0.01 for peak in refined)
    assert any(peak.is_likely_solvent for peak in refined)
    assert meta["matched_reference_peak_count"] == 2
    assert meta["missing_reference_peak_count"] == 1
    assert meta["filtered_unmatched_detected_peak_count"] == 1
    assert any("not fabricated" in note for note in notes)


def test_processed_13c_trace_applies_baseline_and_masks_only_for_peak_picking() -> None:
    rows = ["ppm,intensity"]
    for idx in range(601):
        x = 120.0 - idx * 0.2
        baseline = 0.08 + (0.05 if idx % 2 else -0.03)
        solvent = 120.0 if abs(x - 77.0) <= 0.2 else 0.0
        carbon = 12.0 if abs(x - 58.0) <= 0.2 else 0.0
        rows.append(f"{x:.1f},{baseline + solvent + carbon:.6f}")

    preview = parse_carbon13_processed_spectrum(
        "c13_trace.csv",
        ("\n".join(rows) + "\n").encode(),
        solvent="CDCl3",
        mask_solvent_regions=True,
    )

    preprocessing = preview.metadata["display_preprocessing"]
    assert preprocessing["baseline_smoothing"]["applied"] is False
    assert preprocessing["trace_smoothing"]["applied"] is True
    assert preprocessing["trace_smoothing"]["display_only"] is True
    assert preprocessing["display_solvent_masked"] is False
    assert preview.metadata["processed_baseline_correction"]["correction_applied"] is True
    assert (
        preview.metadata["processed_baseline_correction"]["post_baseline_polish"]["baseline_locked_to_zero"]
        is True
    )
    assert preview.metadata["evidence_trace_mode"] == "uploaded_intensity_baseline_corrected"
    assert preview.metadata["display"]["main_trace"] == "display_smoothed_evidence_intensity"
    assert preview.metadata["display_mode"] == "real"
    assert preview.metadata["baseline_lock_visual_only"] is True
    assert "raw_preview_points" not in preview.metadata
    original_state = preview.metadata["original_spectrum_state"]
    assert original_state["preserved"] is True
    assert original_state["processing_stage"] == "as_uploaded"
    assert original_state["preview_points"]
    assert all(not peak.is_likely_solvent for peak in preview.peaks)
    solvent_display = [
        point["intensity"] for point in preview.metadata["preview_points"] if 76.3 <= point["shift_ppm"] <= 77.7
    ]
    analyte_display = [
        point["intensity"] for point in preview.metadata["preview_points"] if 57.0 <= point["shift_ppm"] <= 59.0
    ]
    assert solvent_display
    assert analyte_display
    assert max(solvent_display) > max(analyte_display)


def test_processed_13c_aromatic_region_resolves_on_curved_baseline() -> None:
    rows = ["ppm,intensity"]
    aromatic_centers = [137.2, 131.4, 129.8, 128.5, 126.7, 114.2]
    for idx in range(1601):
        x = 160.0 - idx * 0.05
        baseline = 0.35 + 0.0008 * (x - 130.0) ** 2
        intensity = baseline
        for center in aromatic_centers:
            intensity += _gaussian(x, center, 0.045, 14.0 if center > 120 else 8.5)
        rows.append(f"{x:.2f},{intensity:.8f}")

    preview = parse_carbon13_processed_spectrum(
        "aromatic_c13.csv",
        ("\n".join(rows) + "\n").encode(),
        solvent="CDCl3",
        peak_sensitivity=0.08,
        mask_solvent_regions=True,
    )

    aromatic_peaks = [peak for peak in preview.peaks if 110.0 <= peak.shift_ppm <= 160.0]
    baseline_points = [
        point["intensity"]
        for point in preview.metadata["preview_points"]
        if 145.0 <= point["shift_ppm"] <= 150.0
    ]
    assert len(aromatic_peaks) >= 5
    assert max(baseline_points) - min(baseline_points) > 0.0
    assert preview.metadata["display_preprocessing"]["baseline_smoothing"]["baseline_locked_to_zero"] is False
    assert preview.metadata["display_preprocessing"]["trace_smoothing"]["applied"] is True
    assert preview.metadata["display_preprocessing"]["trace_smoothing"]["aromatic_points_smoothed"] > 0
    assert preview.metadata["processed_baseline_correction"]["correction_applied"] is True
    assert preview.metadata["display_mode"] == "real"


def test_carbon13_processed_spectrum_accepts_text_pair_exports() -> None:
    preview = parse_carbon13_processed_spectrum(
        "carbon13.xy",
        b"170 1\n140 10\n130 6\n120 2\n",
        solvent="CDCl3",
        infer_peaks=False,
    )

    assert preview.source_mode == "processed_trace"
    assert preview.metadata["point_count"] == 4


def test_context_guided_13c_peak_refinement_uses_smiles_and_proton_text() -> None:
    preview = parse_carbon13_table(
        "noisy_ethanol_13c.csv",
        b"shift_ppm,intensity\n140,8\n118,6\n77.0,100\n58.3,95\n42,5\n18.2,80\n9,4\n",
        solvent="CDCl3",
    )

    refined, meta, notes = refine_carbon13_peaks_with_context(
        preview.peaks,
        smiles="CCO",
        proton_nmr_text="¹H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), 1.26 (t, 3H)",
        solvent="CDCl3",
    )

    non_solvent_shifts = [round(peak.shift_ppm, 1) for peak in refined if not peak.is_likely_solvent]
    assert meta["smiles_guidance_used"] is True
    assert meta["proton_nmr_guidance_used"] is True
    assert meta["context_filtered_peak_count"] > 0
    assert non_solvent_shifts == [58.3, 18.2]
    assert any("Context-guided raw ¹³C" in note for note in notes)


def _carbon13_trace_csv(
    peaks: list[tuple[float, float]],
    *,
    noise: float,
    seed: int,
) -> bytes:
    """Synthesize a dense processed ¹³C-spectrum CSV: Gaussian peaks + noise.

    An empty ``peaks`` list yields a pure-noise trace, which the SNR-based
    detector must leave empty rather than inventing carbons.
    """
    rng = random.Random(seed)
    rows = ["ppm,intensity"]
    steps = int(210.0 / 0.025) + 1
    for idx in range(steps):
        x = 210.0 - idx * 0.025
        intensity = rng.gauss(0.0, noise)
        for center, amplitude in peaks:
            intensity += amplitude * math.exp(-((x - center) ** 2) / (2 * 0.06**2))
        rows.append(f"{x:.3f},{intensity:.5f}")
    return ("\n".join(rows) + "\n").encode()


def test_processed_13c_detector_recovers_carbon_count_under_noise() -> None:
    # A dense ¹³C trace synthesized at six known shifts plus realistic noise
    # must be detected back to the same six signals — the SNR threshold neither
    # drops genuine carbons nor adds noise peaks.
    carbons = [
        (165.2, 200.0),
        (140.1, 170.0),
        (128.5, 150.0),
        (72.3, 220.0),
        (55.0, 130.0),
        (21.8, 110.0),
    ]
    preview = parse_carbon13_processed_spectrum(
        "trace.csv",
        _carbon13_trace_csv(carbons, noise=3.0, seed=22),
        solvent=None,
    )
    assert preview.source_mode == "processed_trace"
    assert preview.observed_signal_count == len(carbons)
    detected = sorted(round(peak.shift_ppm, 1) for peak in preview.peaks)
    for center, _amplitude in carbons:
        assert any(abs(center - shift) <= 0.2 for shift in detected)


def test_processed_13c_detector_rejects_pure_noise_without_fabricating_peaks() -> None:
    # A trace with no real signal must not yield invented ¹³C carbons; the
    # processed-spectrum parser raises rather than fabricating a peak list.
    with pytest.raises(Carbon13ParseError):
        parse_carbon13_processed_spectrum(
            "noise.csv",
            _carbon13_trace_csv([], noise=4.0, seed=23),
            solvent=None,
        )
