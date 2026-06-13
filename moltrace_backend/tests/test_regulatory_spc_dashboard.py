"""Prompt 9 — process-capability & SPC trending engine.

Capability indices are cross-checked against an INDEPENDENT in-test reference computation (mean,
moving-range sigma = MR-bar/1.128, sample SD with ddof=1) so the assertions are non-circular. Each
SPC rule is exercised with a minimal trigger series that should fire exactly that rule, plus a clean
in-control series that fires none. CUSUM/EWMA, the trending layer, and the integration adapters round
it out.
"""

from __future__ import annotations

import math
import statistics

from moltrace.regulatory.quality import (
    AlertSeverity,
    CapabilityRating,
    MeasurementPoint,
    MeasurementSeries,
    analyze_series,
    calculate_capability_indices,
    cusum_signals,
    detect_spc_signals,
    ewma_signals,
    series_from_analytical_results,
    series_from_batch_results,
)
from moltrace.regulatory.quality.oos_investigation import AnalyticalResult
from moltrace.regulatory.specifications.q6a_builder import BatchResult


# --------------------------------------------------------------------------- #
# Independent reference computation (NOT the module under test)
# --------------------------------------------------------------------------- #
def _ref_indices(data, usl, lsl, target):
    n = len(data)
    xbar = statistics.fmean(data)
    sd = statistics.stdev(data)
    mr = [abs(data[i] - data[i - 1]) for i in range(1, n)]
    sw = (sum(mr) / len(mr)) / 1.128
    cp = (usl - lsl) / (6 * sw)
    cpk = min((usl - xbar) / (3 * sw), (xbar - lsl) / (3 * sw))
    pp = (usl - lsl) / (6 * sd)
    ppk = min((usl - xbar) / (3 * sd), (xbar - lsl) / (3 * sd))
    cpm = cp / math.sqrt(1 + ((xbar - target) / sw) ** 2)
    return dict(
        mean=xbar, sigma_within=sw, sigma_overall=sd, cp=cp, cpk=cpk, pp=pp, ppk=ppk, cpm=cpm
    )


# --------------------------------------------------------------------------- #
# Capability indices
# --------------------------------------------------------------------------- #
def test_capability_matches_independent_reference() -> None:
    data = [10.2, 9.8, 10.1, 10.4, 9.9, 10.0, 10.3, 9.7, 10.2, 10.1]
    usl, lsl, target = 11.0, 9.0, 10.0
    ci = calculate_capability_indices(data, usl, lsl, target)
    ref = _ref_indices(data, usl, lsl, target)
    for key in ("mean", "sigma_within", "sigma_overall", "cp", "cpk", "pp", "ppk", "cpm"):
        assert math.isclose(getattr(ci, key), ref[key], rel_tol=1e-12), key
    # the pinned worked-example values (verified by hand two ways)
    assert math.isclose(ci.cpk, 1.0152, rel_tol=1e-6)
    assert math.isclose(ci.pp, 1.50584650, rel_tol=1e-6)
    assert ci.rating is CapabilityRating.MARGINAL  # 1.00 <= Cpk < 1.33
    assert ci.is_capable is False


def test_capability_cpm_equals_direct_taguchi_form() -> None:
    data = [49.5, 50.2, 50.0, 49.8, 50.4, 49.7, 50.1, 50.3]
    usl, lsl, target = 52.0, 48.0, 50.0
    ci = calculate_capability_indices(data, usl, lsl, target)
    tau = math.sqrt(ci.sigma_within**2 + (ci.mean - target) ** 2)
    assert math.isclose(ci.cpm, (usl - lsl) / (6 * tau), rel_tol=1e-12)


def test_capability_rating_bands() -> None:
    # Tight, well-centred -> capable (Cpk >= 1.33)
    capable = calculate_capability_indices([100.0, 100.1, 99.9, 100.05, 99.95, 100.0], 105.0, 95.0)
    assert capable.rating is CapabilityRating.CAPABLE and capable.is_capable
    # Mean pushed near the upper limit -> not capable
    bad = calculate_capability_indices([104.6, 104.9, 104.7, 105.1, 104.8, 104.7], 105.0, 95.0)
    assert bad.rating is CapabilityRating.NOT_CAPABLE


def test_capability_one_sided_specification() -> None:
    # Upper-only limit (e.g. NMT impurities): Cp/Pp/Cpm not applicable, one-sided Cpk reported.
    ci = calculate_capability_indices([0.10, 0.12, 0.11, 0.13, 0.09], usl=0.5, lsl=None)
    assert ci.cp is None and ci.pp is None and ci.cpm is None
    assert ci.cpk is not None and ci.cpu is not None and ci.cpl is None
    assert any("one-sided" in w for w in ci.warnings)


def test_capability_zero_variation_is_infinite_not_a_crash() -> None:
    ci = calculate_capability_indices([100.0, 100.0, 100.0, 100.0], 105.0, 95.0)
    assert ci.sigma_within == 0.0
    assert ci.cp == math.inf and ci.cpk == math.inf
    assert ci.rating is CapabilityRating.CAPABLE
    assert any("zero within-variation" in w for w in ci.warnings)


def test_capability_cpm_zero_variation_is_finite_when_off_target() -> None:
    # Zero within-variation but mean != target: Cpm converges to (USL-LSL)/(6*|mean-target|),
    # NOT infinity (Cp/Cpk are legitimately infinite; the Taguchi index penalises off-centring).
    ci = calculate_capability_indices([10.0, 10.0, 10.0, 10.0], usl=12.0, lsl=8.0, target=9.0)
    assert ci.cp == math.inf and ci.cpk == math.inf
    assert math.isclose(ci.cpm, (12.0 - 8.0) / (6 * abs(10.0 - 9.0)), rel_tol=1e-12)
    # mean exactly on target with zero variation -> perfect (infinite) Cpm
    on_target = calculate_capability_indices([9.0, 9.0, 9.0], usl=12.0, lsl=8.0, target=9.0)
    assert on_target.cpm == math.inf


def test_capability_requires_two_points() -> None:
    import pytest

    with pytest.raises(ValueError):
        calculate_capability_indices([100.0], 105.0, 95.0)


def test_capability_subgroup_sigma() -> None:
    # 3 subgroups of 4; within sigma = Rbar/d2(4) with d2(4)=2.059.
    data = [10.1, 9.9, 10.0, 10.2, 9.8, 10.1, 10.0, 9.9, 10.2, 10.0, 9.8, 10.1]
    ci = calculate_capability_indices(data, 11.0, 9.0, subgroup_size=4)
    ranges = [max(data[i : i + 4]) - min(data[i : i + 4]) for i in (0, 4, 8)]
    expected_sigma = (sum(ranges) / 3) / 2.059
    assert math.isclose(ci.sigma_within, expected_sigma, rel_tol=1e-12)


# --------------------------------------------------------------------------- #
# SPC rules — each trigger fires exactly its rule; in-control fires none
# --------------------------------------------------------------------------- #
_TRIGGERS = {
    1: [0.2, -0.1, 3.2],
    2: [0.5, 0.4, 0.6, 0.3, 0.5, 0.7, 0.2, 0.4, 0.5],
    3: [-0.5, -0.3, -0.1, 0.1, 0.3, 0.5],
    4: [0.1, -0.1, 0.2, -0.2, 0.1, -0.1, 0.2, -0.2, 0.1, -0.1, 0.2, -0.2, 0.1, -0.1],
    5: [0.3, 2.2, 2.3],
    6: [0.2, 1.2, 1.3, 1.4, 1.5],
    7: [0.1, -0.1, 0.2, -0.2, 0.0, 0.1, -0.1, 0.05, -0.05, 0.1, 0.2, -0.1, 0.0, 0.1, -0.1],
    8: [1.2, -1.3, 1.4, -1.5, 1.2, -1.3, 1.4, -1.5],
}
_IN_CONTROL = [
    0.1,
    -0.4,
    0.6,
    -0.2,
    0.3,
    -0.7,
    0.2,
    1.1,
    -0.9,
    0.4,
    -0.3,
    0.8,
    -0.6,
    0.0,
    0.5,
    -1.2,
    0.7,
    -0.1,
    0.3,
    -0.5,
]


def test_each_rule_fires_exclusively_on_its_trigger() -> None:
    # CL=0, sigma=1 standardized so the zones are exactly +/-1/2/3.
    for rule_number, series in _TRIGGERS.items():
        fired = {s.rule_number for s in detect_spc_signals(series, "nelson", center=0.0, sigma=1.0)}
        assert fired == {rule_number}, (rule_number, fired)


def test_in_control_series_fires_no_rule() -> None:
    assert detect_spc_signals(_IN_CONTROL, "nelson", center=0.0, sigma=1.0) == []


def test_western_electric_default_covers_all_eight_rules() -> None:
    # The prompt enumerates all eight rules under "Western Electric"; the documented default must
    # detect them all — including Rule 3 (6-point trend), which the strict 1956 set omits.
    assert {
        s.rule_number
        for s in detect_spc_signals(_TRIGGERS[3], "western_electric", center=0.0, sigma=1.0)
    } == {3}


def test_western_electric_classic_is_only_the_four_zone_rules() -> None:
    # Strict 1956 WECO = {1, 2, 5, 6}; the trend rule (3) must NOT fire under the classic set.
    assert detect_spc_signals(_TRIGGERS[3], "western_electric_classic", center=0.0, sigma=1.0) == []
    # but a beyond-3-sigma point (Rule 1) is in every set
    assert {
        s.rule_number
        for s in detect_spc_signals(_TRIGGERS[1], "western_electric_classic", center=0.0, sigma=1.0)
    } == {1}


def test_unknown_rule_set_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        detect_spc_signals([1.0, 2.0, 3.0], "made_up_rules")


def test_signal_carries_offending_indices() -> None:
    [sig] = detect_spc_signals(_TRIGGERS[1], "nelson", center=0.0, sigma=1.0)
    assert sig.rule_number == 1 and sig.indices == (2,) and sig.side == "upper"


# --------------------------------------------------------------------------- #
# CUSUM + EWMA
# --------------------------------------------------------------------------- #
def test_cusum_detects_sustained_shift_and_is_silent_in_control() -> None:
    # +2 sigma sustained shift (mu0=10, sigma=2) -> C+ crosses h*sigma at the 4th point (index 3).
    sig = cusum_signals([14.0] * 8, center=10.0, sigma=2.0)
    assert len(sig) == 1 and sig[0].side == "upper" and sig[0].method == "cusum"
    assert sig[0].indices[0] == 3
    assert cusum_signals([10.0, 10.1, 9.9, 10.05, 9.95, 10.0], center=10.0, sigma=0.2) == []


def test_ewma_detects_shift_at_expected_point() -> None:
    # CL=10, sigma=2, lambda=0.2, L=3: z_3=11.952 > UCL_3=11.718 -> first signal at index 2.
    sig = ewma_signals([14.0] * 5, center=10.0, sigma=2.0)
    assert len(sig) == 1 and sig[0].side == "upper" and sig[0].method == "ewma"
    assert sig[0].indices[0] == 2
    assert ewma_signals([10.0, 10.1, 9.9, 10.05, 9.95, 10.0], center=10.0, sigma=0.2) == []


def test_detect_spc_signals_dispatches_to_cusum_and_ewma() -> None:
    assert detect_spc_signals([14.0] * 8, "cusum", center=10.0, sigma=2.0)[0].method == "cusum"
    assert detect_spc_signals([14.0] * 5, "ewma", center=10.0, sigma=2.0)[0].method == "ewma"


# --------------------------------------------------------------------------- #
# Trending layer — early warning before OOS
# --------------------------------------------------------------------------- #
def test_trending_warns_before_an_oos_event() -> None:
    # A slow upward drift that stays in-spec for a while, then crosses USL only at the end.
    values = [100.0, 100.3, 100.6, 100.9, 101.2, 101.5, 101.8, 102.1, 102.4, 103.5]
    series = MeasurementSeries(
        product="Examplinib tablets",
        parameter="Assay",
        points=tuple(MeasurementPoint(v) for v in values),
        usl=103.0,
        lsl=97.0,
        target=100.0,
    )
    report = analyze_series(series, rule_set="nelson")
    assert report.has_oos  # the last point crosses USL
    assert report.first_oos_index == 9
    # an SPC/CUSUM/EWMA signal fired strictly BEFORE the OOS point (the early warning)
    assert report.first_signal_index is not None
    assert report.first_signal_index < report.first_oos_index
    assert report.lead_points and report.lead_points > 0
    categories = {a.category for a in report.alerts}
    assert "oos" in categories and "spc" in categories
    assert any(a.severity is AlertSeverity.CRITICAL for a in report.alerts)


def test_trending_in_control_series_has_no_critical_alerts() -> None:
    values = [100.0, 100.2, 99.8, 100.1, 99.9, 100.0, 100.1, 99.9, 100.05, 99.95]
    series = MeasurementSeries(
        product="P",
        parameter="Assay",
        points=tuple(MeasurementPoint(v) for v in values),
        usl=105.0,
        lsl=95.0,
        target=100.0,
    )
    report = analyze_series(series)
    assert not report.has_oos
    assert all(a.severity is not AlertSeverity.CRITICAL for a in report.alerts)
    assert report.as_dict()["capability"]["rating"] in {"capable", "marginal"}


# --------------------------------------------------------------------------- #
# Integration adapters
# --------------------------------------------------------------------------- #
def test_series_from_analytical_results_orders_by_test_date() -> None:
    results = [
        AnalyticalResult("Assay", 100.4, "%", "B3", "Examplinib", test_date="2026-03-01"),
        AnalyticalResult("Assay", 100.0, "%", "B1", "Examplinib", test_date="2026-01-01"),
        AnalyticalResult("Assay", 100.2, "%", "B2", "Examplinib", test_date="2026-02-01"),
    ]
    series = series_from_analytical_results(results, usl=105.0, lsl=95.0, target=100.0)
    assert series.product == "Examplinib" and series.parameter == "Assay"
    assert series.values() == [100.0, 100.2, 100.4]  # chronological
    report = analyze_series(series)
    assert report.n == 3


def test_series_from_batch_results_picks_the_parameter_field() -> None:
    batches = [
        BatchResult("B1", assay_percent=99.8, dissolution_percent_30min=94.0),
        BatchResult("B2", assay_percent=100.1, dissolution_percent_30min=95.0),
        BatchResult("B3", assay_percent=99.6, dissolution_percent_30min=93.0),
    ]
    series = series_from_batch_results(batches, "assay", usl=105.0, lsl=95.0, product="Examplinib")
    assert series.values() == [99.8, 100.1, 99.6]
    diss = series_from_batch_results(batches, "dissolution", lsl=80.0)
    assert diss.values() == [94.0, 95.0, 93.0]


def test_series_from_batch_results_rejects_unknown_parameter() -> None:
    import pytest

    with pytest.raises(ValueError):
        series_from_batch_results([], "ph")
