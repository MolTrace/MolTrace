"""Process-capability & SPC trending engine (Prompt 9).

Two deterministic primitives plus a trending layer:

* :func:`calculate_capability_indices` — Cp, Cpk, Pp, Ppk and the Taguchi Cpm for a set of
  individual measurements against one- or two-sided specification limits. The short-term ("within")
  sigma used by Cp/Cpk/Cpm is the individuals/moving-range estimate sigma = MR-bar / d2 (d2 = 1.128
  for moving ranges of consecutive pairs); the long-term ("overall") sigma used by Pp/Ppk is the
  Bessel-corrected sample standard deviation. Interpretation banding follows the convention
  Cpk >= 1.33 capable, 1.00 <= Cpk < 1.33 marginal, Cpk < 1.00 not capable.
* :func:`detect_spc_signals` — the eight Shewhart run/zone rules (Western Electric / Nelson /
  Montgomery rule sets), plus CUSUM and EWMA as alternative detectors for small sustained shifts.
* :func:`analyze_series` — wraps both over a time-ordered measurement series and raises trending
  alerts (drift, shift, marginal capability, approaching-limit) **before** a point goes
  out-of-specification, with adapters that consume the existing release-test structures.

The statistics are version-pinned, citable, and deterministic: every constant traces to a published
SQC reference (Montgomery, *Introduction to Statistical Quality Control*; Western Electric SQC
Handbook 1956; Nelson, *JQT* 1984). This is decision support — a qualified person reviews the
signals; the engine never dispositions a batch.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # integration types — duck-typed at runtime, imported only for checking
    from moltrace.regulatory.quality.oos_investigation import AnalyticalResult, SpecificationLimit
    from moltrace.regulatory.specifications.q6a_builder import BatchResult

__all__ = [
    "AlertSeverity",
    "CapabilityIndices",
    "CapabilityRating",
    "MeasurementPoint",
    "MeasurementSeries",
    "SPCSignal",
    "TrendAlert",
    "TrendingReport",
    "analyze_series",
    "calculate_capability_indices",
    "capability_for_specification",
    "cusum_signals",
    "cusum_statistics",
    "detect_spc_signals",
    "ewma_signals",
    "ewma_statistics",
    "series_from_analytical_results",
    "series_from_batch_results",
]

# --------------------------------------------------------------------------- #
# Constants (version-pinned SQC reference values)
# --------------------------------------------------------------------------- #
# d2 unbiasing constants by subgroup size (Montgomery SQC App. VI / AIAG SPC / ASTM E2587).
_D2: dict[int, float] = {
    2: 1.128,
    3: 1.693,
    4: 2.059,
    5: 2.326,
    6: 2.534,
    7: 2.704,
    8: 2.847,
    9: 2.970,
    10: 3.078,
}
_D2_MR = _D2[2]  # moving range of consecutive pairs uses the n=2 constant

_CPK_CAPABLE = 1.33  # >= capable
_CPK_MARGINAL = 1.00  # >= marginal, otherwise not capable
_MIN_STUDY_N = 25  # AIAG: fewer individuals -> wide CIs; emit a low-sample warning

# Default CUSUM / EWMA designs (Montgomery): ARL0 ~ 465 / standard small-shift sensitivity.
_CUSUM_K = 0.5  # reference value, in sigma units
_CUSUM_H = 5.0  # decision interval, in sigma units
_EWMA_LAMBDA = 0.2
_EWMA_L = 3.0


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class CapabilityRating(StrEnum):
    """Interpretation banding for a capability index."""

    CAPABLE = "capable"  # Cpk >= 1.33
    MARGINAL = "marginal"  # 1.00 <= Cpk < 1.33
    NOT_CAPABLE = "not_capable"  # Cpk < 1.00
    UNDEFINED = "undefined"  # index could not be computed


class AlertSeverity(StrEnum):
    """Severity of a trending alert."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# Capability indices
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CapabilityIndices:
    """Process-capability and -performance indices for a measurement set.

    ``cp``/``cpk``/``cpm`` use the within (short-term) sigma; ``pp``/``ppk`` use the overall
    (long-term) sigma. A value is ``None`` when the specification is one-sided (Cp/Pp/Cpm need both
    limits) or the target is absent (Cpm); ``inf``/``-inf`` arise only with zero variation.
    """

    n: int
    mean: float
    sigma_within: float
    sigma_overall: float
    usl: float | None
    lsl: float | None
    target: float | None
    cp: float | None
    cpk: float | None
    cpu: float | None
    cpl: float | None
    pp: float | None
    ppk: float | None
    cpm: float | None
    rating: CapabilityRating
    interpretation: str
    warnings: tuple[str, ...] = ()

    @property
    def is_capable(self) -> bool:
        """True when Cpk meets the >= 1.33 capability threshold."""

        return self.cpk is not None and not math.isnan(self.cpk) and self.cpk >= _CPK_CAPABLE

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "mean": self.mean,
            "sigma_within": self.sigma_within,
            "sigma_overall": self.sigma_overall,
            "usl": self.usl,
            "lsl": self.lsl,
            "target": self.target,
            "cp": self.cp,
            "cpk": self.cpk,
            "cpu": self.cpu,
            "cpl": self.cpl,
            "pp": self.pp,
            "ppk": self.ppk,
            "cpm": self.cpm,
            "rating": self.rating.value,
            "interpretation": self.interpretation,
            "warnings": list(self.warnings),
        }


def _safe_div(num: float, den: float) -> float:
    """Divide, mapping a zero denominator to a signed infinity (zero process variation)."""

    if den != 0:
        return num / den
    if num > 0:
        return math.inf
    if num < 0:
        return -math.inf
    return math.nan


def _moving_range_sigma(values: Sequence[float]) -> float:
    """Within/short-term sigma from the average moving range of consecutive pairs (d2 = 1.128)."""

    mrs = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
    return (sum(mrs) / len(mrs)) / _D2_MR if mrs else 0.0


def _subgroup_sigma(values: Sequence[float], k: int) -> tuple[float, str | None]:
    """Within sigma from R-bar/d2 over consecutive subgroups of size *k*."""

    if k not in _D2:
        raise ValueError(f"subgroup_size must be 2..10 (have a d2 constant), got {k}")
    n_groups = len(values) // k
    if n_groups < 1:
        raise ValueError(f"need at least one full subgroup of size {k}")
    ranges = []
    for g in range(n_groups):
        chunk = values[g * k : (g + 1) * k]
        ranges.append(max(chunk) - min(chunk))
    sigma = (sum(ranges) / len(ranges)) / _D2[k]
    warn = None
    if len(values) % k:
        warn = f"{len(values) % k} trailing measurement(s) dropped (not a full subgroup of {k})"
    return sigma, warn


def _rate(cpk: float | None) -> tuple[CapabilityRating, str]:
    if cpk is None or math.isnan(cpk):
        return CapabilityRating.UNDEFINED, "capability undefined (insufficient or degenerate data)"
    if cpk >= _CPK_CAPABLE:
        return CapabilityRating.CAPABLE, f"capable (Cpk {cpk:.3g} >= 1.33)"
    if cpk >= _CPK_MARGINAL:
        return CapabilityRating.MARGINAL, f"marginal (1.00 <= Cpk {cpk:.3g} < 1.33) — monitor"
    return CapabilityRating.NOT_CAPABLE, f"not capable (Cpk {cpk:.3g} < 1.00)"


def calculate_capability_indices(
    measurements: Sequence[float],
    usl: float | None,
    lsl: float | None,
    target: float | None = None,
    *,
    subgroup_size: int | None = None,
) -> CapabilityIndices:
    """Calculate the capability/performance indices for *measurements*.

        Cp  = (USL - LSL) / (6 * sigma_within)
        CPU = (USL - xbar)/(3*sigma_within);  CPL = (xbar - LSL)/(3*sigma_within)
        Cpk = min(CPU, CPL)
        Pp  = (USL - LSL) / (6 * sigma_overall)     # overall, not subgroup
        Ppk = min((USL - xbar)/(3*sigma_overall), (xbar - LSL)/(3*sigma_overall))
        Cpm = Cp / sqrt(1 + ((xbar - target)/sigma_within)^2)   # Taguchi index

    ``sigma_within`` is the individuals moving-range estimate MR-bar/1.128 by default, or the
    R-bar/d2 estimate over consecutive subgroups when ``subgroup_size`` is given. ``sigma_overall``
    is the sample SD (ddof=1). One-sided specs return ``None`` for the two-sided indices (Cp/Pp/Cpm)
    and report only the relevant one-sided index. Cpk >= 1.33 is capable, < 1.00 is not capable.
    """

    if usl is None and lsl is None:
        raise ValueError("at least one of usl/lsl is required")
    if usl is not None and lsl is not None and usl <= lsl:
        raise ValueError(f"usl ({usl}) must exceed lsl ({lsl})")
    values = list(measurements)
    n = len(values)
    if n < 2:
        raise ValueError("at least 2 measurements are required to estimate variation")

    warnings: list[str] = []
    mean = statistics.fmean(values)
    sigma_overall = statistics.stdev(values)  # ddof=1
    if subgroup_size is not None:
        sigma_within, sub_warn = _subgroup_sigma(values, subgroup_size)
        if sub_warn:
            warnings.append(sub_warn)
    else:
        sigma_within = _moving_range_sigma(values)

    if sigma_within == 0:
        warnings.append(
            "zero within-variation: short-term capability is undefined/infinite — verify "
            "measurement resolution (data may be rounded or constant)"
        )
    if n < _MIN_STUDY_N:
        warnings.append(
            f"low sample size (n={n} < {_MIN_STUDY_N}); capability estimates have wide confidence "
            "intervals (AIAG recommends >= 25 individuals)"
        )

    two_sided = usl is not None and lsl is not None
    cpu = _safe_div(usl - mean, 3 * sigma_within) if usl is not None else None
    cpl = _safe_div(mean - lsl, 3 * sigma_within) if lsl is not None else None
    ppu = _safe_div(usl - mean, 3 * sigma_overall) if usl is not None else None
    ppl = _safe_div(mean - lsl, 3 * sigma_overall) if lsl is not None else None

    cp = _safe_div(usl - lsl, 6 * sigma_within) if two_sided else None
    pp = _safe_div(usl - lsl, 6 * sigma_overall) if two_sided else None
    cpk = min(x for x in (cpu, cpl) if x is not None)
    ppk = min(x for x in (ppu, ppl) if x is not None)

    cpm: float | None = None
    if two_sided and target is not None:
        # Direct Taguchi form Cpm = (USL-LSL)/(6*sqrt(sigma^2 + (xbar-T)^2)) — algebraically equal
        # to Cp/sqrt(1+((xbar-T)/sigma)^2) when sigma>0, and the correct finite limit at zero
        # within-variation (where it converges to (USL-LSL)/(6*|xbar-T|), not infinity).
        cpm = _safe_div(usl - lsl, 6 * math.sqrt(sigma_within**2 + (mean - target) ** 2))
    elif target is not None and not two_sided:
        warnings.append("Cpm not reported: requires a two-sided specification")

    if not two_sided:
        warnings.append("one-sided specification: Cp/Pp/Cpm not applicable; one-sided Cpk reported")

    rating, interpretation = _rate(cpk)
    return CapabilityIndices(
        n=n,
        mean=mean,
        sigma_within=sigma_within,
        sigma_overall=sigma_overall,
        usl=usl,
        lsl=lsl,
        target=target,
        cp=cp,
        cpk=cpk,
        cpu=cpu,
        cpl=cpl,
        pp=pp,
        ppk=ppk,
        cpm=cpm,
        rating=rating,
        interpretation=interpretation,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# SPC signals — Shewhart run/zone rules
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SPCSignal:
    """A fired control-chart rule, with the offending point indices."""

    rule_number: int | None  # None for CUSUM/EWMA
    rule_name: str
    method: str  # "shewhart" | "cusum" | "ewma"
    description: str
    indices: tuple[int, ...]
    side: str  # "upper" | "lower" | "both" | direction/pattern label

    def as_dict(self) -> dict:
        return {
            "rule_number": self.rule_number,
            "rule_name": self.rule_name,
            "method": self.method,
            "description": self.description,
            "indices": list(self.indices),
            "side": self.side,
        }


def _rule1(values: Sequence[float], cl: float, s: float) -> list[tuple[tuple[int, ...], str]]:
    """Rule 1 — one point beyond 3-sigma."""

    out = []
    for i, v in enumerate(values):
        z = (v - cl) / s
        if abs(z) > 3:
            out.append(((i,), "upper" if z > 0 else "lower"))
    return out


def _run_same_side(values, cl, s, n):  # rule 2
    zs = [(v - cl) / s for v in values]
    out = []
    for start in range(len(zs) - n + 1):
        window = zs[start : start + n]
        if all(z > 0 for z in window):
            out.append((tuple(range(start, start + n)), "upper"))
        elif all(z < 0 for z in window):
            out.append((tuple(range(start, start + n)), "lower"))
    return out


def _rule2(values, cl, s):
    return _run_same_side(values, cl, s, 9)


def _rule3(values, cl, s):  # 6 monotonic (does not need cl/s)
    n = 6
    out = []
    for start in range(len(values) - n + 1):
        w = values[start : start + n]
        if all(w[j] < w[j + 1] for j in range(n - 1)):
            out.append((tuple(range(start, start + n)), "increasing"))
        elif all(w[j] > w[j + 1] for j in range(n - 1)):
            out.append((tuple(range(start, start + n)), "decreasing"))
    return out


def _rule4(values, cl, s):  # 14 alternating (does not need cl/s)
    n = 14
    diffs = [values[j + 1] - values[j] for j in range(len(values) - 1)]
    out = []
    for start in range(len(values) - n + 1):
        w = diffs[start : start + n - 1]  # 13 transitions
        if all(x != 0 for x in w) and all(w[j] * w[j + 1] < 0 for j in range(len(w) - 1)):
            out.append((tuple(range(start, start + n)), "alternating"))
    return out


def _k_of_m_beyond(values, cl, s, *, k, m, zone):  # rules 5 & 6
    zs = [(v - cl) / s for v in values]
    out = []
    for start in range(len(zs) - m + 1):
        window = zs[start : start + m]
        if sum(1 for z in window if z > zone) >= k:
            out.append((tuple(range(start, start + m)), "upper"))
        elif sum(1 for z in window if z < -zone) >= k:
            out.append((tuple(range(start, start + m)), "lower"))
    return out


def _rule5(values, cl, s):
    return _k_of_m_beyond(values, cl, s, k=2, m=3, zone=2)


def _rule6(values, cl, s):
    return _k_of_m_beyond(values, cl, s, k=4, m=5, zone=1)


def _rule7(values, cl, s):  # 15 within 1-sigma (stratification)
    n = 15
    zs = [(v - cl) / s for v in values]
    out = []
    for start in range(len(zs) - n + 1):
        if all(abs(z) < 1 for z in zs[start : start + n]):
            out.append((tuple(range(start, start + n)), "stratification"))
    return out


def _rule8(values, cl, s):  # 8 outside 1-sigma (mixture)
    n = 8
    zs = [(v - cl) / s for v in values]
    out = []
    for start in range(len(zs) - n + 1):
        if all(abs(z) > 1 for z in zs[start : start + n]):
            out.append((tuple(range(start, start + n)), "mixture"))
    return out


_RULES: dict[int, tuple[str, object]] = {
    1: ("1 point beyond 3-sigma (Zone A boundary)", _rule1),
    2: ("9 points same side of centerline (level shift)", _rule2),
    3: ("6 points steadily trending (drift)", _rule3),
    4: ("14 points alternating (over-control)", _rule4),
    5: ("2 of 3 points beyond 2-sigma, same side (Zone A)", _rule5),
    6: ("4 of 5 points beyond 1-sigma, same side (Zone B)", _rule6),
    7: ("15 points within 1-sigma (stratification)", _rule7),
    8: ("8 points beyond 1-sigma (mixture)", _rule8),
}

# "western_electric" is the full eight-rule run/zone set as commonly enumerated under the Western
# Electric banner (the default — it must detect everything the rule list covers). The strict 1956
# Western Electric SQC Handbook defined only the four zone tests {1, 2, 5, 6} (its run test was 8
# points, not 9) — preserved here as "western_electric_classic" for that exact convention. Nelson
# (1984) and Montgomery's consolidated sensitizing set are the same eight rules with identical
# counts (Rule 2 = 9 same-side throughout).
_RULE_SETS: dict[str, tuple[int, ...]] = {
    "western_electric": (1, 2, 3, 4, 5, 6, 7, 8),
    "western_electric_classic": (1, 2, 5, 6),
    "nelson": (1, 2, 3, 4, 5, 6, 7, 8),
    "montgomery": (1, 2, 3, 4, 5, 6, 7, 8),
}


def detect_spc_signals(
    control_chart_data: Sequence[float],
    rule_set: str = "western_electric",
    *,
    center: float | None = None,
    sigma: float | None = None,
) -> list[SPCSignal]:
    """Apply SPC rules to a control-chart series and return the fired signals.

    ``rule_set`` selects ``"western_electric"`` / ``"nelson"`` / ``"montgomery"`` (all eight rules
    below), ``"western_electric_classic"`` (the strict 1956 four zone tests: rules 1, 2, 5, 6), or
    the alternative detectors ``"cusum"`` / ``"ewma"``. The centerline defaults to the data mean and
    sigma to the moving-range estimate (MR-bar/1.128) when not supplied. The eight Shewhart rules:

      1: point beyond 3-sigma; 2: 9+ same side of centerline; 3: 6+ trending; 4: 14+ alternating;
      5: 2 of 3 beyond 2-sigma (same side); 6: 4 of 5 beyond 1-sigma (same side); 7: 15+ within
      1-sigma (stratification); 8: 8+ outside 1-sigma (mixture).
    """

    data = list(control_chart_data)
    if len(data) < 2:
        raise ValueError("at least 2 points are required")
    rs = rule_set.lower()
    cl = statistics.fmean(data) if center is None else center
    sd = _moving_range_sigma(data) if sigma is None else sigma

    if rs == "cusum":
        return cusum_signals(data, center=cl, sigma=sd)
    if rs == "ewma":
        return ewma_signals(data, center=cl, sigma=sd)
    if rs not in _RULE_SETS:
        raise ValueError(
            f"unknown rule_set {rule_set!r}; expected one of {sorted(_RULE_SETS)} or 'cusum'/'ewma'"
        )
    if sd <= 0:
        return []  # no process variation -> Shewhart zones undefined

    signals: list[SPCSignal] = []
    for num in _RULE_SETS[rs]:
        name, fn = _RULES[num]
        windows = fn(data, cl, sd)  # type: ignore[operator]
        if not windows:
            continue
        idx = tuple(sorted({i for w, _ in windows for i in w}))
        sides = {side for _, side in windows}
        side = sides.pop() if len(sides) == 1 else "both"
        signals.append(
            SPCSignal(
                rule_number=num,
                rule_name=name,
                method="shewhart",
                description=f"Rule {num}: {name} — {len(windows)} occurrence(s)",
                indices=idx,
                side=side,
            )
        )
    return signals


# --------------------------------------------------------------------------- #
# SPC signals — CUSUM and EWMA alternatives
# --------------------------------------------------------------------------- #
def cusum_statistics(
    data: Sequence[float],
    *,
    center: float,
    sigma: float,
    k: float = _CUSUM_K,
    h: float = _CUSUM_H,
) -> tuple[list[tuple[float, float]], float]:
    """Tabular two-sided CUSUM. Returns [(C+, C-), ...] and the decision limit H = h*sigma.

    C+_i = max(0, x_i - (mu0 + K) + C+_{i-1});  C-_i = max(0, (mu0 - K) - x_i + C-_{i-1});
    K = k*sigma is the reference value; the max(0, .) clamp resets a one-sided accumulator.
    """

    big_k = k * sigma
    limit = h * sigma
    c_plus = c_minus = 0.0
    rows: list[tuple[float, float]] = []
    for x in data:
        c_plus = max(0.0, x - (center + big_k) + c_plus)
        c_minus = max(0.0, (center - big_k) - x + c_minus)
        rows.append((c_plus, c_minus))
    return rows, limit


def cusum_signals(
    data: Sequence[float],
    *,
    center: float,
    sigma: float,
    k: float = _CUSUM_K,
    h: float = _CUSUM_H,
) -> list[SPCSignal]:
    """CUSUM signals: C+ or C- exceeding the decision interval H = h*sigma."""

    if sigma <= 0:
        return []
    rows, limit = cusum_statistics(data, center=center, sigma=sigma, k=k, h=h)
    up = tuple(i for i, (cp, _) in enumerate(rows) if cp > limit)
    down = tuple(i for i, (_, cm) in enumerate(rows) if cm > limit)
    out: list[SPCSignal] = []
    if up:
        out.append(
            SPCSignal(
                None,
                f"CUSUM upper (sustained upward shift, k={k}, h={h})",
                "cusum",
                f"C+ exceeds {h}-sigma decision interval at {len(up)} point(s)",
                up,
                "upper",
            )
        )
    if down:
        out.append(
            SPCSignal(
                None,
                f"CUSUM lower (sustained downward shift, k={k}, h={h})",
                "cusum",
                f"C- exceeds {h}-sigma decision interval at {len(down)} point(s)",
                down,
                "lower",
            )
        )
    return out


def ewma_statistics(
    data: Sequence[float],
    *,
    center: float,
    sigma: float,
    lam: float = _EWMA_LAMBDA,
    L: float = _EWMA_L,
) -> list[tuple[float, float, float]]:
    """EWMA chart. Returns [(z_i, LCL_i, UCL_i), ...] with time-varying control limits.

    z_i = lam*x_i + (1-lam)*z_{i-1}, z_0 = center;
    limits = center +/- L*sigma*sqrt((lam/(2-lam)) * (1 - (1-lam)^(2i))).
    """

    z = center
    rows: list[tuple[float, float, float]] = []
    for i, x in enumerate(data, start=1):
        z = lam * x + (1 - lam) * z
        half = L * sigma * math.sqrt((lam / (2 - lam)) * (1 - (1 - lam) ** (2 * i)))
        rows.append((z, center - half, center + half))
    return rows


def ewma_signals(
    data: Sequence[float],
    *,
    center: float,
    sigma: float,
    lam: float = _EWMA_LAMBDA,
    L: float = _EWMA_L,
) -> list[SPCSignal]:
    """EWMA signals: the smoothed statistic crossing its time-varying control limit."""

    if sigma <= 0:
        return []
    rows = ewma_statistics(data, center=center, sigma=sigma, lam=lam, L=L)
    up = tuple(i for i, (z, _, ucl) in enumerate(rows) if z > ucl)
    down = tuple(i for i, (z, lcl, _) in enumerate(rows) if z < lcl)
    out: list[SPCSignal] = []
    if up:
        out.append(
            SPCSignal(
                None,
                f"EWMA upper (lambda={lam}, L={L})",
                "ewma",
                f"EWMA statistic exceeds the upper limit at {len(up)} point(s)",
                up,
                "upper",
            )
        )
    if down:
        out.append(
            SPCSignal(
                None,
                f"EWMA lower (lambda={lam}, L={L})",
                "ewma",
                f"EWMA statistic falls below the lower limit at {len(down)} point(s)",
                down,
                "lower",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Trending layer — real-time alerts before an OOS event
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MeasurementPoint:
    """One time-ordered measurement."""

    value: float
    timepoint: str = ""
    batch_id: str = ""
    label: str = ""


@dataclass(frozen=True)
class MeasurementSeries:
    """A time-ordered series for one (product, parameter) with its specification."""

    product: str
    parameter: str
    points: tuple[MeasurementPoint, ...]
    usl: float | None = None
    lsl: float | None = None
    target: float | None = None
    unit: str = ""

    def values(self) -> list[float]:
        return [p.value for p in self.points]

    def is_oos(self, value: float) -> bool:
        if self.usl is not None and value > self.usl:
            return True
        return self.lsl is not None and value < self.lsl


@dataclass(frozen=True)
class TrendAlert:
    """A trending alert raised over a series."""

    severity: AlertSeverity
    category: str  # "oos" | "capability" | "spc" | "proximity"
    message: str
    indices: tuple[int, ...] = ()

    def as_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "indices": list(self.indices),
        }


@dataclass(frozen=True)
class TrendingReport:
    """Capability + SPC + CUSUM/EWMA trending for a series, with pre-OOS alerts."""

    product: str
    parameter: str
    n: int
    capability: CapabilityIndices
    spc_signals: tuple[SPCSignal, ...]
    cusum_signals: tuple[SPCSignal, ...]
    ewma_signals: tuple[SPCSignal, ...]
    alerts: tuple[TrendAlert, ...]
    oos_indices: tuple[int, ...]
    first_signal_index: int | None
    first_oos_index: int | None = None
    rule_set: str = "nelson"

    @property
    def has_oos(self) -> bool:
        return bool(self.oos_indices)

    @property
    def lead_points(self) -> int | None:
        """How many points the earliest signal preceded the first OOS (early-warning lead)."""

        if self.first_signal_index is None or self.first_oos_index is None:
            return None
        return max(0, self.first_oos_index - self.first_signal_index)

    def as_dict(self) -> dict:
        return {
            "product": self.product,
            "parameter": self.parameter,
            "n": self.n,
            "rule_set": self.rule_set,
            "capability": self.capability.as_dict(),
            "spc_signals": [s.as_dict() for s in self.spc_signals],
            "cusum_signals": [s.as_dict() for s in self.cusum_signals],
            "ewma_signals": [s.as_dict() for s in self.ewma_signals],
            "alerts": [a.as_dict() for a in self.alerts],
            "oos_indices": list(self.oos_indices),
            "first_signal_index": self.first_signal_index,
            "first_oos_index": self.first_oos_index,
            "lead_points": self.lead_points,
        }


def analyze_series(
    series: MeasurementSeries,
    *,
    rule_set: str = "nelson",
    warn_within_sigma: float = 1.0,
    subgroup_size: int | None = None,
) -> TrendingReport:
    """Run capability + SPC + CUSUM/EWMA over *series* and raise pre-OOS trending alerts.

    The value of SPC trending is that drift/shift signals fire while points are still within
    specification — an early warning *before* an OOS event. ``warn_within_sigma`` controls the
    proximity alert when the latest point is in-spec but within that many sigma of a limit;
    ``subgroup_size`` is passed through to the capability calculation.
    """

    values = series.values()
    cap = calculate_capability_indices(
        values, series.usl, series.lsl, series.target, subgroup_size=subgroup_size
    )
    cl, sd = cap.mean, cap.sigma_within

    spc = tuple(detect_spc_signals(values, rule_set, center=cl, sigma=sd)) if sd > 0 else ()
    cusum = tuple(cusum_signals(values, center=cl, sigma=sd))
    ewma = tuple(ewma_signals(values, center=cl, sigma=sd))

    oos_indices = tuple(i for i, v in enumerate(values) if series.is_oos(v))
    first_oos = oos_indices[0] if oos_indices else None

    alerts: list[TrendAlert] = []
    if oos_indices:
        alerts.append(
            TrendAlert(
                AlertSeverity.CRITICAL,
                "oos",
                f"{len(oos_indices)} point(s) out of specification",
                oos_indices,
            )
        )
    if cap.rating is CapabilityRating.NOT_CAPABLE:
        alerts.append(TrendAlert(AlertSeverity.CRITICAL, "capability", cap.interpretation))
    elif cap.rating is CapabilityRating.MARGINAL:
        alerts.append(TrendAlert(AlertSeverity.WARNING, "capability", cap.interpretation))

    signal_indices: list[int] = []
    for sig in (*spc, *cusum, *ewma):
        if sig.indices:
            signal_indices.append(sig.indices[0])
        alerts.append(TrendAlert(AlertSeverity.WARNING, "spc", sig.description, sig.indices))

    # Proximity early-warning: latest point in-spec but hugging a limit.
    if values:
        last_i = len(values) - 1
        last = values[last_i]
        if not series.is_oos(last) and sd > 0:
            if series.usl is not None and (series.usl - last) <= warn_within_sigma * sd:
                alerts.append(
                    TrendAlert(
                        AlertSeverity.WARNING,
                        "proximity",
                        f"latest point within {warn_within_sigma:g} sigma of the upper limit",
                        (last_i,),
                    )
                )
            if series.lsl is not None and (last - series.lsl) <= warn_within_sigma * sd:
                alerts.append(
                    TrendAlert(
                        AlertSeverity.WARNING,
                        "proximity",
                        f"latest point within {warn_within_sigma:g} sigma of the lower limit",
                        (last_i,),
                    )
                )

    first_signal = min(signal_indices) if signal_indices else None
    return TrendingReport(
        product=series.product,
        parameter=series.parameter,
        n=len(values),
        capability=cap,
        spc_signals=spc,
        cusum_signals=cusum,
        ewma_signals=ewma,
        alerts=tuple(alerts),
        oos_indices=oos_indices,
        first_signal_index=first_signal,
        first_oos_index=first_oos,
        rule_set=rule_set,
    )


# --------------------------------------------------------------------------- #
# Integration adapters — connect to release-test & stability data
# --------------------------------------------------------------------------- #
# MolTrace has no dedicated stability/release time-series table; these adapters build a
# MeasurementSeries from the existing single-point structures (AnalyticalResult from the OOS engine,
# BatchResult from the Q6A spec builder) so release-test and stability timepoints flow straight in.
_BATCH_FIELDS = {
    "assay": "assay_percent",
    "dissolution": "dissolution_percent_30min",
    "water": "water_content_percent",
    "total_impurities": "total_impurities_percent",
}


def series_from_analytical_results(
    results: Sequence[AnalyticalResult],
    *,
    usl: float | None = None,
    lsl: float | None = None,
    target: float | None = None,
) -> MeasurementSeries:
    """Build a series from OOS-engine AnalyticalResult records (release tests / stability pulls).

    Ordered by ``test_date`` when every record carries one, else left in the given order.
    """

    items = list(results)
    if not items:
        raise ValueError("no analytical results supplied")
    if all(r.test_date for r in items):
        items = sorted(items, key=lambda r: r.test_date)
    points = tuple(
        MeasurementPoint(value=r.reported_value, timepoint=r.test_date, batch_id=r.batch_id)
        for r in items
    )
    first = items[0]
    return MeasurementSeries(
        product=first.product_name,
        parameter=first.test_name,
        points=points,
        usl=usl,
        lsl=lsl,
        target=target,
        unit=first.unit,
    )


def series_from_batch_results(
    batches: Sequence[BatchResult],
    parameter: str,
    *,
    usl: float | None = None,
    lsl: float | None = None,
    target: float | None = None,
    product: str = "",
) -> MeasurementSeries:
    """Build a series from Q6A-builder BatchResult records for one parameter.

    ``parameter`` is one of: assay, dissolution, water, total_impurities. Batches missing that
    field are skipped.
    """

    key = parameter.lower()
    if key not in _BATCH_FIELDS:
        raise ValueError(f"parameter must be one of {sorted(_BATCH_FIELDS)}, got {parameter!r}")
    field_name = _BATCH_FIELDS[key]
    points = tuple(
        MeasurementPoint(value=getattr(b, field_name), batch_id=b.batch_id)
        for b in batches
        if getattr(b, field_name) is not None
    )
    return MeasurementSeries(
        product=product,
        parameter=parameter,
        points=points,
        usl=usl,
        lsl=lsl,
        target=target,
    )


def capability_for_specification(
    measurements: Sequence[float],
    spec: SpecificationLimit,
    target: float | None = None,
    *,
    subgroup_size: int | None = None,
) -> CapabilityIndices:
    """Capability against an OOS-engine SpecificationLimit (its upper -> USL, lower -> LSL)."""

    return calculate_capability_indices(
        measurements, spec.upper, spec.lower, target, subgroup_size=subgroup_size
    )
