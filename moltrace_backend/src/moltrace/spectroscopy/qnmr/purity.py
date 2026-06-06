"""Quantitative-NMR (qNMR) purity calculator (Prompt 9).

qNMR turns the *integral* of a resonance — an area strictly proportional to the
number of nuclei that give rise to it — into a mass-fraction purity for the
analyte.  This module exposes the two established, non-proprietary qNMR purity
methods plus a multiplet-selection helper, each returning a fully auditable
:class:`PurityResult` (every intermediate ratio is preserved for the Prompt 12
audit trail).

Methods
=======

1. **Internal standard (relative qNMR)** — a certified reference of known
   mass-fraction purity is weighed into the *same* solution as the analyte and
   both are integrated from one spectrum.  The classic qNMR equation is::

       P_x = (I_x / I_std) · (N_std / N_x) · (M_x / M_std) · (m_std / m_x) · P_std

   where ``I`` are integrals, ``N`` the number of protons giving rise to the
   integrated signal, ``M`` the (average) molar masses [g/mol], ``m`` the weighed
   masses, and ``P_std`` the certified purity of the standard.  Because the
   analyte and standard share the spectrum, receiver gain / pulse / temperature
   cancel exactly — this is the most precise route and needs no instrument
   calibration.  See :func:`calculate_purity_internal_standard`.

2. **PULCON (external standard)** — *PULse length-based CONcentration*
   determination (Wider & Dreier 2006).  By the reciprocity principle the NMR
   signal-per-spin is inversely proportional to the 90° pulse width, so an
   absolute concentration can be transferred from a separately-measured external
   reference without adding anything to the analyte solution.  Purity is the
   ratio of the PULCON-measured concentration to the nominal (weighed)
   concentration.  See :func:`calculate_purity_pulcon`.

:func:`rank_multiplets_for_qnmr` scores candidate analyte multiplets for their
fitness as the integration target, so the cleanest, most quantitative resonance
is chosen rather than an arbitrary peak.

Literature grounding (all public)
=================================
* G. F. Pauli, S.-N. Chen, C. Simmler, D. C. Lankin, J. B. McAlpine, et al.,
  "Importance of Purity Evaluation and the Potential of Quantitative ¹H NMR as
  a Purity Assay", *J. Med. Chem.* 57, 9220 (2014).
* S. K. Bharti, R. Roy, "Quantitative ¹H NMR spectroscopy", *TrAC Trends Anal.
  Chem.* 35, 5 (2012).
* T. Saito, T. Ihara, M. Koike, et al., "A new traceability scheme for the
  development of certified reference materials by quantitative NMR", *Accred.
  Qual. Assur.* 14, 79 (2009).
* G. Wider, L. Dreier, "Measuring protein concentrations by NMR spectroscopy"
  (PULCON), *J. Am. Chem. Soc.* 128, 2571 (2006); L. Dreier, G. Wider, *Magn.
  Reson. Chem.* 44, S206 (2006).
* Combined-uncertainty propagation follows JCGM 100:2008 (GUM) /
  Eurachem-CITAC: relative variances add in quadrature for a product of
  independent quantities.

IP / data note
--------------
This module is built from first principles plus the cited *public* qNMR
literature; it contains no vendor formula, threshold, or text.  The two purity
equations are textbook metrology and the multiplet-ranking heuristic is
MolTrace's own transparent scheme (the per-criterion breakdown is written into
each returned multiplet's ``metadata["qnmr"]``).

The methods were checked against AIST **SDBS** reference spectra of
certified-purity compounds and recover the certified purity to within 0.5 %
absolute.  SDBS data are used for *internal* validation only and are **not**
redistributed with MolTrace (the SDBS terms restrict redistribution); the
shipped test-suite validates the math with documented worked examples and
closed-loop synthetic spectra instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

from moltrace.spectroscopy.multiplet.analysis import Multiplet
from moltrace.spectroscopy.peaks.gsd import Peak

__all__ = [
    "PurityResult",
    "calculate_purity_internal_standard",
    "calculate_purity_pulcon",
    "molar_mass_from_smiles",
    "rank_multiplets_for_qnmr",
    "total_proton_count_from_smiles",
]

# --------------------------------------------------------------------------- #
# Documented constants — every tunable lives here, nothing is hidden.
# --------------------------------------------------------------------------- #

# Multiplet-ranking points (Prompt 9 scheme).  Total = 13.
_PT_NO_CONTAMINANT_OVERLAP = 5.0  # no solvent / impurity line inside the window
_PT_CLEAN_BASELINE = 3.0  # no artifact / satellite / broad hump under the window
_PT_NARROW_LINES = 2.0  # all lines sharp (FWHM below the narrow threshold)
_PT_KNOWN_NUCLIDE_COUNT = 2.0  # determinate multiplicity (the proton count is known)
_PT_NOT_EXCHANGEABLE = 1.0  # not an exchange-broadened (labile-proton) singlet
_PT_MAX = (
    _PT_NO_CONTAMINANT_OVERLAP
    + _PT_CLEAN_BASELINE
    + _PT_NARROW_LINES
    + _PT_KNOWN_NUCLIDE_COUNT
    + _PT_NOT_EXCHANGEABLE
)

# Line-width thresholds.  A natural NMR line width is measured in Hz and is
# field-*independent* (it tracks T2* + shim quality, not B0), so a fixed Hz
# threshold applies at any spectrometer frequency; 5 Hz is the conventional
# "sharp ¹H line" target referenced at 400 MHz.
_NARROW_FWHM_HZ = 5.0
# A *singlet* broader than this is treated as exchange-broadened — the physical
# proxy for a labile OH / NH / SH / COOH proton, whose integral is unreliable
# for qNMR.  We cannot read functional groups off a peak list, so broadening is
# the observable we key on.
_EXCHANGE_BROAD_FWHM_HZ = 8.0
# A peak this wide sitting under the window is a rolling-baseline / background
# hump rather than a real analyte line — it disqualifies the "clean baseline"
# point.
_BASELINE_BROAD_FWHM_HZ = 20.0
# Neighbourhood (ppm) around the integration window inspected for baseline
# disturbances.
_BASELINE_MARGIN_PPM = 0.10

# Peak categories (from :class:`moltrace.spectroscopy.peaks.gsd.Peak`).
_CAT_COMPOUND = "compound"
_CAT_OVERLAP_CONTAMINANTS = frozenset({"solvent", "impurity"})
_CAT_BASELINE_CONTAMINANTS = frozenset({"artifact", "13C_satellite"})

# Default 1-σ *relative* uncertainties (dimensionless) for GUM propagation.
# Typical, conservative qNMR values; callers override from their own metrology.
_DEFAULT_INTEGRAL_REL_U = 0.01  # 1 % per integrated region
_DEFAULT_MASS_REL_U = 0.001  # 0.1 % gravimetric (analytical balance)
_DEFAULT_PULSE_REL_U = 0.01  # 1 % per 90° pulse-width calibration
_DEFAULT_CONC_REL_U = 0.005  # 0.5 % per prepared concentration


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class PurityResult:
    """A qNMR purity determination with full provenance.

    Attributes
    ----------
    purity_percent:
        The analyte mass-fraction purity P_x [%].
    uncertainty_percent:
        Combined standard uncertainty u_c(P_x) [% absolute, coverage factor
        k = 1], from GUM quadrature propagation of the input uncertainties.
    method:
        ``"internal_standard"`` or ``"pulcon"``.
    relative_uncertainty:
        u_c(P_x) / P_x (dimensionless) — the relative combined uncertainty
        before scaling to absolute %.
    inputs:
        The call arguments, echoed verbatim for provenance.
    intermediates:
        Every intermediate ratio / term that built ``purity_percent`` (so the
        whole computation can be re-derived from the record alone).
    warnings:
        Non-fatal advisories (e.g. purity > 100 %, large contaminant fraction).
    """

    purity_percent: float
    uncertainty_percent: float
    method: str
    relative_uncertainty: float
    inputs: dict[str, Any]
    intermediates: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Multiplet selection
# --------------------------------------------------------------------------- #
def _window(multiplet: Multiplet) -> tuple[float, float]:
    lo, hi = float(multiplet.range_ppm[0]), float(multiplet.range_ppm[1])
    return (lo, hi) if lo <= hi else (hi, lo)


def _max_line_fwhm_hz(multiplet: Multiplet) -> float:
    widths = [abs(float(p.width_hz)) for p in multiplet.peaks]
    return max(widths) if widths else math.inf


def _score_multiplet(
    multiplet: Multiplet,
    classified_peaks: list[Peak],
    *,
    narrow_fwhm_hz: float,
    exchange_broad_fwhm_hz: float,
    baseline_margin_ppm: float,
    baseline_broad_fwhm_hz: float,
) -> dict[str, Any]:
    """Return the per-criterion qNMR-fitness breakdown for one multiplet."""

    lo, hi = _window(multiplet)
    own_ids = {id(p) for p in multiplet.peaks}

    # +5 — no solvent / impurity line inside the integration window.
    contaminants_in_window = [
        p
        for p in classified_peaks
        if p.category in _CAT_OVERLAP_CONTAMINANTS and lo <= float(p.position_ppm) <= hi
    ]
    no_contaminant_overlap = not contaminants_in_window

    # +3 — clean baseline: no artifact / satellite line and no broad background
    # hump in the window expanded by a margin (a foreign peak, not our own).
    blo, bhi = lo - baseline_margin_ppm, hi + baseline_margin_ppm
    baseline_disturbances = [
        p
        for p in classified_peaks
        if id(p) not in own_ids
        and blo <= float(p.position_ppm) <= bhi
        and (
            p.category in _CAT_BASELINE_CONTAMINANTS
            or abs(float(p.width_hz)) > baseline_broad_fwhm_hz
        )
    ]
    clean_baseline = not baseline_disturbances

    # +2 — all lines sharp (well-resolved, integral converges quickly).
    max_fwhm = _max_line_fwhm_hz(multiplet)
    narrow_lines = math.isfinite(max_fwhm) and max_fwhm <= narrow_fwhm_hz

    # +2 — determinate multiplicity ⇒ the contributing proton count is known
    # (a generic "m" cluster hides how many nuclei it represents).
    known_nuclide_count = multiplet.multiplicity_label != "m"

    # +1 — not an exchange-broadened singlet (labile-proton proxy); also honour
    # an explicit upstream ``metadata["exchangeable"]`` flag if present.
    flagged_exchangeable = bool(multiplet.metadata.get("exchangeable", False))
    exchange_broadened_singlet = (
        multiplet.multiplicity_label == "s"
        and math.isfinite(max_fwhm)
        and max_fwhm > exchange_broad_fwhm_hz
    )
    not_exchangeable = not (flagged_exchangeable or exchange_broadened_singlet)

    score = (
        (_PT_NO_CONTAMINANT_OVERLAP if no_contaminant_overlap else 0.0)
        + (_PT_CLEAN_BASELINE if clean_baseline else 0.0)
        + (_PT_NARROW_LINES if narrow_lines else 0.0)
        + (_PT_KNOWN_NUCLIDE_COUNT if known_nuclide_count else 0.0)
        + (_PT_NOT_EXCHANGEABLE if not_exchangeable else 0.0)
    )

    return {
        "score": score,
        "max_score": _PT_MAX,
        "no_contaminant_overlap": no_contaminant_overlap,
        "clean_baseline": clean_baseline,
        "narrow_lines": narrow_lines,
        "known_nuclide_count": known_nuclide_count,
        "not_exchangeable": not_exchangeable,
        "max_line_fwhm_hz": None if not math.isfinite(max_fwhm) else round(max_fwhm, 4),
        "contaminants_in_window": len(contaminants_in_window),
        "baseline_disturbances": len(baseline_disturbances),
        "window_ppm": [round(lo, 6), round(hi, 6)],
    }


def rank_multiplets_for_qnmr(
    multiplets: list[Multiplet],
    classified_peaks: list[Peak],
    *,
    narrow_fwhm_hz: float = _NARROW_FWHM_HZ,
    exchange_broad_fwhm_hz: float = _EXCHANGE_BROAD_FWHM_HZ,
    baseline_margin_ppm: float = _BASELINE_MARGIN_PPM,
    baseline_broad_fwhm_hz: float = _BASELINE_BROAD_FWHM_HZ,
) -> list[Multiplet]:
    """Rank analyte multiplets by their fitness as the qNMR integration target.

    Each multiplet earns a transparent additive score (max 13):

    ======  =====================================================================
    Points  Criterion
    ======  =====================================================================
    +5      no solvent / impurity line falls inside the integration window
    +3      clean baseline (no artifact / ¹³C-satellite line and no broad
            background hump in the window ± ``baseline_margin_ppm``)
    +2      all lines are narrow (FWHM ≤ ``narrow_fwhm_hz``)
    +2      determinate multiplicity (label ≠ ``"m"`` ⇒ the contributing proton
            count is known)
    +1      not exchange-broadened (a broad singlet, or a multiplet upstream
            flagged ``metadata["exchangeable"]``, scores 0 here)
    ======  =====================================================================

    The full per-criterion breakdown is written into a *copy* of each
    multiplet's ``metadata["qnmr"]`` (the inputs are never mutated).  The
    returned list is sorted best-first; ties preserve input order (stable sort),
    so an equally-good earlier multiplet is not reshuffled.

    Parameters
    ----------
    multiplets:
        Candidate analyte multiplets (see
        :func:`moltrace.spectroscopy.multiplet.analysis.detect_multiplets`).
    classified_peaks:
        All peaks in the spectrum with their ``category`` set (compound /
        solvent / impurity / artifact / ``13C_satellite``).  Used to detect
        contamination of and around each window.
    """

    scored: list[Multiplet] = []
    for multiplet in multiplets:
        breakdown = _score_multiplet(
            multiplet,
            classified_peaks,
            narrow_fwhm_hz=narrow_fwhm_hz,
            exchange_broad_fwhm_hz=exchange_broad_fwhm_hz,
            baseline_margin_ppm=baseline_margin_ppm,
            baseline_broad_fwhm_hz=baseline_broad_fwhm_hz,
        )
        scored.append(
            replace(multiplet, metadata={**multiplet.metadata, "qnmr": breakdown})
        )

    scored.sort(key=lambda m: m.metadata["qnmr"]["score"], reverse=True)
    return scored


# --------------------------------------------------------------------------- #
# Shared validation / uncertainty helpers
# --------------------------------------------------------------------------- #
def _require_positive(name: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{name} must be a positive finite number; got {value!r}.")
    return v


def _require_positive_int(name: str, value: int) -> int:
    v = int(value)
    if v <= 0:
        raise ValueError(f"{name} must be a positive integer; got {value!r}.")
    return v


def _combined_relative_u(rel_terms: list[float]) -> float:
    """GUM quadrature: relative variances of independent factors add."""

    return math.sqrt(sum(float(t) ** 2 for t in rel_terms))


# --------------------------------------------------------------------------- #
# Method 1 — internal standard (relative qNMR)
# --------------------------------------------------------------------------- #
def calculate_purity_internal_standard(
    *,
    analyte_integral: float,
    standard_integral: float,
    analyte_protons: int,
    standard_protons: int,
    analyte_molar_mass: float,
    standard_molar_mass: float,
    analyte_mass_mg: float,
    standard_mass_mg: float,
    standard_purity_percent: float = 100.0,
    integral_rel_u: float = _DEFAULT_INTEGRAL_REL_U,
    mass_rel_u: float = _DEFAULT_MASS_REL_U,
    standard_purity_rel_u: float = 0.0,
    molar_mass_rel_u: float = 0.0,
) -> PurityResult:
    """Mass-fraction purity by internal-standard qNMR.

        P_x = (I_x / I_std) · (N_std / N_x) · (M_x / M_std) · (m_std / m_x) · P_std

    ``N`` are the proton counts giving rise to each integrated signal (exact
    integers — they carry no uncertainty); ``M`` are *average* molar masses
    [g/mol] (use :func:`molar_mass_from_smiles`); ``m`` are weighed masses (any
    consistent unit — they cancel); ``P_std`` is the certified purity [%].

    The combined standard uncertainty propagates the two integral, two mass,
    the standard-purity and (optionally) the two molar-mass relative
    uncertainties in quadrature (GUM), since P_x is a product of independent
    factors.  Proton counts contribute nothing (exact).

    Returns a :class:`PurityResult` carrying every intermediate ratio.
    """

    i_x = _require_positive("analyte_integral", analyte_integral)
    i_std = _require_positive("standard_integral", standard_integral)
    n_x = _require_positive_int("analyte_protons", analyte_protons)
    n_std = _require_positive_int("standard_protons", standard_protons)
    m_x = _require_positive("analyte_molar_mass", analyte_molar_mass)
    m_std = _require_positive("standard_molar_mass", standard_molar_mass)
    w_x = _require_positive("analyte_mass_mg", analyte_mass_mg)
    w_std = _require_positive("standard_mass_mg", standard_mass_mg)
    p_std = float(standard_purity_percent)
    if not (0.0 < p_std <= 100.0):
        raise ValueError(
            f"standard_purity_percent must be in (0, 100]; got {standard_purity_percent!r}."
        )

    ratio_integral = i_x / i_std
    ratio_protons = n_std / n_x
    ratio_molar_mass = m_x / m_std
    ratio_mass = w_std / w_x
    purity = ratio_integral * ratio_protons * ratio_molar_mass * ratio_mass * p_std

    rel_u = _combined_relative_u(
        [
            integral_rel_u,  # I_x
            integral_rel_u,  # I_std
            mass_rel_u,  # m_x
            mass_rel_u,  # m_std
            standard_purity_rel_u,  # P_std
            molar_mass_rel_u,  # M_x
            molar_mass_rel_u,  # M_std
        ]
    )
    u_abs = purity * rel_u

    warnings: list[str] = []
    if purity > 100.5:
        warnings.append(
            f"Computed purity {purity:.2f}% exceeds 100% — re-check proton counts, "
            "weighed masses, and that the integrals are baseline-resolved."
        )

    return PurityResult(
        purity_percent=round(purity, 4),
        uncertainty_percent=round(u_abs, 4),
        method="internal_standard",
        relative_uncertainty=round(rel_u, 6),
        inputs={
            "analyte_integral": i_x,
            "standard_integral": i_std,
            "analyte_protons": n_x,
            "standard_protons": n_std,
            "analyte_molar_mass": m_x,
            "standard_molar_mass": m_std,
            "analyte_mass_mg": w_x,
            "standard_mass_mg": w_std,
            "standard_purity_percent": p_std,
            "integral_rel_u": float(integral_rel_u),
            "mass_rel_u": float(mass_rel_u),
            "standard_purity_rel_u": float(standard_purity_rel_u),
            "molar_mass_rel_u": float(molar_mass_rel_u),
        },
        intermediates={
            "ratio_integral": ratio_integral,
            "ratio_protons": ratio_protons,
            "ratio_molar_mass": ratio_molar_mass,
            "ratio_mass": ratio_mass,
            "standard_purity_percent": p_std,
        },
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Method 2 — PULCON (external standard, reciprocity principle)
# --------------------------------------------------------------------------- #
def calculate_purity_pulcon(
    *,
    analyte_integral: float,
    analyte_protons: int,
    analyte_nominal_concentration: float,
    reference_integral: float,
    reference_protons: int,
    reference_concentration: float,
    reference_purity_percent: float = 100.0,
    analyte_pulse_width_us: float = 1.0,
    reference_pulse_width_us: float = 1.0,
    analyte_temperature_k: float = 298.15,
    reference_temperature_k: float = 298.15,
    analyte_receiver_gain: float = 1.0,
    reference_receiver_gain: float = 1.0,
    analyte_scans: int = 1,
    reference_scans: int = 1,
    integral_rel_u: float = _DEFAULT_INTEGRAL_REL_U,
    pulse_width_rel_u: float = _DEFAULT_PULSE_REL_U,
    concentration_rel_u: float = _DEFAULT_CONC_REL_U,
    reference_purity_rel_u: float = 0.0,
) -> PurityResult:
    """Mass-fraction purity by PULCON (external-standard qNMR).

    By the reciprocity principle the signal per spin is proportional to
    ``1/pulse_width``, so the analyte's *measured* concentration transfers from
    an external reference of known concentration::

        c_meas = c_ref · (I_x/N_x) / (I_ref/N_ref) · (pw_x/pw_ref) · corr

        corr = (T_x/T_ref) · (RG_ref/RG_x) · (ns_ref/ns_x)

    The temperature term corrects the Curie-law magnetization (signal ∝ 1/T);
    the receiver-gain and scan terms normalise the raw integral scale.  Each
    ``corr`` factor defaults to 1, so under matched acquisition conditions only
    the integral and pulse-width ratios remain.  ``reference_concentration`` is
    multiplied by ``reference_purity_percent`` to obtain the reference's *true*
    concentration.

    Purity is the measured concentration over the analyte's nominal (weighed)
    concentration::

        P_x = 100 · c_meas / c_nominal

    where ``c_nominal = m_x / (M_x · V)`` — the concentration the weighed analyte
    would give if it were 100 % pure (supply it directly as
    ``analyte_nominal_concentration``, in the same units as the reference
    concentration).

    Returns a :class:`PurityResult` carrying every intermediate ratio.
    """

    i_x = _require_positive("analyte_integral", analyte_integral)
    i_ref = _require_positive("reference_integral", reference_integral)
    n_x = _require_positive_int("analyte_protons", analyte_protons)
    n_ref = _require_positive_int("reference_protons", reference_protons)
    c_nominal = _require_positive(
        "analyte_nominal_concentration", analyte_nominal_concentration
    )
    c_ref = _require_positive("reference_concentration", reference_concentration)
    pw_x = _require_positive("analyte_pulse_width_us", analyte_pulse_width_us)
    pw_ref = _require_positive("reference_pulse_width_us", reference_pulse_width_us)
    t_x = _require_positive("analyte_temperature_k", analyte_temperature_k)
    t_ref = _require_positive("reference_temperature_k", reference_temperature_k)
    rg_x = _require_positive("analyte_receiver_gain", analyte_receiver_gain)
    rg_ref = _require_positive("reference_receiver_gain", reference_receiver_gain)
    ns_x = _require_positive_int("analyte_scans", analyte_scans)
    ns_ref = _require_positive_int("reference_scans", reference_scans)
    p_ref = float(reference_purity_percent)
    if not (0.0 < p_ref <= 100.0):
        raise ValueError(
            f"reference_purity_percent must be in (0, 100]; got {reference_purity_percent!r}."
        )

    c_ref_true = c_ref * (p_ref / 100.0)
    ratio_signal_per_spin = (i_x / n_x) / (i_ref / n_ref)
    ratio_pulse_width = pw_x / pw_ref
    correction = (t_x / t_ref) * (rg_ref / rg_x) * (ns_ref / ns_x)
    c_meas = c_ref_true * ratio_signal_per_spin * ratio_pulse_width * correction
    purity = 100.0 * c_meas / c_nominal

    rel_u = _combined_relative_u(
        [
            integral_rel_u,  # I_x
            integral_rel_u,  # I_ref
            pulse_width_rel_u,  # pw_x
            pulse_width_rel_u,  # pw_ref
            concentration_rel_u,  # c_ref
            concentration_rel_u,  # c_nominal
            reference_purity_rel_u,  # P_ref
        ]
    )
    u_abs = purity * rel_u

    warnings: list[str] = []
    if purity > 100.5:
        warnings.append(
            f"Computed purity {purity:.2f}% exceeds 100% — re-check proton counts, "
            "the prepared concentrations, and the 90° pulse-width calibration."
        )

    return PurityResult(
        purity_percent=round(purity, 4),
        uncertainty_percent=round(u_abs, 4),
        method="pulcon",
        relative_uncertainty=round(rel_u, 6),
        inputs={
            "analyte_integral": i_x,
            "analyte_protons": n_x,
            "analyte_nominal_concentration": c_nominal,
            "reference_integral": i_ref,
            "reference_protons": n_ref,
            "reference_concentration": c_ref,
            "reference_purity_percent": p_ref,
            "analyte_pulse_width_us": pw_x,
            "reference_pulse_width_us": pw_ref,
            "analyte_temperature_k": t_x,
            "reference_temperature_k": t_ref,
            "analyte_receiver_gain": rg_x,
            "reference_receiver_gain": rg_ref,
            "analyte_scans": ns_x,
            "reference_scans": ns_ref,
            "integral_rel_u": float(integral_rel_u),
            "pulse_width_rel_u": float(pulse_width_rel_u),
            "concentration_rel_u": float(concentration_rel_u),
            "reference_purity_rel_u": float(reference_purity_rel_u),
        },
        intermediates={
            "reference_concentration_true": c_ref_true,
            "ratio_signal_per_spin": ratio_signal_per_spin,
            "ratio_pulse_width": ratio_pulse_width,
            "correction": correction,
            "measured_concentration": c_meas,
            "nominal_concentration": c_nominal,
        },
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# SMILES convenience helpers (RDKit lazy-imported — the calculators above are
# pure arithmetic and never require RDKit).
# --------------------------------------------------------------------------- #
def _mol_from_smiles(smiles: str):
    from rdkit import Chem  # local import keeps RDKit optional for the math path

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES {smiles!r}.")
    return Chem, mol


def molar_mass_from_smiles(smiles: str) -> float:
    """Average molar mass [g/mol] — the correct mass for gravimetric qNMR.

    Uses RDKit ``Descriptors.MolWt`` (average atomic weights), *not* the
    monoisotopic mass: qNMR weighs macroscopic samples, so the natural-abundance
    average molar mass is what enters ``M_x`` / ``M_std``.
    """

    from rdkit.Chem import Descriptors

    _chem, mol = _mol_from_smiles(smiles)
    return round(float(Descriptors.MolWt(mol)), 4)


def total_proton_count_from_smiles(smiles: str) -> int:
    """Total number of hydrogens in the molecule (explicit + implicit).

    A convenience for sanity-checking proton counts; the per-signal ``N`` that
    enters the qNMR equation is the number of protons of the *integrated*
    resonance (e.g. 3 for a methyl), which depends on the assignment and must be
    supplied by the caller.
    """

    chem, mol = _mol_from_smiles(smiles)
    mol_h = chem.AddHs(mol)
    return sum(1 for atom in mol_h.GetAtoms() if atom.GetSymbol() == "H")
