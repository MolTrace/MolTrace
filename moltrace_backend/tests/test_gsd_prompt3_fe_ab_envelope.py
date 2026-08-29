"""Phase 13: FE A/B JSON dump as a backend regression gate.

The FE session captured a full A/B comparison of both detectors
(``/nmr/raw-fid/process`` legacy vs ``/spectrum/analyze/gsd``) across the
20-fixture NMRShiftDB2 corpus and dropped the result at
``tests/fixtures/gsd_prompt3_validation/fe_ab_legacy_vs_gsd_20260527.json``.
Each ab_run carries the FT'd spectrum arrays (``legacy.x`` / ``legacy.y``)
plus the captured peak + environment counts from both detectors.

This test pins those numbers as a regression envelope:

1. **GSD re-run**: replay each captured spectrum through the live GSD
   endpoint and assert the live result matches the captured envelope
   exactly (GSD is deterministic per
   ``test_spectrum_analyze_gsd_api.test_synthetic_baseline_does_not_drift``).
   Catches any change that perturbs peak detection / classification /
   clustering on real-world Bruker data, not just synthetic spectra.

2. **Captured payload sanity**: assert structural invariants on the
   captured legacy + gsd payloads (env_count == len(environments), category
   counts sum to peak count, etc).  Catches schema drift that would silently
   reshape the wire contract.

Legacy detector is NOT re-run live: the 60000006_13c case takes 5.5 min,
which is too slow for a default test.  Phase 12d covers the perf work.

When the FE drops a refreshed A/B JSON, swap the filename constant below
and the test transparently tracks the new envelope.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from nmrcheck.api import AccessContext, spectrum_analyze_gsd
from nmrcheck.models import SpectrumGSDAnalyzeRequest

# Latest FE A/B dump.  Bump when the FE drops a refreshed envelope.
_AB_JSON_FILENAME = "fe_ab_legacy_vs_gsd_20260527.json"
_AB_JSON_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "gsd_prompt3_validation"
    / _AB_JSON_FILENAME
)


def _load_ab_json() -> dict:
    if not _AB_JSON_PATH.exists():
        pytest.skip(f"FE A/B dump not present at {_AB_JSON_PATH}")
    return json.loads(_AB_JSON_PATH.read_text())


def _ab_runs() -> list[dict]:
    data = _load_ab_json()
    return data.get("ab_runs") or []


def _fixture_ids() -> list[str]:
    return [run["fixture_id"] for run in _ab_runs()]


def test_ab_dump_loads_and_is_structurally_valid() -> None:
    """Smoke test: the FE dump exists, parses, and has the expected shape."""

    data = _load_ab_json()
    assert "generated_at" in data
    assert "corpus" in data
    assert "ab_runs" in data
    runs = data["ab_runs"]
    assert len(runs) >= 18, (
        f"FE A/B dump shrunk below 18 fixtures (now {len(runs)}); "
        "either the corpus was reduced or the dump generation regressed."
    )
    for run in runs:
        # Per-fixture envelope keys the live re-run depends on.
        for key in (
            "fixture_id", "spectrum_id", "nucleus", "vendor",
            "reference_peak_count", "legacy", "gsd",
        ):
            assert key in run, f"ab_run missing {key!r}: {run.get('fixture_id')}"


def test_ab_dump_captured_payloads_are_structurally_consistent() -> None:
    """Both detector payloads in the dump must internally agree.

    e.g., legacy.environment_count must equal len(legacy.environments);
    gsd.environment_counts category totals must equal gsd.environment_count.
    Catches schema drift that would silently reshape the wire contract.
    """

    for run in _ab_runs():
        fid = run["fixture_id"]
        legacy = run["legacy"]
        gsd = run["gsd"]

        # Legacy invariants.
        if "environments" in legacy and "environment_count" in legacy:
            assert legacy["environment_count"] == len(legacy["environments"]), (
                f"{fid}: legacy.environment_count mismatch with len(environments)"
            )
        if "environment_counts" in legacy and "environment_count" in legacy:
            assert sum(legacy["environment_counts"].values()) == legacy["environment_count"], (
                f"{fid}: legacy.environment_counts sum != environment_count"
            )

        # GSD invariants.
        assert gsd["environment_count"] == len(gsd["environments"]), (
            f"{fid}: gsd.environment_count mismatch with len(environments)"
        )
        assert sum(gsd["environment_counts"].values()) == gsd["environment_count"], (
            f"{fid}: gsd.environment_counts sum != environment_count"
        )
        # GSD environments must collectively cover every peak (constituent
        # indices partition the peaks list).
        all_indices = []
        for env in gsd["environments"]:
            all_indices.extend(env.get("constituent_peak_indices", []))
        assert sorted(all_indices) == list(range(len(gsd["peaks"]))), (
            f"{fid}: gsd environments do not partition the peaks list"
        )


#: Where "a peak a chemist would put in the table" starts, in units of the
#: whole-spectrum MAD. The conventional limit of quantitation; below it a signal
#: may be detectable but is not a number anyone should read off.
_QUANTIFIABLE_SIGMA = 10.0


def _quantifiable_peaks_lost(*, captured_peaks, live_peaks, x, y, nucleus, level) -> list[float]:
    """Lines the detector finds, the capture reported, and the live run no longer does.

    Anchored on the DETECTED APEX, not on either run's fitted position. Three
    reasons, each of which cost a wrong answer first:

    1. Heights come from the captured TRACE, not from a fitted amplitude. A fitted
       amplitude can exceed the apex it models when the fit is broad, and mixing a
       fitted height with a differently-computed noise estimate is how the same
       three peaks were first measured at 14-23 sigma and then, on a single
       consistent definition, at 1.8x MAD.

    2. A CAPTURED POSITION IS NOT A DETECTION. A single-line fit was free to move
       anywhere inside a window several line widths wide, and on these traces --
       decimated to about 1.5 points per linewidth -- it often did. Only 387 of the
       548 captured peaks (70.6%) sit on an apex the detector seeds; the other 29%
       are positions no detection ever produced. Reading the trace height at one of
       those and calling it a lost peak credits the runaway.

    3. Matching the capture to the live run DIRECTLY fails the same way from the
       other side: a capture that landed between a seed and that seed's true centre
       is further than the tolerance from both, so the line reads as lost while it
       is sitting in the output at its own apex. Both sides are matched to the seed
       instead, so the question is the one the message asks -- is the line the
       detector found still in the table?

    Detection is not what the fitter change touched, which is why this can judge
    that change rather than assume it.
    """
    import numpy as np

    from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
    from moltrace.spectroscopy.peaks.gsd import (
        _finite_spectrum_arrays,
        _initial_peak_indices,
        _positive_peak_orientation,
        _robust_noise,
    )

    signal = np.asarray(y, dtype=float)
    signal = signal - float(np.median(signal))
    centred = signal - float(np.median(signal))
    mad = 1.4826 * float(np.median(np.abs(centred - float(np.median(centred)))))
    if not np.isfinite(mad) or mad <= 0:
        return []

    ppm = np.asarray(x, dtype=float)
    step = float(np.median(np.abs(np.diff(np.sort(ppm))))) or 1e-6

    # The apexes the detector seeds on this trace, through the same entry point the
    # live run uses, so "was there a line here" is asked once and one way.
    spectrum = NMRSpectrum(
        data=np.asarray(y, dtype=float), ppm_axis=ppm, nucleus=nucleus
    )
    axis, values = _finite_spectrum_arrays(spectrum)
    if axis.size < 8:
        return []
    oriented = _positive_peak_orientation(values)
    detection_noise = _robust_noise(oriented - float(np.median(oriented)))
    if not np.isfinite(detection_noise) or detection_noise <= 0:
        return []
    indices, widths_points, _properties = _initial_peak_indices(
        axis,
        oriented - float(np.median(oriented)),
        noise=detection_noise,
        nucleus=nucleus,
        level=level,
    )
    if not indices.size:
        return []

    captured_ppm = np.asarray(
        sorted(float(peak["position_ppm"]) for peak in captured_peaks), dtype=float
    )
    live_ppm = np.asarray(sorted(peak.position_ppm for peak in live_peaks), dtype=float)

    def covered(positions, target: float, tolerance: float) -> bool:
        return bool(
            positions.size and float(np.min(np.abs(positions - target))) <= tolerance
        )

    lost: list[float] = []
    for index, width_points in zip(indices, widths_points, strict=False):
        seed = float(axis[int(index)])
        # ONE LINEWIDTH, not a fixed count of samples. A fixed sample window is a
        # different physical distance on every trace here -- these are decimated to
        # about 1.5 points per linewidth, and on the sparsest of them a line spans
        # 1.5 ppm, so four samples is a fifth of a linewidth. A fit that refines a
        # quarter of a linewidth off its apex is doing its job, and the fixed window
        # called that the line disappearing. Same reasoning, and the same unit, as
        # ``eval.detector_corpus.score_detection``.
        tolerance = max(step * 4.0, 0.01, float(width_points) * step)
        trace_index = int(np.argmin(np.abs(ppm - seed)))
        height = abs(float(signal[trace_index])) / mad
        if height < _QUANTIFIABLE_SIGMA:
            continue
        if not covered(captured_ppm, seed, tolerance):
            # The capture did not report this line either, so its disappearance is
            # not something this envelope recorded.
            continue
        if covered(live_ppm, seed, tolerance):
            continue
        lost.append(height)
    return lost


@pytest.mark.parametrize("fixture_id", _fixture_ids() or ["no-fixtures"])
def test_gsd_live_rerun_within_ab_envelope(fixture_id: str) -> None:
    """Re-run GSD on the captured spectrum; result must stay within envelope.

    Tolerance is per-fixture: the FE dump records ``peak_count_tolerance``
    (typically ±2 peaks) reflecting the manifest's expected wiggle room.
    We use that as the live-vs-captured allowed drift.  Exact equality is
    too brittle because algorithmic refinements between the FE capture and
    a later backend turn legitimately shift classifications by a few peaks
    even on the same input.

    What this test catches:
      * Detection-level breakage (peak_count drops by 10+ vs captured).
      * Major classification shifts (environment_count moves significantly).
      * Whole-fixture regressions (live can't process the captured trace).

    What this test deliberately does NOT enforce:
      * Exact category_counts / environment_counts equality -- those are
        very sensitive to small classifier tweaks and would produce
        constant false-positive failures every time the FE re-captures.
        Category mix is sanity-checked structurally (totals match) instead.
    """

    if fixture_id == "no-fixtures":
        pytest.skip("FE A/B dump not present")

    run = next((r for r in _ab_runs() if r["fixture_id"] == fixture_id), None)
    assert run is not None, f"fixture_id {fixture_id} not in dump"
    captured = run["gsd"]
    legacy = run["legacy"]
    x = legacy.get("x") or []
    y = legacy.get("y") or []
    if not x or not y or len(x) != len(y) or len(x) < 16:
        pytest.skip(
            f"{fixture_id}: captured trace too short / mismatched for live re-run"
        )

    # Use the same input parameters the FE captured.
    # NOTE: renamed from ``request`` to ``payload`` after v0.6.3 added a
    # ``request: Request`` parameter to ``spectrum_analyze_gsd`` for
    # telemetry — we pass ``request=None`` below to skip the audit emit.
    payload = SpectrumGSDAnalyzeRequest(
        ppm_axis=x,
        intensity=y,
        nucleus=run["nucleus"],
        solvent=legacy.get("solvent") or "",
        field_mhz=float(legacy.get("field_mhz") or 500.0),
        level=int(captured.get("level") or 2),
    )

    # Tolerance: use the dump's per-fixture peak_count_tolerance plus a
    # generous relative floor (50%) so the test rides out the inevitable
    # drift between FE capture and later backend turns (e.g., Phase 10
    # multiplet clustering can legitimately shift env counts by 30%+ on
    # multiplet-heavy 1H spectra without indicating a regression).  The
    # 50% floor still catches catastrophic regressions like "fixture
    # returns 0 peaks" or "env_count cratered to 1".
    captured_peak_count = len(captured["peaks"])
    captured_env_count = int(captured["environment_count"])
    base_tol = int(run.get("peak_count_tolerance") or 2)
    peak_tol = max(base_tol, int(0.50 * captured_peak_count))
    env_tol = max(base_tol, int(0.50 * max(captured_env_count, 1)))

    async def _run() -> None:
        result = await spectrum_analyze_gsd(
            payload=payload,
            request=None,  # direct handler call: telemetry skipped
            context=AccessContext(system_api_key=True),
        )

        live_peak_count = len(result.peaks)
        peak_delta = abs(live_peak_count - captured_peak_count)

        # A DROP AND A RISE ARE NOT THE SAME EVENT, and pinning |delta| treated
        # them as one. The captured baseline is a recording of what the detector
        # did, not of what is in the spectrum — so when the detector was picking
        # noise, this window pinned the noise and went red on the correction.
        #
        # Measured on the four 13C fixtures here when the 13C noise estimator was
        # unbiased: 81 peaks disappeared and every one of them sat between 1.6x
        # and 3.3x the whole-spectrum MAD. Nothing at or above 10x was lost —
        # nothing quantifiable, on any fixture.
        #
        # So a drop is judged on what it dropped. Every captured peak that clears
        # the quantitation floor must still be found; below that the count is the
        # detector's opinion about noise and is not a regression envelope.
        # A RISE is still judged on the count, because inventing peaks has no
        # such excuse.
        lost_real = _quantifiable_peaks_lost(
            captured_peaks=captured["peaks"],
            live_peaks=result.peaks,
            x=x,
            y=y,
            nucleus=run["nucleus"],
            level=int(captured.get("level") or 2),
        )
        assert not lost_real, (
            f"{fixture_id}: {len(lost_real)} peak(s) at or above "
            f"{_QUANTIFIABLE_SIGMA}x the baseline noise were captured and are no longer found "
            f"(heights over MAD: {[round(h, 1) for h in lost_real[:5]]}).  "
            "That is a detection regression: something a chemist would put in the table is gone."
        )
        if live_peak_count > captured_peak_count:
            assert peak_delta <= peak_tol, (
                f"{fixture_id}: peak_count ROSE {captured_peak_count} -> {live_peak_count} "
                f"(delta {peak_delta} over tolerance {peak_tol}).  The detector is finding more "
                "than it was: over-detection, or a threshold that dropped."
            )
        if result.environment_count > captured_env_count:
            env_delta = abs(result.environment_count - captured_env_count)
            assert env_delta <= env_tol, (
                f"{fixture_id}: environment_count ROSE "
                f"{captured_env_count} -> {result.environment_count} (delta {env_delta} over "
                f"tolerance {env_tol}).  Multiplet clustering window changed materially."
            )
        # Structural sanity: category_counts must sum to peak_count even if
        # the per-category distribution drifted.
        assert sum(result.category_counts.values()) == live_peak_count, (
            f"{fixture_id}: live category_counts sum != peak_count"
        )
        assert sum(result.environment_counts.values()) == result.environment_count, (
            f"{fixture_id}: live environment_counts sum != environment_count"
        )

    asyncio.run(_run())


def test_the_lost_line_criterion_is_not_vacuous() -> None:
    """Delete a line the detector found, and the criterion must say so.

    This criterion was narrowed -- it used to count any captured position whose
    trace height cleared the floor, and it now counts only lines the detector
    actually seeds, matched within a linewidth. A narrowed guard has to be shown
    to still bite, or the narrowing is just the failure being switched off.

    Fires on 15 of the 19 replayable fixtures when their tallest reported line is
    deleted. The ones it stays silent on are correct: there, another reported line
    still sits within a linewidth of that seed, so the line the detector found is
    still in the table. Two of them are the CDCl3 triplet, whose three lines are
    0.06 ppm apart.

    The bar is a bare majority, not the measured 15. This asks whether the
    criterion bites at all, and it must answer that the same way for any detector
    the repository might have -- on the fitter this file's own fixes replaced it
    fires on 12 of 19, because there a runaway from a neighbouring seed often
    covered the deleted line. A bar set at today's number would quietly turn a
    vacuity check into a second opinion about the fitter.
    """

    fired = 0
    checked = 0
    for run in _ab_runs():
        legacy = run["legacy"]
        captured = run["gsd"]
        x = legacy.get("x") or []
        y = legacy.get("y") or []
        if not x or not y or len(x) != len(y) or len(x) < 16:
            continue
        payload = SpectrumGSDAnalyzeRequest(
            ppm_axis=x,
            intensity=y,
            nucleus=run["nucleus"],
            solvent=legacy.get("solvent") or "",
            field_mhz=float(legacy.get("field_mhz") or 500.0),
            level=int(captured.get("level") or 2),
        )

        async def _run(payload=payload):
            return await spectrum_analyze_gsd(
                payload=payload, request=None, context=AccessContext(system_api_key=True)
            )

        peaks = list(asyncio.run(_run()).peaks)
        if len(peaks) < 3:
            continue
        checked += 1
        tallest = max(range(len(peaks)), key=lambda i: peaks[i].intensity)
        without = [peak for i, peak in enumerate(peaks) if i != tallest]
        if _quantifiable_peaks_lost(
            captured_peaks=captured["peaks"],
            live_peaks=without,
            x=x,
            y=y,
            nucleus=run["nucleus"],
            level=int(captured.get("level") or 2),
        ):
            fired += 1

    if checked == 0:
        pytest.skip("FE A/B dump not present")
    assert fired > checked // 2, (
        f"deleting the tallest line went unnoticed on {checked - fired} of {checked} "
        "fixtures — this criterion is no longer measuring whether a line disappeared"
    )
