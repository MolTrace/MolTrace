"""One pivot convention, so reported phase angles mean something.

`apply_phase` ramps the first-order term from a pivot index. Three conventions
coexisted: the nmrglue path and the no-op path reported pivot 0, the grid
fallback searched and reported ``argmax(|real|)``, and manual mode silently used
``size // 2`` while reporting it.

The consequence is that a reported ``(p0, p1)`` pair did not describe the
spectrum it came from: replaying an auto result through manual mode applied the
same angles about a different pivot and produced a different spectrum. Angles a
caller cannot replay are not a usable manual control, and they are what a
reviewer reads off the report.

Pivot 0 is the convention, matching nmrglue's ``ps`` and the two paths that
already reported it.
"""

from __future__ import annotations

import numpy as np

from nmrcheck.fid import _auto_phase_spectrum, apply_phase


def _misphased(n: int = 4096, p0: float = 37.0, p1: float = -45.0) -> np.ndarray:
    """Lorentzian lines, then a known phase error applied about pivot 0."""
    x = np.arange(n, dtype=float)
    spectrum = np.zeros(n, dtype=np.complex128)
    for centre, amplitude in ((900.0, 1.0), (1800.0, 0.6), (3000.0, 0.35)):
        half_width = 6.0
        spectrum += amplitude * (half_width / ((x - centre) + 1j * half_width))
    return apply_phase(spectrum, p0=p0, p1=p1, pivot=0)


class TestPhasePivotConvention:
    def test_manual_mode_uses_and_reports_pivot_zero(self) -> None:
        spectrum = _misphased()
        _, detail, _ = _auto_phase_spectrum(
            spectrum, mode="manual", phase_p0=12.0, phase_p1=-8.0
        )
        assert detail["pivot_index"] == 0

    def test_manual_mode_applies_the_pivot_it_reports(self) -> None:
        """The reported pivot has to be the one actually used."""
        spectrum = _misphased()
        phased, detail, _ = _auto_phase_spectrum(
            spectrum, mode="manual", phase_p0=12.0, phase_p1=-8.0
        )
        expected = apply_phase(spectrum, p0=12.0, p1=-8.0, pivot=int(detail["pivot_index"]))
        np.testing.assert_allclose(np.real(phased), np.real(expected), rtol=0, atol=1e-9)

    def test_an_auto_result_round_trips_through_manual(self) -> None:
        """The point of the whole thing: replay the reported angles, get the
        same spectrum back. This is what makes a manual phase control possible
        and what makes the reported numbers honest."""
        spectrum = _misphased()
        auto, detail, _ = _auto_phase_spectrum(spectrum, mode="auto")

        replayed, _, _ = _auto_phase_spectrum(
            spectrum,
            mode="manual",
            phase_p0=float(detail["zero_order_degrees"]),
            phase_p1=float(detail["first_order_degrees"]),
        )
        # Rounded to 3 dp in the report, so compare on the scale of the trace
        # rather than demanding bit equality.
        scale = float(np.max(np.abs(np.real(auto)))) or 1.0
        np.testing.assert_allclose(
            np.real(replayed) / scale, np.real(auto) / scale, rtol=0, atol=2e-3
        )

    def test_every_path_reports_the_same_convention(self) -> None:
        spectrum = _misphased()
        for mode in ("none", "manual", "auto"):
            _, detail, _ = _auto_phase_spectrum(
                spectrum, mode=mode, phase_p0=5.0, phase_p1=3.0
            )
            assert detail["pivot_index"] == 0, mode
