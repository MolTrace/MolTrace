"""Full-resolution synthetic acquisitions with known lines, for calibrating the
peak detector.

**Why this exists.** The corpus the detector was tuned against
(``tests/fixtures/gsd_prompt3_validation/``) holds DECIMATED traces — measured at
a median 1.5 points per linewidth, against 29.4 for an acquisition read straight
off an instrument. A 19x difference, filtered identically. Over-picking cannot
appear in data that carries barely one point per line, so the corpus was
structurally incapable of showing the defect it was meant to guard.

**Why synthetic, and not more real spectra.** Calibrating a DETECTOR is asking
where the line between signal and noise should sit, and that question needs data
where the answer is known. A real acquisition's true peak list is itself an
opinion — the two curated peak lists in this repository came from different
processing than MolTrace applies, so comparing against them measures the
disagreement between two pipelines rather than the detector's accuracy. Planting
lines of known height in noise of known width is the only version of the question
with an arithmetic answer.

Real acquisitions remain the check that the calibration TRANSFERS. They are not
the arbiter.

**Every parameter below is measured, not chosen.** Across the 23 acquisitions in
this repository:

| property | 13C | 1H |
|---|---|---|
| Hz per point (median) | 0.297 | 0.072 |
| FWHM Hz (p10 / median / p90) | 0.99 / 3.23 / 6.46 | 1.10 / 2.08 / 6.04 |
| points per linewidth (median) | ~11 | ~29 |

with 8,192 to 524,288 points, fields from 62.9 to 700.2 MHz, and a tallest-peak
to noise ratio spanning 8 to 30,541 (median 241).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum

#: Measured from the acquisitions in this repository, model-free: walk down from
#: each of the five tallest well-separated apexes until half height. Fitted
#: widths were not used — this platform's fitted half-widths are known to be
#: mis-scaled against their own bound, so they cannot calibrate anything.
MEASURED_FWHM_HZ = {"13C": (0.99, 3.23, 6.46), "1H": (1.10, 2.08, 6.04)}

#: Median Hz per point, measured. Sets points-per-linewidth, which is the whole
#: property the old corpus lacked.
MEASURED_HZ_PER_POINT = {"13C": 0.297, "1H": 0.072}


@dataclass(frozen=True)
class PlantedLine:
    """A line put into the spectrum on purpose, with its truth recorded."""

    position_ppm: float
    #: Apex height in units of the noise sigma. The quantity a detection
    #: threshold is actually deciding about.
    snr: float
    fwhm_hz: float


@dataclass(frozen=True)
class SyntheticAcquisition:
    spectrum: NMRSpectrum
    lines: tuple[PlantedLine, ...]
    noise_sigma: float
    label: str

    def lines_above(self, snr: float) -> tuple[PlantedLine, ...]:
        return tuple(line for line in self.lines if line.snr >= snr)


def _lorentzian(x_hz: np.ndarray, centre_hz: float, fwhm_hz: float) -> np.ndarray:
    """An NMR line is Lorentzian. A Gaussian would make the tails too thin and
    flatter the detector, because most false positives live in the tails."""
    half = fwhm_hz / 2.0
    return (half * half) / ((x_hz - centre_hz) ** 2 + half * half)


def synthesise(
    *,
    nucleus: str,
    field_mhz: float,
    points: int,
    sweep_ppm: tuple[float, float],
    snrs: list[float],
    fwhm_hz: float,
    noise_sigma: float = 1.0,
    seed: int = 0,
    label: str = "",
) -> SyntheticAcquisition:
    """One acquisition with lines of known height in noise of known width."""
    rng = np.random.default_rng(seed)
    high, low = max(sweep_ppm), min(sweep_ppm)
    ppm = np.linspace(high, low, points)
    hz = ppm * field_mhz

    # Lines spread across the middle 80% so none sits on an edge, where a
    # detector's window runs out and the result would measure edge handling
    # rather than detection.
    span = high - low
    positions = np.linspace(low + span * 0.1, high - span * 0.1, len(snrs))

    intensity = rng.normal(0.0, noise_sigma, points)
    planted = []
    for centre_ppm, snr in zip(positions, snrs, strict=True):
        intensity += snr * noise_sigma * _lorentzian(hz, centre_ppm * field_mhz, fwhm_hz)
        planted.append(PlantedLine(position_ppm=float(centre_ppm), snr=float(snr), fwhm_hz=fwhm_hz))

    spectrum = NMRSpectrum(
        data=intensity,
        ppm_axis=ppm,
        nucleus=nucleus,
        field_mhz=field_mhz,
    )
    return SyntheticAcquisition(
        spectrum=spectrum,
        lines=tuple(planted),
        noise_sigma=noise_sigma,
        label=label or f"{nucleus}-{field_mhz:.0f}MHz-{points}pt",
    )


#: The SNR ladder every acquisition carries.
#:
#: Spans the decision. Below 3 is under any conventional limit of detection and
#: should NOT be found; 3 to 10 is detectable but not quantifiable; above 10 is a
#: line a chemist would expect in the table, and missing one is the failure the
#: original 13C tuning existed to prevent.
SNR_LADDER = [2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 25.0, 50.0, 100.0, 500.0, 2000.0]


def synthesise_clustered(
    *,
    nucleus: str,
    field_mhz: float,
    points: int,
    sweep_ppm: tuple[float, float],
    fwhm_hz: float,
    noise_sigma: float = 1.0,
    seed: int = 0,
    label: str = "",
) -> SyntheticAcquisition:
    """Lines that SIT ON EACH OTHER'S SHOULDERS, which well-separated lines cannot test.

    Added after the separated corpus gave a clean answer that real data
    contradicted. Detection is prominence-based, and prominence is the height of
    a peak above the saddle joining it to a taller neighbour — so a tall line
    beside a taller one can be dropped by a threshold that its own height would
    sail past. Measured on real acquisitions: of 75 peaks a corrected threshold
    dropped, 72 sat below 10 sigma and were noise, but three did not, and all
    three were shoulders.

    A corpus of isolated lines cannot see that case, so it reports a precision
    win with no cost and is wrong. This plants each cluster at a real coupling
    spacing on the shoulder of a dominant line.
    """
    rng = np.random.default_rng(seed)
    high, low = max(sweep_ppm), min(sweep_ppm)
    ppm = np.linspace(high, low, points)
    hz = ppm * field_mhz
    intensity = rng.normal(0.0, noise_sigma, points)
    planted: list[PlantedLine] = []

    span = high - low
    # Each group: a dominant line, then partners a few linewidths away at
    # descending height — the shape of a real multiplet beside a solvent line.
    for group, (dominant_snr, partner_snrs) in enumerate(
        [(2000.0, [40.0, 15.0]), (500.0, [25.0, 12.0]), (100.0, [30.0, 11.0])]
    ):
        centre = low + span * (0.25 + 0.25 * group)
        for offset_widths, snr in [(0.0, dominant_snr)] + [
            ((index + 1) * 1.5, snr) for index, snr in enumerate(partner_snrs)
        ]:
            position = centre + (offset_widths * fwhm_hz) / field_mhz
            intensity += snr * noise_sigma * _lorentzian(hz, position * field_mhz, fwhm_hz)
            planted.append(
                PlantedLine(position_ppm=float(position), snr=float(snr), fwhm_hz=fwhm_hz)
            )

    return SyntheticAcquisition(
        spectrum=NMRSpectrum(data=intensity, ppm_axis=ppm, nucleus=nucleus, field_mhz=field_mhz),
        lines=tuple(planted),
        noise_sigma=noise_sigma,
        label=label or f"clustered-{nucleus}-{field_mhz:.0f}MHz",
    )


def default_corpus(seed: int = 20260827) -> list[SyntheticAcquisition]:
    """Acquisitions spanning the measured parameter ranges.

    Deliberately includes the resolutions the old corpus lacked: the point of
    this corpus is that points-per-linewidth is the axis along which the detector
    was never tested.
    """
    corpus: list[SyntheticAcquisition] = []
    cases = [
        # nucleus, field, points, sweep, fwhm  -- narrow, median and broad lines
        ("13C", 100.6, 65536, (200.0, -10.0), 0.99),
        ("13C", 100.6, 65536, (200.0, -10.0), 3.23),
        ("13C", 150.9, 131072, (200.0, -10.0), 6.46),
        ("13C", 62.9, 8192, (200.0, -10.0), 3.23),      # coarse, like the old corpus
        ("13C", 100.7, 524288, (250.0, -40.0), 3.23),   # the largest seen here
        ("1H", 400.0, 65536, (12.0, -1.0), 1.10),
        ("1H", 400.0, 65536, (12.0, -1.0), 2.08),
        ("1H", 700.2, 131072, (12.0, -1.0), 6.04),
        ("1H", 250.1, 16384, (12.0, -1.0), 2.08),       # coarse
    ]
    for index, (nucleus, field, points, sweep, fwhm) in enumerate(cases):
        corpus.append(
            synthesise(
                nucleus=nucleus,
                field_mhz=field,
                points=points,
                sweep_ppm=sweep,
                snrs=SNR_LADDER,
                fwhm_hz=fwhm,
                seed=seed + index,
                label=f"{nucleus}-{field:.0f}MHz-{points}pt-fwhm{fwhm:g}Hz",
            )
        )

    # Shoulders. Without these the corpus reports a precision win with no cost,
    # which real acquisitions contradict.
    for index, (nucleus, field, points, sweep, fwhm) in enumerate(
        [
            ("13C", 100.6, 65536, (200.0, -10.0), 3.23),
            ("13C", 150.9, 131072, (200.0, -10.0), 6.46),
            ("1H", 400.0, 65536, (12.0, -1.0), 2.08),
        ]
    ):
        corpus.append(
            synthesise_clustered(
                nucleus=nucleus,
                field_mhz=field,
                points=points,
                sweep_ppm=sweep,
                fwhm_hz=fwhm,
                seed=seed + 100 + index,
                label=f"clustered-{nucleus}-{field:.0f}MHz-fwhm{fwhm:g}Hz",
            )
        )
    return corpus


def points_per_linewidth(acquisition: SyntheticAcquisition) -> float:
    x = np.asarray(acquisition.spectrum.ppm_axis, dtype=float)
    step_hz = float(np.median(np.abs(np.diff(x)))) * acquisition.spectrum.field_mhz
    return acquisition.lines[0].fwhm_hz / step_hz if step_hz > 0 else float("nan")


@dataclass(frozen=True)
class DetectionScore:
    """What the detector found, against what was planted."""

    found_by_band: dict[str, tuple[int, int]]
    false_positives: int
    picked: int
    planted: int

    def recall(self, band: str) -> float:
        found, total = self.found_by_band.get(band, (0, 0))
        return found / total if total else float("nan")


#: SNR bands the score is reported in, and what each one means.
#:
#: Below 3 sigma is under any conventional limit of detection: finding lines
#: there is picking noise. 3-10 is detectable but NOT quantifiable — the
#: distinction this platform draws elsewhere and must draw here. Above 10 is a
#: line a chemist expects in the table, and missing one is the failure the 13C
#: tuning was written to prevent.
BANDS: tuple[tuple[str, float, float], ...] = (
    ("below-detection <3", 0.0, 3.0),
    ("detectable 3-10", 3.0, 10.0),
    ("quantifiable >=10", 10.0, float("inf")),
)


def score_detection(
    acquisition: SyntheticAcquisition,
    picked_ppm: list[float],
    *,
    tolerance_linewidths: float = 1.0,
) -> DetectionScore:
    """Match what was picked against what was planted.

    Tolerance is expressed in LINEWIDTHS rather than ppm, because a fixed ppm
    window is a different physical distance at every field and would score a
    700 MHz acquisition on a different question from a 63 MHz one.
    """
    field = acquisition.spectrum.field_mhz
    tol_ppm = (acquisition.lines[0].fwhm_hz * tolerance_linewidths) / field if field else 0.01
    picked = np.asarray(sorted(picked_ppm), dtype=float)

    matched_picks: set[int] = set()
    by_band: dict[str, tuple[int, int]] = {}
    for name, low, high in BANDS:
        in_band = [line for line in acquisition.lines if low <= line.snr < high]
        found = 0
        for line in in_band:
            if picked.size == 0:
                continue
            distances = np.abs(picked - line.position_ppm)
            nearest = int(np.argmin(distances))
            if distances[nearest] <= tol_ppm:
                found += 1
                matched_picks.add(nearest)
        by_band[name] = (found, len(in_band))

    return DetectionScore(
        found_by_band=by_band,
        false_positives=int(picked.size - len(matched_picks)),
        picked=int(picked.size),
        planted=len(acquisition.lines),
    )
