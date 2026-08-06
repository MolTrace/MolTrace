"""B1 slice 1: kinetic rate constants, with their uncertainty or not at all.

`git grep` for kinetics across `spectroscopy/` returned nothing before this — there was no
concept of an ordered series of spectra, let alone a rate. All four 2026 strategy documents asked
for it, and it is the one genuinely absent capability among them.

The precondition shapes the design. k is a fit over integration values, and integration accuracy
is an open program here (the detector over-picks on real spectra). A rate constant computed on
unreliable integrals is a confident number with nothing behind it — precisely the failure this
platform exists to prevent. So every path either returns k **with its standard error and residual
diagnostics**, or refuses and names the cause. There is no third option and no bare point estimate.
"""

from __future__ import annotations

import math

from moltrace.spectroscopy.kinetics import (
    KineticFit,
    KineticRefusal,
    fit_first_order,
    fit_second_order,
    identify_order,
)


def _first_order_series(k=0.10, a0=100.0, n=11, dt=1.0):
    times = [i * dt for i in range(n)]
    return times, [a0 * math.exp(-k * t) for t in times]


def _second_order_series(k=0.02, a0=100.0, n=11, dt=1.0):
    # 1/[A] = 1/[A]0 + kt
    times = [i * dt for i in range(n)]
    return times, [1.0 / (1.0 / a0 + k * t) for t in times]


# --- a rate never ships without its uncertainty -------------------------------------------------


def test_a_clean_first_order_decay_recovers_its_rate_constant_with_uncertainty():
    times, values = _first_order_series(k=0.10)
    fit = fit_first_order(times, values)

    assert isinstance(fit, KineticFit)
    assert fit.order == "first"
    assert abs(fit.rate_constant - 0.10) < 1e-6
    # The uncertainty is present and finite — never None, never omitted.
    assert fit.standard_error is not None
    assert fit.standard_error >= 0.0
    assert fit.r_squared > 0.999
    assert fit.point_count == 11
    assert fit.half_life is not None
    assert abs(fit.half_life - math.log(2) / 0.10) < 1e-6


def test_a_clean_second_order_decay_recovers_its_rate_constant():
    times, values = _second_order_series(k=0.02)
    fit = fit_second_order(times, values)

    assert isinstance(fit, KineticFit)
    assert fit.order == "second"
    assert abs(fit.rate_constant - 0.02) < 1e-6
    assert fit.standard_error is not None
    # A second-order half-life depends on the starting concentration, so it is not reported as a
    # property of the rate constant alone.
    assert fit.half_life is None


# --- refusals, each naming its cause ------------------------------------------------------------


def test_too_few_points_refuses_rather_than_fitting_two_parameters_to_three_points():
    """A two-parameter fit needs residual degrees of freedom before a standard error means much.

    The bound is df >= 3 (n >= 5), which comes from the fit itself rather than a round number.
    """
    times, values = _first_order_series(n=4)
    refusal = fit_first_order(times, values)

    assert isinstance(refusal, KineticRefusal)
    assert refusal.reason == "too_few_points"
    assert "4" in refusal.detail and "5" in refusal.detail


def test_a_flat_series_refuses_because_there_is_no_decay_to_measure():
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    values = [50.0] * 6
    refusal = fit_first_order(times, values)

    assert isinstance(refusal, KineticRefusal)
    assert refusal.reason == "no_change_over_time"


def test_a_non_positive_value_refuses_instead_of_taking_the_log_of_zero():
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    values = [100.0, 60.0, 36.0, 0.0, 7.8, 4.7]
    refusal = fit_first_order(times, values)

    assert isinstance(refusal, KineticRefusal)
    assert refusal.reason == "non_positive_value"
    assert "0" in refusal.detail


def test_duplicate_timestamps_refuse_because_the_series_is_not_ordered_in_time():
    times = [0.0, 1.0, 1.0, 2.0, 3.0, 4.0]
    _, values = _first_order_series(n=6)
    refusal = fit_first_order(times, values)

    assert isinstance(refusal, KineticRefusal)
    assert refusal.reason == "duplicate_timestamps"


def test_mismatched_lengths_refuse():
    refusal = fit_first_order([0.0, 1.0, 2.0], [1.0, 2.0])
    assert isinstance(refusal, KineticRefusal)
    assert refusal.reason == "length_mismatch"


# --- order identification never silently picks the better R² -------------------------------------


def test_identify_order_names_first_order_when_the_data_actually_supports_it():
    times, values = _first_order_series(k=0.25)
    result = identify_order(times, values)

    assert isinstance(result, KineticFit)
    assert result.order == "first"


def test_identify_order_refuses_when_both_orders_fit_equally_well():
    """Over a short, shallow decay the two models are indistinguishable.

    Picking whichever R² is higher would report an order the data cannot support.
    """
    # ~5% conversion sampled briefly, with scatter the size real integration delivers. Over so
    # little of the curve the two rate laws are physically near-identical, and the noise swamps
    # what difference remains.
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    values = [100.45, 98.625, 98.32, 96.625, 96.429, 94.823]
    result = identify_order(times, values)

    assert isinstance(result, KineticRefusal)
    assert result.reason == "order_not_identifiable"
    assert "conversion" in result.detail


def test_orders_are_compared_on_the_measured_scale_not_the_linearised_one():
    """The linearised residuals are incommensurable between orders.

    ``ln[A]`` sits near 4.6 while ``1/[A]`` sits near 0.01, so a reciprocal fit's RSS is ~10^4
    smaller for arithmetic reasons alone. Comparing those directly would hand every verdict to
    second order regardless of the chemistry.
    """
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    values = [100.45, 98.625, 98.32, 96.625, 96.429, 94.823]
    first = fit_first_order(times, values)
    second = fit_second_order(times, values)
    assert isinstance(first, KineticFit) and isinstance(second, KineticFit)

    # The trap: on the linearised scale second order looks decisively better — by four orders of
    # magnitude — purely because 1/[A] is numerically ~100x smaller than ln[A] before squaring.
    linearised_ratio = first.residual_sum_of_squares / second.residual_sum_of_squares
    assert linearised_ratio > 1000

    # On the measured scale the same two fits are within a couple of percent of each other, which
    # is the truth: this series cannot tell the orders apart.
    native_ratio = (
        first.native_residual_sum_of_squares / second.native_residual_sum_of_squares
    )
    assert 0.9 < native_ratio < 1.1
    assert isinstance(identify_order(times, values), KineticRefusal)


def test_a_refusal_is_never_mistaken_for_a_fit():
    """The two outcomes are distinct types, so a caller cannot read a refusal as a rate."""
    refusal = fit_first_order([0.0, 1.0], [1.0, 0.5])
    assert isinstance(refusal, KineticRefusal)
    assert not hasattr(refusal, "rate_constant")
