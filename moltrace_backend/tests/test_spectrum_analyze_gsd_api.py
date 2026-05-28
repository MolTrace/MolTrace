"""Tests for the opt-in GSD-Prompt-3 analysis endpoint.

The endpoint at ``POST /spectrum/analyze/gsd`` exposes the validated Prompt 3
sidecar (``moltrace.spectroscopy.peaks.gsd``) as an experimental analysis
backend, separate from the default ``/spectrum/analyze`` flow.  These tests
exercise the happy path against synthetic spectra (which give predictable
peak counts without relying on the NMRShiftDB2 fixtures the
``test_prompt3_gsd_fixture_validation`` suite already covers).
"""

from __future__ import annotations

import asyncio
import math
from tempfile import mkdtemp

import numpy as np
from starlette.requests import Request

from nmrcheck.api import AccessContext, create_app, spectrum_analyze_gsd
from nmrcheck.database import init_db
from nmrcheck.models import SpectrumGSDAnalyzeRequest
from nmrcheck.settings import Settings


def _request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-gsd-api-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/gsd_api.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
            "method": "POST",
            "path": "/spectrum/analyze/gsd",
            "query_string": b"",
        }
    )


def _synthetic_1h_cdcl3_spectrum() -> tuple[list[float], list[float]]:
    """Generate a deterministic 1H spectrum with 3 peaks (incl. CDCl3 residual)."""

    ppm = np.linspace(10.0, 0.0, 8192)

    def _lorentzian(centre: float, height: float, fwhm: float) -> np.ndarray:
        hwhm = fwhm / 2.0
        return height * hwhm * hwhm / ((ppm - centre) ** 2 + hwhm * hwhm)

    intensity = (
        _lorentzian(7.26, 80.0, 0.010)  # CDCl3 residual
        + _lorentzian(3.50, 60.0, 0.014)  # analyte
        + _lorentzian(1.25, 40.0, 0.018)  # analyte
        + 0.05 * np.sin(np.arange(ppm.size) * 0.037)  # baseline noise
    )
    return ppm.tolist(), intensity.tolist()


def test_spectrum_analyze_gsd_returns_classified_peaks() -> None:
    ppm, intensity = _synthetic_1h_cdcl3_spectrum()

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=2,
            ),
            context=AccessContext(system_api_key=True),
        )

        assert result.backend == "gsd_prompt3"
        assert result.experimental is True
        assert result.level == 2
        assert result.spectrum_metadata["nucleus"] == "1H"
        assert result.spectrum_metadata["solvent"] == "CDCl3"
        assert result.spectrum_metadata["input_point_count"] == len(ppm)
        # All three synthetic peaks should be picked up.
        assert len(result.peaks) >= 3
        # CDCl3 residual at 7.26 must be auto-classified as solvent.
        solvent_peaks = [p for p in result.peaks if p.category == "solvent"]
        assert any(abs(p.position_ppm - 7.26) <= 0.05 for p in solvent_peaks)
        # Category counts must aggregate the per-peak categories.
        assert sum(result.category_counts.values()) == len(result.peaks)

    asyncio.run(run())


def test_spectrum_analyze_gsd_defaults_to_level_2_pseudo_voigt() -> None:
    ppm, intensity = _synthetic_1h_cdcl3_spectrum()

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
            ),
            context=AccessContext(system_api_key=True),
        )

        assert result.level == 2
        # Level 2 fits pseudo-Voigt per peak; level 4-5 would trigger the
        # deconvolve_region bridge with a documented note.
        assert not any("deconvolve_region" in note for note in result.notes)
        assert all(p.shape == "voigt" for p in result.peaks[:3])

    asyncio.run(run())


def test_spectrum_analyze_gsd_level_4_emits_iterative_note() -> None:
    ppm, intensity = _synthetic_1h_cdcl3_spectrum()

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=4,
            ),
            context=AccessContext(system_api_key=True),
        )

        assert result.level == 4
        assert any("deconvolve_region" in note for note in result.notes), (
            "Level 4-5 must surface the iterative-deconvolve note so users "
            "understand the multiplet-line resolution semantics."
        )

    asyncio.run(run())


def test_spectrum_analyze_gsd_rejects_mismatched_array_lengths() -> None:
    from fastapi.exceptions import HTTPException

    ppm, intensity = _synthetic_1h_cdcl3_spectrum()
    truncated = intensity[:-1]  # drop one sample
    payload = SpectrumGSDAnalyzeRequest.model_construct(
        ppm_axis=ppm,
        intensity=truncated,
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=500.0,
        level=2,
    )

    raised = False
    try:
        asyncio.run(
            spectrum_analyze_gsd(
                payload=payload,
                context=AccessContext(system_api_key=True),
            )
        )
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 400
        assert "same length" in str(exc.detail)
    assert raised, "spectrum_analyze_gsd must reject mismatched array lengths."


def test_openapi_schema_includes_gsd_endpoint() -> None:
    """Sanity check that the FE will see the new contract via schema.d.ts."""

    tmpdir = mkdtemp(prefix="nmrcheck-gsd-openapi-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/gsd_openapi.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    schema = app.openapi()
    assert "/spectrum/analyze/gsd" in schema["paths"], (
        "/spectrum/analyze/gsd must appear in the OpenAPI schema so the FE "
        "session's `npm run generate:openapi` picks it up automatically."
    )
    operation = schema["paths"]["/spectrum/analyze/gsd"]["post"]
    assert operation["operationId"] == "spectrum_analyze_gsd_spectrum_analyze_gsd_post"
    # The opt-in / experimental nature must be discoverable from the schema docs.
    assert "experimental" in operation.get("description", "").lower()


def test_synthetic_baseline_does_not_drift() -> None:
    """Deterministic input -> deterministic output across runs."""

    ppm, intensity = _synthetic_1h_cdcl3_spectrum()
    payload = SpectrumGSDAnalyzeRequest(
        ppm_axis=ppm,
        intensity=intensity,
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=500.0,
        level=2,
    )

    async def _once() -> list[float]:
        result = await spectrum_analyze_gsd(
            payload=payload,
            context=AccessContext(system_api_key=True),
        )
        return [round(p.position_ppm, 4) for p in result.peaks]

    first = asyncio.run(_once())
    second = asyncio.run(_once())
    assert first == second, f"Non-deterministic GSD output: {first} != {second}"
    assert all(math.isfinite(value) for value in first)


def _synthetic_13c_cdcl3_spectrum() -> tuple[list[float], list[float]]:
    """Deterministic 13C spectrum with 3 analyte peaks + CDCl3 residual."""

    ppm = np.linspace(220.0, -20.0, 16384)

    def _lorentzian(centre: float, height: float, fwhm: float) -> np.ndarray:
        hwhm = fwhm / 2.0
        return height * hwhm * hwhm / ((ppm - centre) ** 2 + hwhm * hwhm)

    intensity = (
        _lorentzian(77.16, 60.0, 0.06)  # CDCl3 residual (will be classified solvent)
        + _lorentzian(128.5, 85.0, 0.08)  # aromatic carbon
        + _lorentzian(55.0, 70.0, 0.07)  # methoxy carbon
        + _lorentzian(22.0, 55.0, 0.07)  # methyl carbon
        + 0.04 * np.sin(np.arange(ppm.size) * 0.041)
    )
    return ppm.tolist(), intensity.tolist()


def test_spectrum_analyze_gsd_handles_13c_spectrum() -> None:
    """The endpoint accepts ``nucleus='13C'`` and classifies CDCl3 carbon correctly."""

    ppm, intensity = _synthetic_13c_cdcl3_spectrum()

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="13C",
                solvent="CDCl3",
                field_mhz=125.0,
                level=2,
            ),
            context=AccessContext(system_api_key=True),
        )

        assert result.spectrum_metadata["nucleus"] == "13C"
        assert result.spectrum_metadata["field_mhz"] == 125.0
        # All three analyte peaks + residual should surface.
        assert len(result.peaks) >= 4
        # The 77.16 ppm peak (CDCl3 residual) must be classified solvent.
        solvent_peaks = [p for p in result.peaks if p.category == "solvent"]
        assert any(abs(p.position_ppm - 77.16) <= 0.7 for p in solvent_peaks), (
            f"CDCl3 13C residual not classified solvent. "
            f"Solvent peaks: {[(round(p.position_ppm, 3), round(p.confidence, 3)) for p in solvent_peaks]}"
        )

    asyncio.run(run())


def test_spectrum_analyze_gsd_handles_realistic_spectrum_size() -> None:
    """65k point spectrum (typical 1D NMR FFT size) must process in reasonable time."""

    ppm = np.linspace(10.0, 0.0, 65536)

    def _lorentzian(centre: float, height: float, fwhm: float) -> np.ndarray:
        hwhm = fwhm / 2.0
        return height * hwhm * hwhm / ((ppm - centre) ** 2 + hwhm * hwhm)

    intensity = (
        _lorentzian(7.26, 80.0, 0.010)
        + _lorentzian(3.50, 60.0, 0.014)
        + _lorentzian(1.25, 40.0, 0.018)
        + 0.05 * np.sin(np.arange(ppm.size) * 0.037)
    )

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm.tolist(),
                intensity=intensity.tolist(),
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=2,
            ),
            context=AccessContext(system_api_key=True),
        )

        assert result.spectrum_metadata["input_point_count"] == 65536
        assert len(result.peaks) >= 3
        # The CDCl3 residual must still be classified at full resolution.
        assert any(p.category == "solvent" for p in result.peaks)

    asyncio.run(run())


def test_spectrum_analyze_gsd_all_levels_round_trip() -> None:
    """All five levels (1..5) must round-trip through the API without errors."""

    ppm, intensity = _synthetic_1h_cdcl3_spectrum()

    async def _run_level(level: int) -> tuple[int, str, bool]:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=level,
            ),
            context=AccessContext(system_api_key=True),
        )
        return result.level, result.backend, result.experimental

    for level in (1, 2, 3, 4, 5):
        returned_level, backend, experimental = asyncio.run(_run_level(level))
        assert returned_level == level, (
            f"Level {level} request returned level {returned_level}."
        )
        assert backend == "gsd_prompt3", f"Wrong backend for level {level}: {backend}"
        assert experimental is True, f"Level {level} dropped the experimental flag."


def _synthetic_quartet_at(centre_ppm: float, j_hz: float, field_mhz: float) -> tuple[list[float], list[float]]:
    """Spectrum with a 4-peak multiplet centred at ``centre_ppm`` (1H, ~quartet).

    Used to verify that ``cluster_into_environments`` correctly groups the
    4 multiplet lines into a single ``GSDPromptEnvironment`` entry while
    preserving them as separate items in the raw ``peaks`` list.
    """

    ppm = np.linspace(centre_ppm + 0.5, centre_ppm - 0.5, 8192)
    j_ppm = j_hz / field_mhz
    centres = [centre_ppm - 1.5 * j_ppm, centre_ppm - 0.5 * j_ppm, centre_ppm + 0.5 * j_ppm, centre_ppm + 1.5 * j_ppm]
    intensities = [10.0, 30.0, 30.0, 10.0]  # 1:3:3:1 (proton quartet)

    def _lorentzian(c: float, h: float, fwhm: float) -> np.ndarray:
        hwhm = fwhm / 2.0
        return h * hwhm * hwhm / ((ppm - c) ** 2 + hwhm * hwhm)

    signal = sum(
        _lorentzian(c, h, j_hz * 0.4 / field_mhz)
        for c, h in zip(centres, intensities, strict=True)
    )
    signal = signal + 0.05 * np.sin(np.arange(ppm.size) * 0.041)
    return ppm.tolist(), signal.tolist()


def test_clustering_collapses_multiplet_into_one_environment() -> None:
    """A 4-line proton quartet must yield 4 peaks but 1 environment."""

    ppm, intensity = _synthetic_quartet_at(centre_ppm=3.5, j_hz=7.0, field_mhz=500.0)

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=3,
            ),
            context=AccessContext(system_api_key=True),
        )

        # The quartet should resolve as 4 separate compound peaks.
        compound_peaks = [p for p in result.peaks if p.category == "compound"]
        assert len(compound_peaks) >= 3, (
            f"Quartet must resolve as >= 3 peaks; got {len(compound_peaks)}"
        )
        # But cluster into 1 environment (one chemical environment).
        compound_envs = [e for e in result.environments if e.category == "compound"]
        assert len(compound_envs) == 1, (
            f"4-line quartet must cluster to 1 compound environment; "
            f"got {len(compound_envs)} envs from {len(compound_peaks)} peaks. "
            f"Env centres: {[round(e.centre_ppm, 3) for e in compound_envs]}"
        )
        env = compound_envs[0]
        assert env.peak_count == len(compound_peaks)
        # Multiplicity letter depends on detected peak count (3 -> t, 4 -> q).
        assert env.multiplicity in {"t", "q", "quint"}, env.multiplicity
        # Centre must land near the configured 3.5 ppm.
        assert abs(env.centre_ppm - 3.5) <= 0.05, env.centre_ppm
        # Constituent indices must point at real positions in the peaks list.
        assert len(env.constituent_peak_indices) == env.peak_count
        for idx in env.constituent_peak_indices:
            assert 0 <= idx < len(result.peaks)
            assert result.peaks[idx].category == "compound"

    asyncio.run(run())


def test_clustering_keeps_separate_categories_separate() -> None:
    """A compound peak adjacent to a solvent peak must NOT merge."""

    ppm, intensity = _synthetic_1h_cdcl3_spectrum()

    async def run() -> None:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=2,
            ),
            context=AccessContext(system_api_key=True),
        )

        # The synthetic spectrum has CDCl3 (solvent) at 7.26 + analyte
        # peaks at 3.5 and 1.25.  Each is a different chemical environment.
        assert result.environment_count >= 3, (
            f"Expected >= 3 distinct environments; got {result.environment_count}. "
            f"Categories: {result.environment_counts}"
        )
        # Solvent and compound categories must each show up.
        assert result.environment_counts.get("solvent", 0) >= 1
        assert result.environment_counts.get("compound", 0) >= 2
        # Every peak must be accounted for in exactly one environment.
        all_peak_indices = []
        for env in result.environments:
            all_peak_indices.extend(env.constituent_peak_indices)
        assert sorted(all_peak_indices) == list(range(len(result.peaks))), (
            f"Environment constituent_peak_indices must partition the peaks list. "
            f"Got {sorted(all_peak_indices)} vs expected {list(range(len(result.peaks)))}"
        )


    asyncio.run(run())


def test_clustering_explicit_j_overrides_nucleus_default() -> None:
    """``cluster_j_hz`` override must change the grouping behavior."""

    # Two peaks 0.04 ppm apart at 500 MHz = 20 Hz apart.
    # Default 1H window is 20 Hz so they merge; cluster_j_hz=5 should split.
    ppm = np.linspace(5.0, 2.0, 8192).tolist()
    ppm_arr = np.asarray(ppm)

    def _lorentzian(c: float, h: float, fwhm: float) -> np.ndarray:
        hwhm = fwhm / 2.0
        return h * hwhm * hwhm / ((ppm_arr - c) ** 2 + hwhm * hwhm)

    intensity = (
        _lorentzian(3.50, 40.0, 0.008)
        + _lorentzian(3.46, 40.0, 0.008)  # 0.04 ppm = 20 Hz at 500 MHz
        + 0.05 * np.sin(np.arange(ppm_arr.size) * 0.037)
    ).tolist()

    async def _run(cluster_j_hz: float | None) -> int:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm,
                intensity=intensity,
                nucleus="1H",
                solvent="",
                field_mhz=500.0,
                level=2,
                cluster_j_hz=cluster_j_hz,
            ),
            context=AccessContext(system_api_key=True),
        )
        return sum(1 for e in result.environments if e.category == "compound")

    # Default 20 Hz: two ~20-Hz-separated peaks merge into 1 environment.
    default_env_count = asyncio.run(_run(None))
    # Tighter 5 Hz: same peaks should split into 2 environments.
    tight_env_count = asyncio.run(_run(5.0))
    assert tight_env_count >= default_env_count, (
        f"Tight cluster_j_hz=5 should produce >= environments than default 20. "
        f"default={default_env_count}, tight={tight_env_count}"
    )


def test_spectrum_analyze_gsd_empty_peaks_suggests_level_escalation() -> None:
    """When no peaks are picked, the note must point the FE at level N+1.

    Per Phase 8 FE feedback: the FE renders backend ``notes`` as info-level
    alerts above an empty results table.  Surfacing the level-escalation
    suggestion server-side means the empty-state UX improves automatically
    with no FE change.
    """

    # A featureless near-zero trace: 1024 samples, all tiny.
    n = 1024
    ppm_flat = np.linspace(10.0, 0.0, n).tolist()
    intensity_flat = [1e-9] * n

    async def _run_at_level(level: int) -> list[str]:
        result = await spectrum_analyze_gsd(
            payload=SpectrumGSDAnalyzeRequest(
                ppm_axis=ppm_flat,
                intensity=intensity_flat,
                nucleus="1H",
                solvent="CDCl3",
                field_mhz=500.0,
                level=level,
            ),
            context=AccessContext(system_api_key=True),
        )
        return result.notes

    # Level 2: empty -> note should explicitly suggest level 3.
    notes_l2 = asyncio.run(_run_at_level(2))
    assert any(
        "level 3" in note and "level 2" in note for note in notes_l2
    ), f"Level 2 empty-peaks note must suggest level 3. Got: {notes_l2}"

    # Level 5: cannot escalate further, message should pivot to data-quality.
    notes_l5 = asyncio.run(_run_at_level(5))
    assert any("level 5" in note for note in notes_l5), notes_l5
    assert not any(
        "level 6" in note for note in notes_l5
    ), f"Must not suggest a non-existent level 6. Got: {notes_l5}"
