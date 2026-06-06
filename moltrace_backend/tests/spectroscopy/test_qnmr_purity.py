"""Tests for the qNMR purity calculator (Prompt 9).

Covers the multiplet-ranking heuristic, both purity equations (internal
standard + PULCON) with hand-computed worked examples and closed-loop synthetic
recovery (the SDBS-equivalent acceptance: recover purity to < 0.5 % absolute),
the GUM uncertainty propagation, the validation / warning paths, and the RDKit
SMILES helpers.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from moltrace.spectroscopy.multiplet.analysis import Multiplet
from moltrace.spectroscopy.peaks.gsd import Peak
from moltrace.spectroscopy.qnmr.purity import (
    PurityResult,
    calculate_purity_internal_standard,
    calculate_purity_pulcon,
    molar_mass_from_smiles,
    rank_multiplets_for_qnmr,
    total_proton_count_from_smiles,
)


# --------------------------------------------------------------------------- #
# Fixtures / factories
# --------------------------------------------------------------------------- #
def _peak(ppm: float, *, width_hz: float = 2.0, category: str = "compound") -> Peak:
    return Peak(
        position_ppm=ppm,
        position_hz=ppm * 400.0,
        intensity=1.0,
        area=1.0,
        width_hz=width_hz,
        shape="lorentzian",
        category=category,  # type: ignore[arg-type]
    )


def _multiplet(
    name: str,
    center: float,
    *,
    label: str = "s",
    width_hz: float = 2.0,
    half_width_ppm: float = 0.02,
    peaks: list[Peak] | None = None,
    metadata: dict | None = None,
) -> Multiplet:
    lines = peaks if peaks is not None else [_peak(center, width_hz=width_hz)]
    return Multiplet(
        name=name,
        center_ppm=center,
        range_ppm=(center - half_width_ppm, center + half_width_ppm),
        multiplicity_label=label,  # type: ignore[arg-type]
        j_couplings_hz=[],
        num_nuclides=0,
        peaks=lines,
        metadata=dict(metadata or {}),
    )


# --------------------------------------------------------------------------- #
# rank_multiplets_for_qnmr
# --------------------------------------------------------------------------- #
def test_rank_perfect_singlet_scores_full_marks():
    m = _multiplet("A", 2.0)
    ranked = rank_multiplets_for_qnmr([m], m.peaks)
    q = ranked[0].metadata["qnmr"]
    assert q["score"] == q["max_score"] == 13.0
    assert q["no_contaminant_overlap"]
    assert q["clean_baseline"]
    assert q["narrow_lines"]
    assert q["known_nuclide_count"]
    assert q["not_exchangeable"]


def test_rank_does_not_mutate_inputs():
    m = _multiplet("A", 2.0)
    assert "qnmr" not in m.metadata
    rank_multiplets_for_qnmr([m], m.peaks)
    assert "qnmr" not in m.metadata  # original untouched; a copy is returned


def test_rank_solvent_overlap_loses_five():
    m = _multiplet("A", 2.0)
    solvent = _peak(2.0, category="solvent")  # inside the window
    ranked = rank_multiplets_for_qnmr([m], m.peaks + [solvent])
    q = ranked[0].metadata["qnmr"]
    assert q["no_contaminant_overlap"] is False
    assert q["contaminants_in_window"] == 1
    assert q["score"] == 13.0 - 5.0


def test_rank_impurity_overlap_loses_five():
    m = _multiplet("A", 2.0)
    impurity = _peak(2.0, category="impurity")
    ranked = rank_multiplets_for_qnmr([m], m.peaks + [impurity])
    assert ranked[0].metadata["qnmr"]["score"] == 13.0 - 5.0


def test_rank_satellite_in_window_hits_baseline_not_overlap():
    # A 13C satellite is a baseline contaminant, not a solvent/impurity overlap.
    m = _multiplet("A", 2.0)
    sat = _peak(2.0, category="13C_satellite")
    q = rank_multiplets_for_qnmr([m], m.peaks + [sat])[0].metadata["qnmr"]
    assert q["no_contaminant_overlap"] is True
    assert q["clean_baseline"] is False
    assert q["score"] == 13.0 - 3.0


def test_rank_broad_background_hump_loses_clean_baseline():
    m = _multiplet("A", 2.0)
    hump = _peak(2.05, width_hz=25.0, category="compound")  # foreign broad line
    q = rank_multiplets_for_qnmr([m], m.peaks + [hump])[0].metadata["qnmr"]
    assert q["clean_baseline"] is False
    assert q["score"] == 13.0 - 3.0


def test_rank_own_broad_line_does_not_self_disqualify_baseline():
    # A broad singlet's own line must not count as a foreign baseline hump.
    broad = _peak(2.0, width_hz=12.0)
    m = _multiplet("A", 2.0, peaks=[broad], width_hz=12.0)
    q = rank_multiplets_for_qnmr([m], [broad])[0].metadata["qnmr"]
    assert q["clean_baseline"] is True
    # but it is broad: loses narrow (2) and not_exchangeable (1)
    assert q["narrow_lines"] is False
    assert q["not_exchangeable"] is False
    assert q["score"] == 13.0 - 2.0 - 1.0


def test_rank_broad_lines_lose_narrow_point():
    lines = [_peak(1.99, width_hz=7.0), _peak(2.01, width_hz=7.0)]
    m = _multiplet("A", 2.0, label="d", peaks=lines)
    q = rank_multiplets_for_qnmr([m], m.peaks)[0].metadata["qnmr"]
    assert q["narrow_lines"] is False
    # a doublet, so not flagged exchangeable; keeps the +1
    assert q["not_exchangeable"] is True
    assert q["score"] == 13.0 - 2.0


def test_rank_generic_multiplet_loses_known_nuclide_count():
    m = _multiplet("A", 2.0, label="m")
    q = rank_multiplets_for_qnmr([m], m.peaks)[0].metadata["qnmr"]
    assert q["known_nuclide_count"] is False
    assert q["score"] == 13.0 - 2.0


def test_rank_exchangeable_flag_loses_point():
    m = _multiplet("A", 11.0, metadata={"exchangeable": True})
    q = rank_multiplets_for_qnmr([m], m.peaks)[0].metadata["qnmr"]
    assert q["not_exchangeable"] is False
    assert q["score"] == 13.0 - 1.0


def test_rank_sorts_best_first_and_is_stable():
    good = _multiplet("A", 2.0)  # 13
    contaminated = _multiplet("B", 3.0)  # 8 (solvent overlap)
    generic = _multiplet("C", 4.0, label="m")  # 11
    peaks = good.peaks + contaminated.peaks + generic.peaks + [_peak(3.0, category="solvent")]
    ranked = rank_multiplets_for_qnmr([contaminated, generic, good], peaks)
    assert [m.name for m in ranked] == ["A", "C", "B"]
    assert [m.metadata["qnmr"]["score"] for m in ranked] == [13.0, 11.0, 8.0]


def test_rank_empty_list():
    assert rank_multiplets_for_qnmr([], []) == []


# --------------------------------------------------------------------------- #
# calculate_purity_internal_standard
# --------------------------------------------------------------------------- #
def test_internal_standard_worked_example():
    # Hand-computed: P = (0.475/1)(2/1)(100/200)(20/10)(100) = 95.0
    res = calculate_purity_internal_standard(
        analyte_integral=0.475,
        standard_integral=1.0,
        analyte_protons=1,
        standard_protons=2,
        analyte_molar_mass=100.0,
        standard_molar_mass=200.0,
        analyte_mass_mg=10.0,
        standard_mass_mg=20.0,
        standard_purity_percent=100.0,
    )
    assert res.method == "internal_standard"
    assert res.purity_percent == pytest.approx(95.0, abs=1e-6)
    assert res.intermediates["ratio_integral"] == pytest.approx(0.475)
    assert res.intermediates["ratio_protons"] == pytest.approx(2.0)
    assert res.intermediates["ratio_molar_mass"] == pytest.approx(0.5)
    assert res.intermediates["ratio_mass"] == pytest.approx(2.0)


@pytest.mark.parametrize("true_purity", [70.0, 88.5, 95.0, 99.9, 100.0])
def test_internal_standard_closed_loop_recovery(true_purity):
    # Build the integrals physics would produce for a sample of known purity,
    # then confirm the calculator recovers it to < 0.5 % absolute (SDBS target).
    n_x, n_std = 3, 2  # methyl analyte vs 2H-standard
    m_x, m_std = 180.16, 116.07  # arbitrary molar masses (g/mol)
    w_x, w_std = 12.34, 9.87  # weighed masses (mg)
    p_std = 99.8
    k = 7.3  # spectrometer signal-per-mole constant (cancels)

    moles_x_pure = (w_x * true_purity / 100.0) / m_x
    moles_std_pure = (w_std * p_std / 100.0) / m_std
    i_x = k * n_x * moles_x_pure
    i_std = k * n_std * moles_std_pure

    res = calculate_purity_internal_standard(
        analyte_integral=i_x,
        standard_integral=i_std,
        analyte_protons=n_x,
        standard_protons=n_std,
        analyte_molar_mass=m_x,
        standard_molar_mass=m_std,
        analyte_mass_mg=w_x,
        standard_mass_mg=w_std,
        standard_purity_percent=p_std,
    )
    assert res.purity_percent == pytest.approx(true_purity, abs=0.5)


def test_internal_standard_uncertainty_is_gum_quadrature():
    res = calculate_purity_internal_standard(
        analyte_integral=1.0,
        standard_integral=1.0,
        analyte_protons=1,
        standard_protons=1,
        analyte_molar_mass=100.0,
        standard_molar_mass=100.0,
        analyte_mass_mg=10.0,
        standard_mass_mg=10.0,
        standard_purity_percent=100.0,
        integral_rel_u=0.01,
        mass_rel_u=0.001,
    )
    expected_rel = math.sqrt(2 * 0.01**2 + 2 * 0.001**2)
    assert res.relative_uncertainty == pytest.approx(expected_rel, rel=1e-4)
    assert res.uncertainty_percent == pytest.approx(100.0 * expected_rel, rel=1e-4)


def test_internal_standard_purity_over_100_warns():
    res = calculate_purity_internal_standard(
        analyte_integral=2.0,
        standard_integral=1.0,
        analyte_protons=1,
        standard_protons=1,
        analyte_molar_mass=100.0,
        standard_molar_mass=100.0,
        analyte_mass_mg=10.0,
        standard_mass_mg=10.0,
    )
    assert res.purity_percent == pytest.approx(200.0)
    assert any("exceeds 100" in w for w in res.warnings)


@pytest.mark.parametrize(
    "bad",
    [
        {"analyte_integral": 0.0},
        {"standard_integral": -1.0},
        {"analyte_protons": 0},
        {"standard_protons": -2},
        {"analyte_molar_mass": 0.0},
        {"analyte_mass_mg": 0.0},
        {"standard_purity_percent": 0.0},
        {"standard_purity_percent": 150.0},
    ],
)
def test_internal_standard_validates(bad):
    kwargs = dict(
        analyte_integral=1.0,
        standard_integral=1.0,
        analyte_protons=1,
        standard_protons=1,
        analyte_molar_mass=100.0,
        standard_molar_mass=100.0,
        analyte_mass_mg=10.0,
        standard_mass_mg=10.0,
    )
    kwargs.update(bad)
    with pytest.raises(ValueError):
        calculate_purity_internal_standard(**kwargs)


# --------------------------------------------------------------------------- #
# calculate_purity_pulcon
# --------------------------------------------------------------------------- #
def test_pulcon_closed_loop_matched_conditions():
    # Same compound as the external reference, identical acquisition; analyte is
    # 90 % pure so its integral is 90 % of the reference's at equal concentration.
    res = calculate_purity_pulcon(
        analyte_integral=0.09,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
    )
    assert res.method == "pulcon"
    assert res.purity_percent == pytest.approx(90.0, abs=1e-6)
    assert res.intermediates["measured_concentration"] == pytest.approx(0.09)


def test_pulcon_pulse_width_correction():
    # Analyte run with a 2x longer 90° pulse → half the signal per spin; the
    # pw_x/pw_ref factor restores the true 90 % purity.
    res = calculate_purity_pulcon(
        analyte_integral=0.045,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
        analyte_pulse_width_us=2.0,
        reference_pulse_width_us=1.0,
    )
    assert res.purity_percent == pytest.approx(90.0, abs=1e-6)
    assert res.intermediates["ratio_pulse_width"] == pytest.approx(2.0)


def test_pulcon_scan_count_correction():
    # Analyte co-added twice as many scans → double the raw integral; the
    # ns_ref/ns_x factor normalises it back.
    res = calculate_purity_pulcon(
        analyte_integral=0.18,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
        analyte_scans=2,
        reference_scans=1,
    )
    assert res.purity_percent == pytest.approx(90.0, abs=1e-6)
    assert res.intermediates["correction"] == pytest.approx(0.5)


def test_pulcon_reference_purity_folds_in():
    # A 95 %-pure reference at nominal 0.1 M has true concentration 0.095 M.
    res = calculate_purity_pulcon(
        analyte_integral=0.10,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
        reference_purity_percent=95.0,
    )
    assert res.intermediates["reference_concentration_true"] == pytest.approx(0.095)
    assert res.purity_percent == pytest.approx(95.0, abs=1e-6)


def test_pulcon_uncertainty_is_gum_quadrature():
    res = calculate_purity_pulcon(
        analyte_integral=0.10,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
        integral_rel_u=0.01,
        pulse_width_rel_u=0.01,
        concentration_rel_u=0.005,
    )
    expected_rel = math.sqrt(2 * 0.01**2 + 2 * 0.01**2 + 2 * 0.005**2)
    assert res.relative_uncertainty == pytest.approx(expected_rel, rel=1e-4)


def test_pulcon_purity_over_100_warns():
    res = calculate_purity_pulcon(
        analyte_integral=0.20,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
    )
    assert res.purity_percent == pytest.approx(200.0)
    assert any("exceeds 100" in w for w in res.warnings)


@pytest.mark.parametrize(
    "bad",
    [
        {"analyte_integral": 0.0},
        {"reference_integral": -1.0},
        {"analyte_protons": 0},
        {"analyte_nominal_concentration": 0.0},
        {"reference_concentration": -0.1},
        {"analyte_pulse_width_us": 0.0},
        {"analyte_scans": 0},
        {"reference_purity_percent": 0.0},
        {"reference_purity_percent": 101.0},
    ],
)
def test_pulcon_validates(bad):
    kwargs = dict(
        analyte_integral=0.10,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
    )
    kwargs.update(bad)
    with pytest.raises(ValueError):
        calculate_purity_pulcon(**kwargs)


# --------------------------------------------------------------------------- #
# PurityResult
# --------------------------------------------------------------------------- #
def test_purity_result_is_frozen():
    res = calculate_purity_pulcon(
        analyte_integral=0.10,
        analyte_protons=2,
        analyte_nominal_concentration=0.1,
        reference_integral=0.10,
        reference_protons=2,
        reference_concentration=0.1,
    )
    assert isinstance(res, PurityResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.purity_percent = 1.0  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# SMILES helpers (RDKit)
# --------------------------------------------------------------------------- #
def test_molar_mass_from_smiles_average_weight():
    # Benzene average molar mass ~ 78.11 g/mol (average, not monoisotopic 78.047).
    assert molar_mass_from_smiles("c1ccccc1") == pytest.approx(78.11, abs=0.05)


def test_total_proton_count_from_smiles():
    assert total_proton_count_from_smiles("C") == 4  # methane
    assert total_proton_count_from_smiles("c1ccccc1") == 6  # benzene


def test_smiles_helpers_reject_garbage():
    with pytest.raises(ValueError):
        molar_mass_from_smiles("not_a_smiles)(")
    with pytest.raises(ValueError):
        total_proton_count_from_smiles("not_a_smiles)(")
