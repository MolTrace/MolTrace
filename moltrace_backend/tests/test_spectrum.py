import random

from nmrcheck.spectrum import SpectrumParseError
from nmrcheck.models import Peak
from nmrcheck.parser import parse_reference_nmr_text
from nmrcheck.compound_class_priors import diagnostic_regions_for
from nmrcheck.spectrum import _apply_reference_multiplicity, _build_reference_guided_nmr_text, _classify_multiplicity, _downsample_points, _infer_peak_estimates, _round_half_integrations, _structure_guided_peak_estimates, parse_processed_spectrum

TOBRAMYCIN_REFERENCE_TEXT = """'H NMR (500 MHz, D2O) 8 5.23 (d, J = 3.6 Hz, 1H), 5.08 (d, J = 3.9 Hz, 1H), 3.95 (ddd,
J= 10.3, 4.6, 2.6 Hz, 1H), 3.80 (dd, J = 6.6, 3.6 Hz, 2H), 3.68 (tdd, J = 9.2, 5.6, 3.1 Hz,
2H), 3.60 - 3.53 (т, 3H), 3.40 - 3.33 (m, 3H), 3.32 - 3.23 (m, 1H), 3.11 - 2.98 (m, 4H),
2.93 (tdd, J = 11.9,9.7, 4.1 Hz, 3H), 2.83 (dd, J = 13.6, 7.5 Hz, 1H), 2.07 (dt, J = 11.8,
4.5 Hz, 1H), 2.00 (dt, J = 13.0, 4.2 Hz, 1H), 1.71 - 1.60 (m, 1H), 1.27 (q, J = 12.5 Hz,
1H)"""


def _gaussian(x: float, center: float, width: float, amplitude: float) -> float:
    exponent = -((x - center) ** 2) / (2 * (width**2))
    return amplitude * (2.718281828459045 ** exponent)


def _lorentzian(x: float, amplitude: float, center: float, hwhm: float) -> float:
    return amplitude * hwhm * hwhm / ((x - center) ** 2 + hwhm * hwhm)


def _dense_sugar_trace_csv() -> bytes:
    xs = [5.4 - idx * 0.0005 for idx in range(int((5.4 - 1.1) / 0.0005) + 1)]
    peaks = [
        (5.23, 0.004, 9.0),
        (5.08, 0.004, 8.5),
        (4.79, 0.010, 45.0),
        (3.95, 0.004, 8.0),
        (3.80, 0.005, 12.0),
        (3.68, 0.0045, 11.0),
        (3.56, 0.005, 10.5),
        (3.40, 0.005, 10.0),
        (3.31, 0.0045, 9.5),
        (3.22, 0.0045, 8.0),
        (3.08, 0.006, 13.0),
        (2.98, 0.005, 12.5),
        (2.93, 0.004, 11.0),
        (2.83, 0.004, 9.0),
        (2.07, 0.005, 8.0),
        (2.00, 0.005, 7.5),
        (1.66, 0.0055, 6.0),
        (1.27, 0.0045, 5.0),
    ]
    rows = ["ppm,intensity"]
    for x in xs:
        intensity = 0.03
        for center, width, amplitude in peaks:
            intensity += _gaussian(x, center, width, amplitude)
        rows.append(f"{x:.4f},{intensity:.8f}")
    return ("\n".join(rows) + "\n").encode()


def _resolved_multiplet_trace_csv() -> bytes:
    xs = [4.2 - idx * 0.0005 for idx in range(int((4.2 - 0.8) / 0.0005) + 1)]
    peaks = [
        (3.607, 0.0017, 8.0),
        (3.593, 0.0017, 8.0),
        (1.254, 0.0018, 5.0),
        (1.240, 0.0018, 10.0),
        (1.226, 0.0018, 5.0),
    ]
    rows = ["ppm,intensity"]
    for x in xs:
        intensity = 0.01
        for center, width, amplitude in peaks:
            intensity += _gaussian(x, center, width, amplitude)
        rows.append(f"{x:.4f},{intensity:.8f}")
    return ("\n".join(rows) + "\n").encode()


def _noisy_trace_csv(
    peaks: list[tuple[float, float, float]],
    *,
    noise: float,
    seed: int,
) -> bytes:
    """Synthesize a dense processed-spectrum CSV: Gaussian peaks + Gaussian noise.

    ``peaks`` are ``(center_ppm, width_ppm, amplitude)`` triples. An empty list
    yields a pure-noise trace, which the SNR-based detector must leave empty.
    """
    rng = random.Random(seed)
    xs = [9.0 - idx * 0.0015 for idx in range(6000)]
    rows = ["ppm,intensity"]
    for x in xs:
        intensity = rng.gauss(0.0, noise)
        for center, width, amplitude in peaks:
            intensity += _gaussian(x, center, width, amplitude)
        rows.append(f"{x:.4f},{intensity:.6f}")
    return ("\n".join(rows) + "\n").encode()


def test_parse_peak_table_csv() -> None:
    content = b"shift_ppm,multiplicity,integration_h\n3.50,q,2\n1.20,t,3\n"
    preview = parse_processed_spectrum(filename="peaks.csv", content=content, solvent="CDCl3")
    assert preview.source_mode == "peak_table"
    assert len(preview.inferred_peaks) == 2
    assert "3.50 (q, 2H)" in preview.inferred_nmr_text


def test_parse_trace_csv_infers_peaks() -> None:
    # A realistic dense processed-spectrum trace: the SNR-based detector needs
    # enough baseline points to estimate the noise floor, so a handful-of-points
    # toy is not a representative fixture for trace peak inference.
    preview = parse_processed_spectrum(filename="trace.csv", content=_dense_sugar_trace_csv())
    assert preview.source_mode == "trace"
    assert preview.point_count >= 1000
    assert len(preview.inferred_peaks) >= 1


def test_trace_detector_rejects_pure_noise_without_inventing_peaks() -> None:
    # A trace with no real signal — only Gaussian noise. The SNR-based detector
    # must not invent peaks from noise fluctuations ("no random predictions").
    preview = parse_processed_spectrum(
        filename="noise.csv",
        content=_noisy_trace_csv([], noise=5.0, seed=1),
    )
    assert preview.source_mode == "trace"
    assert preview.inferred_peaks == []


def test_trace_detector_recovers_reference_multiplet_count_under_noise() -> None:
    # Ground truth = a literature 1H reference text. A spectrum synthesized at
    # its reported shifts plus realistic noise must be detected back to the same
    # multiplet count and positions — the SNR threshold neither drops genuine
    # peaks nor adds noise peaks.
    reference = (
        "1H NMR (500 MHz, CDCl3) 7.34 (t, 2H), 3.62 (s, 2H), "
        "2.41 (q, 2H), 1.58 (m, 2H), 0.92 (t, 3H)"
    )
    _frequency, assignments = parse_reference_nmr_text(reference)
    synthetic_peaks = [
        (assignment.shift_ppm, 0.012, 30.0 + 20.0 * float(assignment.integration_h))
        for assignment in assignments
    ]
    preview = parse_processed_spectrum(
        filename="trace.csv",
        content=_noisy_trace_csv(synthetic_peaks, noise=4.0, seed=3),
    )
    detected = sorted(peak.shift_ppm for peak in preview.inferred_peaks)
    assert len(detected) == len(assignments)
    for assignment in assignments:
        assert any(abs(assignment.shift_ppm - shift) <= 0.06 for shift in detected)


def test_structure_guided_sweep_recovers_reference_multiplets_under_noise() -> None:
    # The shared structure-guided sweep (used by both the processed-upload and
    # Raw-FID paths) must pick the SNR sensitivity whose detected peak list best
    # matches the reference, recovering the reported multiplet count under noise.
    reference = (
        "1H NMR (400 MHz, CDCl3) 7.34 (t, 2H), 3.62 (s, 2H), "
        "2.41 (q, 2H), 1.58 (m, 2H), 0.92 (t, 3H)"
    )
    _frequency, assignments = parse_reference_nmr_text(reference)
    rng = random.Random(11)
    points: list[tuple[float, float]] = []
    for idx in range(6000):
        x = 9.0 - idx * 0.0015
        intensity = rng.gauss(0.0, 4.0)
        for assignment in assignments:
            intensity += _gaussian(x, assignment.shift_ppm, 0.012, 60.0)
        points.append((x, intensity))

    estimates, comparison, chosen = _structure_guided_peak_estimates(
        points,
        reference_assignments=assignments,
        reference_peaks=[],
        target_total_h=None,
        frequency_mhz=400.0,
    )
    detected = sorted(round(estimate.shift_ppm, 2) for estimate in estimates)
    assert len(estimates) == len(assignments)
    for assignment in assignments:
        assert any(abs(assignment.shift_ppm - shift) <= 0.06 for shift in detected)
    assert comparison is not None
    assert chosen in {0.06, 0.08, 0.1, 0.12, 0.15}


def test_structure_guided_sweep_honours_an_explicit_fixed_sensitivity() -> None:
    # An explicit fixed sensitivity collapses the sweep to that single value.
    points = [(9.0 - idx * 0.0015, 0.0) for idx in range(3000)]
    _estimates, _comparison, chosen = _structure_guided_peak_estimates(
        points,
        reference_assignments=[],
        reference_peaks=[],
        target_total_h=None,
        frequency_mhz=None,
        fixed_sensitivity=0.1,
    )
    assert chosen == 0.1


def test_priority_regions_recover_a_weak_peak_a_uniform_threshold_misses() -> None:
    # A weak peak inside a compound-class-diagnostic window (carbohydrate
    # anomeric region) must be recovered when the class hint supplies that
    # window, while staying below the normal uniform threshold without it.
    rng = random.Random(5)
    points: list[tuple[float, float]] = []
    for idx in range(6000):
        x = 10.0 - idx * (10.0 / 5999)
        intensity = rng.gauss(0.0, 12.0)
        intensity += _gaussian(x, 2.0, 0.012, 400.0)  # strong peak
        intensity += _gaussian(x, 4.8, 0.012, 26.0)  # weak peak, anomeric region
        points.append((x, intensity))

    without_hint = _infer_peak_estimates(points, sensitivity=0.12)
    with_hint = _infer_peak_estimates(
        points,
        sensitivity=0.12,
        priority_regions=diagnostic_regions_for("carbohydrates", "1H"),
    )
    assert sorted(round(estimate.shift_ppm, 1) for estimate in without_hint) == [2.0]
    assert sorted(round(estimate.shift_ppm, 1) for estimate in with_hint) == [2.0, 4.8]


def test_reference_multiplicity_is_adopted_for_matched_peaks() -> None:
    # A detected peak that matches a literature 1H-text assignment must adopt
    # that assignment's multiplicity and J — the text is authoritative for the
    # coupling pattern. An unmatched peak keeps its geometric label.
    _frequency, assignments = parse_reference_nmr_text(
        "1H NMR (400 MHz, CDCl3) 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H)"
    )
    detected = [
        Peak(shift_ppm=3.652, multiplicity="m", integration_h=2.0, j_values_hz=[]),
        Peak(shift_ppm=1.261, multiplicity="q", integration_h=3.0, j_values_hz=[12.0]),
        Peak(shift_ppm=9.99, multiplicity="m", integration_h=1.0, j_values_hz=[]),
    ]
    adopted = _apply_reference_multiplicity(detected, assignments)
    assert (adopted[0].multiplicity, adopted[0].j_values_hz) == ("q", [7.1])
    assert (adopted[1].multiplicity, adopted[1].j_values_hz) == ("t", [7.1])
    assert (adopted[2].multiplicity, adopted[2].j_values_hz) == ("m", [])
    # No reference text -> peaks returned unchanged.
    assert _apply_reference_multiplicity(detected, []) == detected


def test_geometric_multiplicity_does_not_overclaim_quartets() -> None:
    # Without spectral deconvolution a four-line cluster cannot be told apart
    # from a doublet-of-doublets, so it is reported honestly as "m".
    assert _classify_multiplicity(2, 0.01, 0.001) == "d"
    assert _classify_multiplicity(3, 0.01, 0.001) == "t"
    assert _classify_multiplicity(4, 0.01, 0.001) == "m"
    assert _classify_multiplicity(6, 0.01, 0.001) == "m"


def test_gsd_resolves_an_overlapped_quartet_through_the_full_pipeline() -> None:
    # An overlapped quartet (J = 7 Hz) that the local-maximum picker sees as a
    # two-bump envelope must be reported as a quartet once GSD deconvolution
    # runs inside parse_processed_spectrum.
    frequency = 400.0
    j_ppm = 7.0 / frequency
    quartet = [
        (2.40 + k * j_ppm, amp)
        for k, amp in zip((1.5, 0.5, -0.5, -1.5), (50.0, 150.0, 150.0, 50.0))
    ]
    rng = random.Random(7)
    rows = ["ppm,intensity"]
    point_count = 12000
    for index in range(point_count):
        x = 8.0 - index * (8.0 / (point_count - 1))
        intensity = _lorentzian(x, 300.0, 7.00, 0.0030)
        for center, amplitude in quartet:
            intensity += _lorentzian(x, amplitude, center, 0.0045)
        intensity += rng.gauss(0.0, 6.0)
        rows.append(f"{x:.5f},{intensity:.4f}")
    content = ("\n".join(rows) + "\n").encode()

    preview = parse_processed_spectrum(
        filename="trace.csv", content=content, frequency_mhz=frequency
    )
    near_quartet = [
        peak for peak in preview.inferred_peaks if abs(peak.shift_ppm - 2.40) <= 0.05
    ]
    assert len(near_quartet) == 1
    assert near_quartet[0].multiplicity == "q"


def test_parse_text_spectrum_pair_exports() -> None:
    content = b"4.0 0\n3.8 1\n3.6 5\n3.4 1\n3.2 0\n"
    preview = parse_processed_spectrum(filename="trace.xy", content=content)
    assert preview.source_mode == "trace"
    assert preview.point_count == 5


def test_parse_jcamp_extension_alias() -> None:
    content = b"##TITLE=demo\n4.0 0 3.8 1 3.6 5 3.4 1 3.2 0\n"
    preview = parse_processed_spectrum(filename="trace.jcamp", content=content)
    assert preview.source_mode == "trace"
    assert preview.point_count == 5


def test_parse_processed_spectrum_rejects_unsupported_file_formats() -> None:
    try:
        parse_processed_spectrum(filename="trace.raw", content=b"\x00\x01vendor-binary")
    except SpectrumParseError as exc:
        assert "Unsupported processed spectrum format" in str(exc)
    else:
        raise AssertionError("Expected unsupported spectrum formats to fail clearly.")


def test_round_half_integrations_never_drops_small_positive_values_to_zero() -> None:
    rounded = _round_half_integrations([0.2, 0.24, 0.26, 0.49], minimum=0.5)
    assert rounded == [0.5, 0.5, 0.5, 0.5]


def test_reference_guided_nmr_text_preserves_dense_region_ranges_when_coverage_is_high() -> None:
    _, assignments = parse_reference_nmr_text(TOBRAMYCIN_REFERENCE_TEXT)
    extracted_peaks = [
        Peak(shift_ppm=5.235, multiplicity="s", integration_h=2.0),
        Peak(shift_ppm=5.116, multiplicity="s", integration_h=0.5),
        Peak(shift_ppm=5.084, multiplicity="s", integration_h=2.5),
        Peak(shift_ppm=3.943, multiplicity="d", integration_h=0.5),
        Peak(shift_ppm=3.8, multiplicity="m", integration_h=5.5),
        Peak(shift_ppm=3.67, multiplicity="q", integration_h=2.5),
        Peak(shift_ppm=3.563, multiplicity="m", integration_h=3.5),
        Peak(shift_ppm=3.367, multiplicity="m", integration_h=8.0),
        Peak(shift_ppm=3.285, multiplicity="t", integration_h=4.0),
        Peak(shift_ppm=2.999, multiplicity="m", integration_h=12.0),
        Peak(shift_ppm=2.832, multiplicity="q", integration_h=3.5),
        Peak(shift_ppm=2.068, multiplicity="m", integration_h=3.0),
        Peak(shift_ppm=1.996, multiplicity="m", integration_h=3.0),
        Peak(shift_ppm=1.658, multiplicity="q", integration_h=4.0),
        Peak(shift_ppm=1.273, multiplicity="q", integration_h=4.0),
    ]

    guided_text, covered_count = _build_reference_guided_nmr_text(
        reference_assignments=assignments,
        extracted_peaks=extracted_peaks,
    )

    assert covered_count == 15
    assert guided_text is not None
    assert "3.60 - 3.53 (t, 3H)" in guided_text
    assert "3.11 - 2.98 (m, 4H)" in guided_text
    assert "2.93 (tdd" in guided_text


def test_trace_preview_without_reference_text_keeps_multiple_sugar_region_peaks() -> None:
    preview = parse_processed_spectrum(
        filename="dense_trace.csv",
        content=_dense_sugar_trace_csv(),
        solvent="D2O",
        mask_solvent_regions=True,
        expected_total_h=37,
        expected_non_labile_h=22,
    )

    sugar_peaks = [peak for peak in preview.inferred_peaks if 2.8 <= peak.shift_ppm <= 4.05]
    assert preview.source_mode == "trace"
    assert len(preview.inferred_peaks) >= 15
    assert len(sugar_peaks) >= 8
    assert preview.metadata["integration_normalized_to_target"] is True
    assert "3.22 (m, 12.5H)" not in preview.inferred_nmr_text
    assert preview.metadata["impurity_candidates"] == []


def test_embedded_h1_impurity_library_flags_pdf_shift_matches() -> None:
    content = b"shift_ppm,integration_h,multiplicity\n2.17,0.3,s\n"
    preview = parse_processed_spectrum(
        filename="acetone_impurity.csv",
        content=content,
        solvent="CDCl3",
    )

    candidates = preview.metadata["impurity_candidates"]
    assert candidates
    assert candidates[0]["library_match"]["label"] == "acetone CH3"
    assert candidates[0]["library_match"]["expected_ppm"] == 2.17


def test_trace_preview_without_reference_text_infers_j_values_when_frequency_is_supplied() -> None:
    preview = parse_processed_spectrum(
        filename="resolved_trace.csv",
        content=_resolved_multiplet_trace_csv(),
        frequency_mhz=500.0,
        expected_total_h=5,
        expected_non_labile_h=5,
    )

    assert preview.source_mode == "trace"
    assert any(peak.multiplicity == "d" and peak.j_values_hz for peak in preview.inferred_peaks)
    assert any(peak.multiplicity == "t" and peak.j_values_hz for peak in preview.inferred_peaks)
    assert "J = 7.0 Hz" in preview.inferred_nmr_text


def test_trace_preview_builds_reference_comparison_and_uses_d2o_visible_target() -> None:
    content = b"""ppm,intensity
5.50,0
5.35,1
5.28,4
5.23,8
5.18,4
5.12,1
5.02,3
4.95,24
4.88,36
4.81,44
4.74,34
4.67,18
4.60,5
4.20,0
4.08,1
4.00,4
3.95,7
3.90,3
3.84,1
3.72,2
3.68,5
3.64,2
3.20,0
"""
    preview = parse_processed_spectrum(
        filename="trace.csv",
        content=content,
        solvent="D2O",
        reference_nmr_text=TOBRAMYCIN_REFERENCE_TEXT,
        mask_solvent_regions=True,
        expected_total_h=37,
        expected_non_labile_h=22,
    )

    assert preview.source_mode == "trace"
    assert preview.reference_nmr_text_normalized is not None
    assert len(preview.reference_peaks) == 15
    assert preview.comparison is not None
    assert preview.comparison.structure_visible_h == 22.0
    assert preview.comparison.structure_reference_mismatch is True
    assert preview.metadata["target_visible_h"] == 22.0
    assert preview.metadata["mask_solvent_regions"] is True
    assert any("26H" in note and "22 visible H" in note for note in preview.comparison.notes)


def test_trace_preview_applies_baseline_and_display_smoothing_by_default() -> None:
    rows = ["ppm,intensity"]
    for idx in range(401):
        x = 8.0 - idx * 0.02
        baseline = 0.05 + (0.035 if idx % 2 else -0.02)
        solvent = 80.0 if abs(x - 7.26) <= 0.02 else 0.0
        analyte = 8.0 if abs(x - 3.50) <= 0.02 else 0.0
        rows.append(f"{x:.2f},{baseline + solvent + analyte:.6f}")

    preview = parse_processed_spectrum(
        filename="trace.csv",
        content=("\n".join(rows) + "\n").encode(),
        solvent="CDCl3",
        mask_solvent_regions=True,
    )

    preprocessing = preview.metadata["display_preprocessing"]
    assert preprocessing["baseline_smoothing"]["applied"] is False
    assert preprocessing["trace_smoothing"]["applied"] is True
    assert preprocessing["trace_smoothing"]["display_only"] is True
    assert preprocessing["display_solvent_masked"] is False
    assert preview.metadata["processed_baseline_correction"]["correction_applied"] is True
    assert preview.metadata["evidence_trace_mode"] == "uploaded_intensity_baseline_corrected"
    assert preview.metadata["display"]["main_trace"] == "display_smoothed_evidence_intensity"
    assert preview.metadata["display_mode"] == "real"
    assert preview.metadata["display_gain"] == 1.0
    assert preview.metadata["baseline_lock_visual_only"] is True
    assert preview.metadata["preview_downsampling"]["method"] == "min_max_bucket_extrema_preserving"
    assert "raw_preview_points" not in preview.metadata
    original_state = preview.metadata["original_spectrum_state"]
    assert original_state["preserved"] is True
    assert original_state["processing_stage"] == "as_uploaded"
    assert original_state["preview_points"]
    solvent_display = [
        point.intensity for point in preview.preview_points if 7.20 <= point.shift_ppm <= 7.32
    ]
    non_solvent_display = [
        point.intensity for point in preview.preview_points if 3.40 <= point.shift_ppm <= 3.60
    ]
    assert solvent_display
    assert non_solvent_display
    assert max(solvent_display) > max(non_solvent_display)


def test_vertical_gain_does_not_change_api_output_or_inferred_peaks() -> None:
    content = b"ppm,intensity\n4.0,0\n3.8,1\n3.6,5\n3.4,1\n3.2,0\n1.8,1\n1.6,4\n1.4,1\n"
    base = parse_processed_spectrum(filename="trace.csv", content=content, vertical_gain=1)
    gained = parse_processed_spectrum(filename="trace.csv", content=content, vertical_gain=128)

    assert [point.model_dump() for point in gained.preview_points] == [
        point.model_dump() for point in base.preview_points
    ]
    assert [peak.model_dump() for peak in gained.inferred_peaks] == [
        peak.model_dump() for peak in base.inferred_peaks
    ]
    assert gained.metadata["display_gain"] == 128.0


def test_weak_peak_magnifier_is_display_only() -> None:
    content = b"ppm,intensity\n4.0,0\n3.8,1\n3.6,50\n3.4,1\n3.2,0\n1.8,0.5\n1.6,2\n1.4,0.5\n"
    base = parse_processed_spectrum(filename="trace.csv", content=content)
    magnified = parse_processed_spectrum(
        filename="trace.csv",
        content=content,
        display_mode="magnifier",
        vertical_gain=80,
    )

    assert [point.model_dump() for point in magnified.preview_points] == [
        point.model_dump() for point in base.preview_points
    ]
    assert [peak.model_dump() for peak in magnified.inferred_peaks] == [
        peak.model_dump() for peak in base.inferred_peaks
    ]
    assert magnified.metadata["display_mode"] == "magnifier"
    assert magnified.metadata["display_preprocessing"]["weak_peak_magnifier"]["display_only"] is True
    assert magnified.metadata["display_preprocessing"]["weak_peak_magnifier"]["points"]


def test_extrema_preserving_downsampling_keeps_sharp_peaks() -> None:
    points = [(idx * 0.05, 0.0) for idx in range(5000)]
    points[2417] = (120.85, 1000.0)
    points[3199] = (159.95, -500.0)

    downsampled = _downsample_points(points, limit=300)

    assert len(downsampled) <= 300
    assert any(point.shift_ppm == 120.85 and point.intensity == 1000.0 for point in downsampled)
    assert any(point.shift_ppm == 159.95 and point.intensity == -500.0 for point in downsampled)


def test_peak_table_preview_emits_reference_guided_range_text_for_dense_assignments() -> None:
    content = b"""shift_ppm,multiplicity,integration_h
5.235,s,2.0
5.116,s,0.5
5.084,s,2.5
3.943,d,0.5
3.800,m,5.5
3.670,q,2.5
3.563,m,3.5
3.367,m,8.0
3.285,t,4.0
2.999,m,12.0
2.832,q,3.5
2.068,m,3.0
1.996,m,3.0
1.658,q,4.0
1.273,q,4.0
"""
    preview = parse_processed_spectrum(
        filename="peaks.csv",
        content=content,
        solvent="D2O",
        reference_nmr_text=TOBRAMYCIN_REFERENCE_TEXT,
    )

    assert preview.metadata["reference_guided_text_used"] is True
    assert preview.metadata["reference_coverage_count"] == 15
    assert preview.comparison is not None
    assert preview.comparison.missing_count == 0
    assert any("dense-region reference assignment" in note for note in preview.comparison.notes)
    assert "3.60 - 3.53 (t, 3H)" in preview.inferred_nmr_text
    assert "3.11 - 2.98 (m, 4H)" in preview.inferred_nmr_text
    assert "2.93 (tdd" in preview.inferred_nmr_text


def test_trace_reference_text_does_not_fabricate_missing_assignments() -> None:
    rows = ["ppm,intensity"]
    for idx in range(401):
        x = 2.0 - idx * 0.005
        intensity = 0.01 + _gaussian(x, 1.0, 0.01, 12.0)
        rows.append(f"{x:.4f},{intensity:.8f}")

    reference = "1H NMR (500 MHz, CDCl3) δ 7.20 (s, 1H), 1.00 (s, 3H)"
    preview = parse_processed_spectrum(
        filename="trace.csv",
        content=("\n".join(rows) + "\n").encode(),
        solvent="CDCl3",
        frequency_mhz=500.0,
        reference_nmr_text=reference,
    )

    assert "7.20" not in preview.inferred_nmr_text
    assert preview.metadata["reference_guided_text_used"] is False
    assert preview.metadata["reference_guided_text_abstained"] is True
    assert preview.metadata["peak_evidence_policy"] == "detected_peaks_only_no_reference_fabrication"
    assert preview.comparison is not None
    assert preview.comparison.missing_count >= 1
