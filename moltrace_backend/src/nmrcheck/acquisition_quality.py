"""Whether the acquisition supports quantitative integration.

Integrals are reported as proton counts, but a 1H spectrum only yields
quantitative integrals when it was ACQUIRED for that purpose. Two effects
dominate:

* **Incomplete relaxation.** Signal recovery between transients follows
  1 - exp(-recycle/T1). With a short recycle delay, slowly relaxing protons
  (isolated aromatics, exchangeables) recover less than fast-relaxing ones, so
  their integrals are systematically low. The usual qNMR requirement is a
  recycle time of at least 5·T1, which for typical small-molecule 1H T1 of
  1-5 s means roughly 25-30 s.
* **Solvent suppression and selective excitation.** Presaturation, WET and
  NOESY-presat sequences attenuate signal near the irradiated frequency, so
  resonances close to the suppressed solvent line lose intensity that has
  nothing to do with proton count.

Nothing in the pipeline checked either. This module reports a level plus the
reasons behind it, and deliberately returns ``unknown`` rather than guessing
when the parameters are absent: claiming an unverified spectrum is quantitative
is worse than admitting the acquisition is unknown.

T1 is not measured here — no routine dataset contains it — so the strongest
claim available is that the parameters are CONSISTENT with quantitative
integration, which is how the reasons are phrased.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

# Integration bias is judged from the Ernst steady state rather than from a
# flat recycle-time threshold, because the flip angle matters as much as the
# delay. For a pulse of flip angle a repeated every T seconds, the steady-state
# signal of a spin with relaxation time T1 is
#
#     S(T1)  ∝  sin(a) · (1 - E) / (1 - E·cos(a)),      E = exp(-T / T1)
#
# What corrupts an integral is not saturation itself but DIFFERENTIAL
# saturation: fast- and slow-relaxing protons losing different fractions. So
# the figure of merit is the ratio of S between the extremes of a plausible
# small-molecule 1H T1 range. A 90 degree pulse needs ~5·T1 to bring that ratio
# near 1, which is where the familiar "25-30 s" rule comes from; a 30 degree
# pulse — the standard routine experiment, zg30 — reaches the same fidelity far
# sooner, and judging it by the 90 degree rule condemns almost every real
# spectrum ever recorded.
T1_FAST_S = 0.5
T1_SLOW_S = 5.0

# Tolerated ratio S(fast)/S(slow). 2% is a genuinely quantitative integral;
# beyond 10% the integrals reflect relaxation as much as proton count.
QUANTITATIVE_BIAS_RATIO = 1.02
SEMI_QUANTITATIVE_BIAS_RATIO = 1.10

# Flip angle inferred from the pulse-program name when it is not supplied.
# Bruker names the angle in the sequence: zg30 is 30 degrees, zg is a 90.
_DEFAULT_PULSE_ANGLE_DEG = 90.0

# Scans below this give poor SNR on minor components; integrals of small peaks
# carry large relative error even when relaxation is complete.
MIN_SCANS_FOR_MINOR_COMPONENTS = 8

LEVEL_QUANTITATIVE = "quantitative"
LEVEL_SEMI = "semi_quantitative"
LEVEL_NOT = "not_quantitative"
LEVEL_UNKNOWN = "unknown"

# Pulse programs that distort integrals. Substring match on the lowercased
# PULPROG string.
_SUPPRESSION_PULSE_PROGRAMS = (
    "pr",  # zgpr, noesypr1d, ...
    "presat",
    "wet",
    "watergate",
    "excsculp",
    "p3919",
)
_SELECTIVE_PULSE_PROGRAMS = ("sel", "cpmg", "t1ir", "t2", "diff", "led", "bpp")


@dataclass(frozen=True)
class AcquisitionQuality:
    level: str
    reasons: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def integrals_are_quantitative(self) -> bool:
        return self.level == LEVEL_QUANTITATIVE

    def to_payload(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "reasons": list(self.reasons),
            "parameters": dict(self.parameters),
        }


def pulse_angle_from_program(pulse_program: str | None) -> float:
    """Flip angle in degrees, read from the Bruker pulse-program name.

    ``zg30`` is a 30 degree read pulse, ``zg60`` a 60, plain ``zg`` a 90.
    Unrecognised sequences fall back to 90 degrees, which is the conservative
    choice: it demands the longest recycle delay.
    """
    if not pulse_program:
        return _DEFAULT_PULSE_ANGLE_DEG
    match = re.search(r"(\d{2,3})\s*$", pulse_program.strip().lower())
    if match:
        angle = float(match.group(1))
        if 1.0 <= angle <= 180.0:
            return angle
    return _DEFAULT_PULSE_ANGLE_DEG


def steady_state_response(*, recycle_s: float, t1_s: float, angle_deg: float) -> float:
    """Ernst steady-state signal for one spin, in arbitrary units."""
    angle = math.radians(angle_deg)
    e = math.exp(-recycle_s / t1_s) if t1_s > 0 else 0.0
    denominator = 1.0 - e * math.cos(angle)
    if denominator <= 0:
        return 0.0
    return math.sin(angle) * (1.0 - e) / denominator


def differential_saturation_ratio(*, recycle_s: float, angle_deg: float) -> float:
    """S(fast-relaxing) / S(slow-relaxing) across the plausible 1H T1 range.

    1.0 means both relax fully between transients and their integrals are
    directly comparable; larger values mean slowly relaxing protons integrate
    low purely because of the acquisition.
    """
    fast = steady_state_response(recycle_s=recycle_s, t1_s=T1_FAST_S, angle_deg=angle_deg)
    slow = steady_state_response(recycle_s=recycle_s, t1_s=T1_SLOW_S, angle_deg=angle_deg)
    if slow <= 0:
        return float("inf")
    return fast / slow


def acquisition_time_s(*, td: float | None, sw_hz: float | None) -> float | None:
    """Acquisition time from time-domain points and sweep width.

    Bruker TD counts real+imaginary points, so the complex point count is TD/2
    and AQ = (TD/2)/SW.
    """
    if not td or not sw_hz or td <= 0 or sw_hz <= 0:
        return None
    return (float(td) / 2.0) / float(sw_hz)


def assess_1h_acquisition(
    *,
    relaxation_delay_s: float | None,
    td: float | None,
    sw_hz: float | None,
    scans: int | None = None,
    pulse_program: str | None = None,
    pulse_angle_deg: float | None = None,
) -> AcquisitionQuality:
    """Classify how far the acquisition supports quantitative integration."""
    aq = acquisition_time_s(td=td, sw_hz=sw_hz)
    recycle = (
        relaxation_delay_s + aq
        if relaxation_delay_s is not None and aq is not None
        else None
    )
    parameters: dict[str, Any] = {
        "relaxation_delay_s": relaxation_delay_s,
        "acquisition_time_s": round(aq, 4) if aq is not None else None,
        "recycle_time_s": round(recycle, 4) if recycle is not None else None,
        "scans": scans,
        "pulse_program": pulse_program,
    }
    reasons: list[str] = []

    program = (pulse_program or "").strip().lower()
    if program:
        if any(token in program for token in _SUPPRESSION_PULSE_PROGRAMS):
            reasons.append(
                f"Pulse program '{pulse_program}' applies solvent suppression, which "
                "attenuates resonances near the irradiated frequency; their integrals "
                "do not reflect proton count."
            )
            return AcquisitionQuality(LEVEL_NOT, reasons, parameters)
        if any(token in program for token in _SELECTIVE_PULSE_PROGRAMS):
            reasons.append(
                f"Pulse program '{pulse_program}' is selective or relaxation-encoded "
                "rather than a simple pulse-acquire, so signal amplitudes are not "
                "proportional to proton count."
            )
            return AcquisitionQuality(LEVEL_NOT, reasons, parameters)

    if recycle is None:
        missing = []
        if relaxation_delay_s is None:
            missing.append("relaxation delay (D1)")
        if aq is None:
            missing.append("acquisition time (TD/SW)")
        reasons.append(
            "Cannot confirm quantitative acquisition: "
            + " and ".join(missing)
            + " not reported. Integrals are shown as relative areas."
        )
        return AcquisitionQuality(LEVEL_UNKNOWN, reasons, parameters)

    if scans is not None and scans < MIN_SCANS_FOR_MINOR_COMPONENTS:
        reasons.append(
            f"Only {scans} scan(s): minor-component integrals carry large relative "
            "error even when relaxation is complete."
        )

    angle = (
        float(pulse_angle_deg)
        if pulse_angle_deg is not None
        else pulse_angle_from_program(pulse_program)
    )
    parameters["pulse_angle_deg"] = angle
    ratio = differential_saturation_ratio(recycle_s=recycle, angle_deg=angle)
    parameters["differential_saturation_ratio"] = (
        round(ratio, 4) if math.isfinite(ratio) else None
    )

    bias_pct = (ratio - 1.0) * 100.0 if math.isfinite(ratio) else float("inf")
    summary = (
        f"Recycle time {recycle:.1f} s at a {angle:.0f} degree pulse. Across a "
        f"{T1_FAST_S:g}-{T1_SLOW_S:g} s T1 range that leaves "
    )

    if ratio <= QUANTITATIVE_BIAS_RATIO:
        reasons.insert(
            0,
            summary
            + f"about {bias_pct:.0f}% differential saturation, so integrals may be "
            "read as proton counts. T1 was not measured.",
        )
        return AcquisitionQuality(LEVEL_QUANTITATIVE, reasons, parameters)

    if ratio <= SEMI_QUANTITATIVE_BIAS_RATIO:
        reasons.insert(
            0,
            summary
            + f"about {bias_pct:.0f}% differential saturation: slowly relaxing "
            "protons integrate low by roughly that much.",
        )
        return AcquisitionQuality(LEVEL_SEMI, reasons, parameters)

    reasons.insert(
        0,
        summary
        + (
            f"about {bias_pct:.0f}% differential saturation"
            if math.isfinite(bias_pct)
            else "near-total saturation"
        )
        + ". Integrals reflect relaxation rates as much as proton counts and should "
        "not be read as proton ratios.",
    )
    return AcquisitionQuality(LEVEL_NOT, reasons, parameters)
