"""The noise width the peak detector measures its threshold against.

Written BEFORE the fix it describes, and it failed when written. The estimator
decides whether a bump is a peak, so a bias in it is a bias in every peak list
this platform produces.

**The arbiter is synthetic noise of a sigma we chose**, not another estimator.
Comparing two estimates of an unknown quantity says which is larger, never which
is right; generating noise of known width and asking what each one reports is the
only version of the question with an answer.
"""

from __future__ import annotations

import numpy as np
import pytest

from moltrace.spectroscopy.peaks.gsd import _detection_noise

#: How far from the true sigma an estimator may sit and still be usable.
#:
#: From the measured spread rather than chosen for roundness. Across peak
#: densities from 0% to 10% of points, a whole-spectrum MAD reads 0.999 to 1.144
#: and the reflected estimator reads 0.998 to 1.080. The estimator this replaced
#: read 0.589 to 0.624 — never inside any tolerance that admits the other two.
_TOLERANCE = 0.20


def _noisy(seed: int, *, peak_fraction: float = 0.0, sigma: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = 65536
    y = rng.normal(0.0, sigma, n)
    count = int(n * peak_fraction)
    if count:
        y[rng.choice(n, count, replace=False)] += rng.uniform(20.0, 200.0, count) * sigma
    return y


def _mad(y: np.ndarray) -> float:
    centred = y - float(np.median(y))
    return 1.4826 * float(np.median(np.abs(centred - float(np.median(centred)))))


@pytest.mark.parametrize("sigma", [0.5, 1.0, 40.0])
def test_the_13c_estimator_recovers_a_sigma_it_was_given(sigma: float) -> None:
    """On peak-free noise it must report the width that is actually there.

    The whole defect in one assertion. The estimator took the lower half of the
    sorted values — peak-free, correctly — then applied the MAD constant for a
    SYMMETRIC distribution to a half of one. On pure noise with no peaks at all
    it returned 0.59x the truth, so the height gate sat at 1.4x MAD instead of
    3.5x, below any conventional limit of detection.
    """
    for seed in range(6):
        y = _noisy(seed, sigma=sigma)
        estimate = _detection_noise(y, _mad(y), "13C")
        assert estimate == pytest.approx(sigma, rel=_TOLERANCE), (
            f"peak-free noise of width {sigma} measured as {estimate:.4f} "
            f"({estimate / sigma:.2f}x) — the threshold is scaled by that factor"
        )


@pytest.mark.parametrize("peak_fraction", [0.001, 0.01, 0.05])
def test_the_estimator_is_not_dragged_upward_by_the_peaks(peak_fraction: float) -> None:
    """The property the lower-half trick exists for, and it survives the fix.

    Analyte lines inflate a whole-spectrum MAD, which raises the threshold and
    culls minor 13C lines. Staying peak-free is the point; being biased was not.
    """
    for seed in range(6):
        y = _noisy(seed, peak_fraction=peak_fraction)
        estimate = _detection_noise(y, _mad(y), "13C")
        assert estimate == pytest.approx(1.0, rel=_TOLERANCE), (
            f"with peaks on {peak_fraction:.1%} of points the estimate was {estimate:.4f}"
        )


def test_the_estimator_beats_a_whole_spectrum_mad_where_it_claims_to() -> None:
    """It must be BETTER than what it replaced, not merely different."""
    for seed in range(6):
        y = _noisy(seed, peak_fraction=0.05)
        plain = _mad(y)
        estimate = _detection_noise(y, plain, "13C")
        assert abs(estimate - 1.0) <= abs(plain - 1.0) + 1e-9, (
            f"the peak-free estimate ({estimate:.4f}) is further from the truth "
            f"than a whole-spectrum MAD ({plain:.4f})"
        )


def test_a_1h_spectrum_still_uses_the_whole_spectrum_estimate() -> None:
    """Unchanged on purpose: 1H detects adequately, and a lower threshold there
    over-detects multiplet components absent from curated reference lists."""
    y = _noisy(3, peak_fraction=0.01)
    plain = _mad(y)
    assert _detection_noise(y, plain, "1H") == plain


def test_a_degenerate_baseline_falls_back_rather_than_returning_zero() -> None:
    """A clipped or flat-lined baseline has a zero-width peak-free half, and a
    zero threshold makes every bump a peak."""
    flat = np.zeros(4096)
    flat[2048] = 1000.0
    assert _detection_noise(flat, 1.0, "13C") > 0.0
