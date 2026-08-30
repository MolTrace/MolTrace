"""A per-line width, distinct from the extent of the cluster it sits in.

``_PeakEstimate.width_ppm`` spans a whole cluster from its leftmost to its
rightmost point, wings included; on real acquisitions it measures 3-16x the
width of the line inside it. It is not a linewidth and cannot be compared
against one. ``line_width_ppm`` is the FWHM of a single line, which is the
quantity a merge, a shim problem or an exchange-broadened proton actually move.

Both widths were already being computed on the way through -- the half-width
that sizes the integration window, and the ``hwhm_ppm`` term of the tuples
``deconvolve_region`` returns -- and both were discarded before anything could
read them.
"""

from __future__ import annotations

import pytest

from nmrcheck.spectrum import _estimates_to_peaks, _infer_peak_estimates

#: 0.0100 ppm at 400 MHz is a 4.0 Hz line: an ordinary, well-shimmed 1H
#: resonance rather than a favourable one.
TRUE_FWHM_PPM = 0.0100
FIELD_MHZ = 400.0
SPAN_PPM = 12.0
#: 19200 points over 12 ppm is 16 points per FWHM, matching the density the
#: viewer requests at zoom. The width is measured on the smoothed detection
#: trace, so it is only honest where the trace is sampled: against this known
#: line it reads 1.06x true at 16 points per FWHM, but 1.38x at 8, 1.75x at 4
#: and 3.50x at 2. Below roughly 8 points per linewidth it is smoothing width,
#: not line width.
DENSE_POINTS = 19200


def _lorentzian(x: float, centre: float, fwhm: float, amplitude: float) -> float:
    half = fwhm / 2.0
    return amplitude * half * half / ((x - centre) ** 2 + half * half)


def _trace(
    centres: list[float], *, points: int = DENSE_POINTS, amplitude: float = 100.0
) -> list[tuple[float, float]]:
    """Descending-ppm trace carrying one Lorentzian per centre."""
    xs = [SPAN_PPM * (1.0 - index / (points - 1)) for index in range(points)]
    return [
        (x, sum(_lorentzian(x, c, TRUE_FWHM_PPM, amplitude) for c in centres))
        for x in xs
    ]


def _tallest_near(estimates, centre: float, tolerance: float = 0.4):
    near = [e for e in estimates if abs(e.shift_ppm - centre) < tolerance]
    return max(near, key=lambda e: e.intensity) if near else None


def _pair_at(separation_fwhm: float, centre: float = 6.0, **kwargs):
    offset = separation_fwhm * TRUE_FWHM_PPM / 2.0
    trace = _trace([centre - offset, centre + offset], **kwargs)
    return _tallest_near(_infer_peak_estimates(trace, frequency_mhz=FIELD_MHZ), centre)


def test_line_width_recovers_a_known_linewidth() -> None:
    """The number has to be the width of the line that was put there."""
    estimate = _tallest_near(
        _infer_peak_estimates(_trace([6.0]), frequency_mhz=FIELD_MHZ), 6.0
    )
    assert estimate is not None
    ratio = estimate.line_width_ppm / TRUE_FWHM_PPM
    assert 0.90 <= ratio <= 1.25, (
        f"a {TRUE_FWHM_PPM} ppm line measured {estimate.line_width_ppm:.5f} ppm "
        f"({ratio:.2f}x) at 16 points per FWHM. Smoothing broadens the measured "
        f"width, so this drifts high as sampling density falls; a large ratio "
        f"here means the width is reporting the smoothing kernel."
    )
    assert estimate.line_width_hz == pytest.approx(
        estimate.line_width_ppm * FIELD_MHZ, rel=1e-9
    ), "width_hz is width_ppm x field, the convention gsd.py:1150 already uses"


def test_line_width_is_not_the_cluster_extent() -> None:
    """The two must never be conflated again: they differ by ~an order of magnitude."""
    estimate = _tallest_near(
        _infer_peak_estimates(_trace([6.0]), frequency_mhz=FIELD_MHZ), 6.0
    )
    assert estimate is not None
    assert estimate.line_width_ppm > 0.0
    assert estimate.width_ppm > 4.0 * estimate.line_width_ppm, (
        f"extent {estimate.width_ppm:.5f} ppm vs line width "
        f"{estimate.line_width_ppm:.5f} ppm. A comparison written against one "
        f"of these is wrong by that factor if it is fed the other."
    )


def test_line_width_hz_is_absent_when_the_field_is_unknown() -> None:
    """No fabricated Hz: a linewidth in Hz without a field is not a measurement."""
    estimate = _tallest_near(
        _infer_peak_estimates(_trace([6.0]), frequency_mhz=None), 6.0
    )
    assert estimate is not None
    assert estimate.line_width_hz is None
    assert estimate.line_width_ppm > 0.0, "ppm survives; only the conversion is absent"


def test_line_width_rises_as_two_lines_move_apart() -> None:
    """The invariant the cluster extent does NOT satisfy.

    Two equal Lorentzians lose their dip at d = FWHM/sqrt(3) = 0.577 FWHM, so
    below that the picker necessarily sees one line and the only evidence that
    there are two is that the one line is too wide. That evidence has to grow
    with separation, monotonically, or it cannot be read as evidence at all.
    """
    widths = []
    for separation in [round(0.1 * step, 2) for step in range(10)]:
        estimate = _pair_at(separation)
        assert estimate is not None, f"no signal found at {separation} FWHM"
        widths.append((separation, estimate.line_width_ppm))

    # strict=False is deliberate: this pairs CONSECUTIVE entries, so the two
    # sequences differ in length by one by construction.
    for (prev_sep, prev), (sep, current) in zip(widths, widths[1:], strict=False):
        assert current >= prev - 1e-9, (
            f"line width fell from {prev:.5f} to {current:.5f} ppm as the pair "
            f"moved from {prev_sep} to {sep} FWHM apart. A width that is not "
            f"monotonic in separation cannot support a claim about merging."
        )
    assert widths[-1][1] > 1.3 * widths[0][1], (
        f"a pair 0.9 FWHM apart measured {widths[-1][1]:.5f} ppm against "
        f"{widths[0][1]:.5f} for coincident lines: too little to be usable."
    )


def test_widths_are_index_aligned_with_the_reported_peaks() -> None:
    """The arrays are read positionally, so a length mismatch is silent corruption."""
    estimates = _infer_peak_estimates(
        _trace([6.0, 4.0, 2.0]), frequency_mhz=FIELD_MHZ
    )
    peaks, meta = _estimates_to_peaks(estimates)
    assert peaks
    assert len(meta["line_widths_ppm"]) == len(peaks)
    assert len(meta["line_widths_hz"]) == len(peaks)
    assert all(width > 0.0 for width in meta["line_widths_ppm"])
    assert all(width is not None for width in meta["line_widths_hz"])
