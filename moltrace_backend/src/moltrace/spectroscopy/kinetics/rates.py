"""Linearised rate-law fits with exact uncertainty, or a refusal that names its cause."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

KineticOrder = Literal["first", "second"]

RefusalReason = Literal[
    "length_mismatch",
    "too_few_points",
    "duplicate_timestamps",
    "non_positive_value",
    "no_change_over_time",
    "degenerate_fit",
    "order_not_identifiable",
]

# A two-parameter fit needs residual degrees of freedom before its standard error carries
# information: df = n - 2, and df >= 3 is the smallest that gives the residual variance any
# stability. That is where n >= 5 comes from — the fit's own algebra, not a round number.
_MIN_PARAMETERS = 2
_MIN_RESIDUAL_DF = 3
MIN_POINTS = _MIN_PARAMETERS + _MIN_RESIDUAL_DF

# Two models are indistinguishable when swapping one for the other buys less residual variance
# than one degree of freedom is worth — an F-statistic of about 1. Below that the "better" fit is
# noise, so the order is not identifiable from this measurement.
_F_INDISTINGUISHABLE = 1.0


@dataclass(frozen=True)
class KineticFit:
    """A rate constant, always accompanied by what is known about its reliability."""

    order: KineticOrder
    rate_constant: float
    standard_error: float
    r_squared: float
    #: Residuals on the LINEARISED scale the fit was performed on. Never compare this between
    #: orders — ``ln[A]`` and ``1/[A]`` are incommensurable, and the reciprocal's numbers are
    #: ~100x smaller, so second order would always appear to win by ~10^4. Use
    #: :attr:`native_residual_sum_of_squares` for that.
    residual_sum_of_squares: float
    #: Residuals in the units actually measured, after back-transforming each model's prediction.
    #: This is the only scale on which two orders can be compared.
    native_residual_sum_of_squares: float
    intercept: float
    point_count: int
    #: First order only. A second-order half-life depends on the starting concentration, so it is
    #: not a property of ``k`` alone and is deliberately not reported as one.
    half_life: float | None
    human_review_required: bool = True


@dataclass(frozen=True)
class KineticRefusal:
    """Why no rate constant was produced. Deliberately carries no ``rate_constant`` attribute."""

    reason: RefusalReason
    detail: str
    point_count: int = 0
    human_review_required: bool = True


@dataclass(frozen=True)
class _LinearFit:
    slope: float
    intercept: float
    slope_standard_error: float
    r_squared: float
    residual_sum_of_squares: float


def _ordinary_least_squares(xs: Sequence[float], ys: Sequence[float]) -> _LinearFit | None:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0.0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys, strict=True)]
    rss = sum(r * r for r in residuals)
    syy = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1.0 - (rss / syy) if syy > 0.0 else 1.0

    df = n - _MIN_PARAMETERS
    residual_variance = rss / df if df > 0 else 0.0
    slope_se = math.sqrt(residual_variance / sxx) if sxx > 0.0 else math.inf
    return _LinearFit(slope, intercept, slope_se, r_squared, rss)


def _validate(times: Sequence[float], values: Sequence[float]) -> KineticRefusal | None:
    if len(times) != len(values):
        return KineticRefusal(
            reason="length_mismatch",
            detail=(
                f"{len(times)} timestamps and {len(values)} values were supplied; a series must "
                "pair every observation with the time it was acquired."
            ),
        )
    if len(times) < MIN_POINTS:
        return KineticRefusal(
            reason="too_few_points",
            detail=(
                f"{len(times)} usable points were supplied; a two-parameter rate fit needs at "
                f"least {MIN_POINTS} before its standard error carries information "
                f"(residual degrees of freedom >= {_MIN_RESIDUAL_DF})."
            ),
            point_count=len(times),
        )
    if len(set(times)) != len(times):
        return KineticRefusal(
            reason="duplicate_timestamps",
            detail=(
                "Two or more observations share a timestamp, so the series is not ordered in "
                "time and a rate cannot be attributed to it."
            ),
            point_count=len(times),
        )
    for index, value in enumerate(values):
        if value <= 0.0:
            return KineticRefusal(
                reason="non_positive_value",
                detail=(
                    f"Observation {index} is {value:g}. Both rate laws are linearised through a "
                    "reciprocal or a logarithm, and neither is defined at or below 0 — a "
                    "non-positive integral means the measurement, not the kinetics, needs review."
                ),
                point_count=len(times),
            )
    if len(set(values)) == 1:
        return KineticRefusal(
            reason="no_change_over_time",
            detail=(
                "Every observation is identical, so there is no decay or growth to measure. A "
                "rate constant fitted to a flat series would be zero by construction, not by "
                "evidence."
            ),
            point_count=len(times),
        )
    return None


def _fit(
    times: Sequence[float], values: Sequence[float], *, order: KineticOrder
) -> KineticFit | KineticRefusal:
    refusal = _validate(times, values)
    if refusal is not None:
        return refusal

    if order == "first":
        transformed = [math.log(v) for v in values]
    else:
        transformed = [1.0 / v for v in values]

    linear = _ordinary_least_squares(list(times), transformed)
    if linear is None:
        return KineticRefusal(
            reason="degenerate_fit",
            detail=(
                "The timestamps carry no spread, so no line can be fitted through them and no "
                "rate can be attributed."
            ),
            point_count=len(times),
        )

    # First order linearises to a NEGATIVE slope (-k); second order to a positive slope (+k).
    rate_constant = -linear.slope if order == "first" else linear.slope
    half_life = (
        math.log(2) / rate_constant if order == "first" and rate_constant > 0.0 else None
    )

    # Back-transform each prediction into the units that were measured, so the two orders can be
    # compared on one scale.
    native_rss = 0.0
    for t, observed in zip(times, values, strict=True):
        linearised = linear.slope * t + linear.intercept
        if order == "first":
            predicted = math.exp(linearised)
        else:
            predicted = 1.0 / linearised if linearised != 0.0 else math.inf
        native_rss += (observed - predicted) ** 2

    return KineticFit(
        order=order,
        rate_constant=rate_constant,
        standard_error=linear.slope_standard_error,
        r_squared=linear.r_squared,
        residual_sum_of_squares=linear.residual_sum_of_squares,
        native_residual_sum_of_squares=native_rss,
        intercept=linear.intercept,
        point_count=len(times),
        half_life=half_life,
    )


def fit_first_order(
    times: Sequence[float], values: Sequence[float]
) -> KineticFit | KineticRefusal:
    """Fit ``ln[A] = -kt + ln[A]₀`` and report ``k`` with its standard error, or refuse."""
    return _fit(times, values, order="first")


def fit_second_order(
    times: Sequence[float], values: Sequence[float]
) -> KineticFit | KineticRefusal:
    """Fit ``1/[A] = kt + 1/[A]₀`` and report ``k`` with its standard error, or refuse."""
    return _fit(times, values, order="second")


def identify_order(
    times: Sequence[float], values: Sequence[float]
) -> KineticFit | KineticRefusal:
    """Return the better-supported order, or refuse when the data cannot tell them apart.

    Refusing is the point. Reporting whichever R² came out higher would name an order the
    measurement does not support, and a reader has no way to see that from the number alone.
    """
    first = fit_first_order(times, values)
    second = fit_second_order(times, values)
    if isinstance(first, KineticRefusal):
        return first
    if isinstance(second, KineticRefusal):
        return second

    # Compare on the measured scale, never on the linearised one — see KineticFit.
    better, worse = (
        (first, second)
        if first.native_residual_sum_of_squares <= second.native_residual_sum_of_squares
        else (second, first)
    )
    df = better.point_count - _MIN_PARAMETERS
    if better.native_residual_sum_of_squares <= 0.0 or df <= 0:
        return better

    # Numerical floor, checked BEFORE the F ratio. As the better fit approaches perfection its
    # residual variance approaches zero, so F explodes and any difference — including one made
    # entirely of floating-point rounding — reads as decisive. Require the improvement to be
    # larger than double precision can represent across this sum before it is allowed to mean
    # anything.
    improvement = (
        worse.native_residual_sum_of_squares - better.native_residual_sum_of_squares
    )
    numerical_floor = worse.native_residual_sum_of_squares * 1e-9
    if improvement <= numerical_floor:
        return KineticRefusal(
            reason="order_not_identifiable",
            detail=(
                "A first-order and a second-order fit describe this series to within floating-"
                "point rounding, so neither can be preferred. Naming an order here would report "
                "a mechanism the measurement does not distinguish; acquire a wider extent of "
                "conversion."
            ),
            point_count=better.point_count,
        )

    # How much residual variance the better model buys, in units of one degree of freedom.
    f_statistic = improvement / (better.native_residual_sum_of_squares / df)
    if f_statistic < _F_INDISTINGUISHABLE:
        return KineticRefusal(
            reason="order_not_identifiable",
            detail=(
                "A first-order and a second-order fit describe this series equally well "
                f"(F = {f_statistic:.2f} between them, below the {_F_INDISTINGUISHABLE:g} that "
                "one degree of freedom is worth). Naming an order here would report a mechanism "
                "the measurement does not distinguish; acquire a wider extent of conversion."
            ),
            point_count=better.point_count,
        )
    return better
