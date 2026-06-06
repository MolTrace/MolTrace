"""Solvent / residual-solvent / impurity expert system (Prompt 10).

This module is the **source of truth** for *solvent and impurity identity* in
MolTrace.  Prompt 3's :func:`moltrace.spectroscopy.peaks.gsd.auto_classify`
remains the per-spectrum classifier that walks every GSD peak, but when it needs
to decide *which* deuterated solvent a spectrum was acquired in, or whether a
given line is the bulk solvent, a leftover process solvent, a trace impurity, a
¹³C satellite, or an instrumental artifact, this module holds the authoritative
reference data and decision rules.

Two public entry points implement the Prompt 10 contract:

``detect_solvent(spectrum, peaks) -> str``
    Return the most likely deuterated NMR solvent (canonical name, e.g.
    ``"CDCl3"``) inferred from the *pattern of peak positions* — i.e. which
    solvent's residual signature best explains the observed prominent peaks.

``classify_peak(peak, spectrum_solvent, all_peaks) -> tuple[str, float]``
    Return ``(category, confidence)`` where ``category`` is one of::

        compound | solvent | residual_solvent | impurity | 13C_satellite | artifact

    * ``solvent``         — residual protio signal of the deuterated solvent in use
    * ``residual_solvent``— a leftover volatile *process* solvent (EtOAc, hexanes,
                            DCM, THF, Et2O, …; ICH Q3C class)
    * ``impurity``        — a non-solvent contaminant (water, grease, BHT, TMS, …)
    * ``13C_satellite``   — the symmetric ±½·¹J(C,H) partner of a strong ¹²C-bound
                            proton resonance
    * ``artifact``        — out-of-range, anomalous line width, or below the noise
                            floor

Scoring scheme (Prompt 10 specification, realised as additive evidence)::

    + high   position match to the solvent / impurity table
    + med    ¹³C-satellite pattern detection
    + med    line-width anomaly
    + high   outside the reasonable chemical-shift range
    + low    intensity below the noise threshold

``high`` evidence on its own classifies a peak; ``med`` evidence on its own
classifies a peak; ``low`` evidence on its own does *not* (it only tips the
balance when it stacks with another signal) — so a merely weak but otherwise
ordinary compound peak stays ``compound``.  When no rule fires the peak is
``compound`` and the confidence reports how cleanly it cleared every alternative.

Reference data
==============
All chemical-shift values are drawn from the standard published residual-solvent
and trace-impurity tables:

* G. R. Fulmer, A. J. M. Miller, N. H. Sherden, H. E. Gottlieb, A. Nudelman,
  B. M. Stoltz, J. E. Bercaw, K. I. Goldberg, "NMR Chemical Shifts of Trace
  Impurities: Common Laboratory Solvents, Organics, and Gases in Deuterated
  Solvents Relevant to the Organometallic Chemist", *Organometallics* 29, 2176
  (2010). DOI 10.1021/om100106e.
* Predecessor table: H. E. Gottlieb, V. Kotlyar, A. Nudelman, "NMR Chemical
  Shifts of Common Laboratory Solvents as Trace Impurities", *J. Org. Chem.* 62,
  7512 (1997).

The registry key for the Fulmer citation in :mod:`nmrcheck.literature_data` is
``"fulmer_2010_solvent_impurities"``.

IP / data note
--------------
Chemical-shift values are *measured physical facts* and are not copyrightable;
they are reproduced here from the cited public literature with attribution as
good scientific practice.  The decision rules, the confidence-scoring scheme,
and the ¹³C-satellite geometry are MolTrace's own first-principles work and
contain no vendor formula, threshold, or text.  One-bond ¹H–¹³C coupling
constants (¹J ≈ 125 Hz for sp³ C–H, ≈ 160 Hz for sp² C–H) are textbook values
(Silverstein/Webster/Kiemle; Friebolin).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Literal

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import Peak

__all__ = [
    "COMMON_IMPURITIES",
    "DEUTERATED_SOLVENTS",
    "SolventImpurityCategory",
    "classify_peak",
    "classify_peaks",
    "detect_solvent",
]

SolventImpurityCategory = Literal[
    "compound",
    "solvent",
    "residual_solvent",
    "impurity",
    "13C_satellite",
    "artifact",
]

# --------------------------------------------------------------------------- #
# Documented constants — every tunable lives here, nothing is hidden.
# --------------------------------------------------------------------------- #

# Evidence weights for the Prompt 10 scoring scheme.  A "high" signal alone
# classifies (>= the decision threshold); a "med" signal alone classifies; a
# "low" signal alone does not (0.30 < 0.45) and only matters when it stacks.
_SCORE_HIGH: float = 0.90
_SCORE_MED: float = 0.58
_SCORE_LOW: float = 0.30
_DECISION_THRESHOLD: float = 0.45
# Floor for a clean compound peak's confidence when nothing competes for it.
_COMPOUND_CONFIDENCE_FLOOR: float = 0.55

# Default spectrometer field if it cannot be recovered from the peaks/metadata.
_DEFAULT_FIELD_MHZ: float = 500.0

# Reasonable first-order chemical-shift windows.  A peak outside these is almost
# never a genuine analyte resonance — it is folded/aliased, a baseline glitch,
# or a referencing error, i.e. an artifact.
_REASONABLE_RANGE_PPM: dict[str, tuple[float, float]] = {
    "1H": (-2.0, 16.0),
    "13C": (-10.0, 235.0),
}

# Absolute line-width floors for the "anomalously broad" artifact test.  Mirrors
# the gsd.auto_classify floors so the two layers agree: a peak is only "broad"
# if it is BOTH > 2x the spectrum's median width AND above the nucleus floor
# (otherwise legitimately broad ¹³C lines or exchanging OH/NH get mislabelled).
_BROAD_WIDTH_FLOOR_HZ: dict[str, float] = {"1H": 25.0, "13C": 60.0}
# A line far narrower than a real resonance is a digital spike, not signal.
_SPIKE_WIDTH_FLOOR_HZ: float = 0.15

# ¹³C-satellite geometry.  Satellites sit at ±½·¹J(C,H) about a strong ¹²C-bound
# parent and carry ~0.55 % of its intensity each (¹³C natural abundance 1.1 %
# split into two lines).  Accept a wider band for SNR-limited / overlapped
# parents, matching gsd._MIN/_MAX_SATELLITE_RATIO.
_J_CH_HZ: tuple[float, ...] = (125.0, 160.0)
_MIN_SATELLITE_RATIO: float = 0.003
_MAX_SATELLITE_RATIO: float = 0.025

# Below-noise test: prefer the GSD-provided S/N; otherwise fall back to a
# fraction-of-tallest-peak heuristic.
_MIN_SIGNAL_TO_NOISE: float = 3.0
_BELOW_NOISE_INTENSITY_FRACTION: float = 0.004

# A trace impurity / residual process solvent is by definition a *minority*
# signal: a line carrying more than this fraction of the tallest peak's
# intensity is too dominant to be a contaminant and is left as compound (an
# aliphatic analyte methyl at ~1.2 ppm otherwise collides with the diethyl
# ether / ethanol / EtOAc impurity shifts).  The bulk-solvent residual is
# exempt — it is legitimately allowed to be one of the tallest peaks.  Mirrors
# the 0.4 gate in gsd.auto_classify's ``_detail_is_impurity``.
_IMPURITY_MAX_PROMINENCE: float = 0.5


@dataclass(slots=True, frozen=True)
class DeuteratedSolvent:
    """One deuterated NMR solvent and its residual signature.

    ``residual_1h`` / ``residual_13c`` are the residual *protio* solvent
    resonance(s) (the lines actually observed because deuteration is never
    100 %).  ``water_1h`` is the trace-water (HDO) position in that solvent —
    tracked for :func:`detect_solvent` context but classified as an *impurity*,
    not as the solvent itself.
    """

    canonical_name: str
    aliases: tuple[str, ...]
    residual_1h: tuple[float, ...]
    residual_13c: tuple[float, ...]
    water_1h: float | None
    tol_1h_ppm: float = 0.06
    tol_13c_ppm: float = 0.6


# 14 deuterated solvents.  The first seven are the canonical Fulmer/Gottlieb
# table columns; the remaining seven are the next most common deuterated NMR
# solvents, with residual shifts from Fulmer's extended tables and standard
# vendor reference charts.  ¹H values agree with nmrcheck.solvents /
# nmrcheck.impurities and the gsd residual-probe tables.
DEUTERATED_SOLVENTS: tuple[DeuteratedSolvent, ...] = (
    DeuteratedSolvent(
        "CDCl3", ("cdcl3", "chloroform-d", "chloroform-d1"),
        residual_1h=(7.26,), residual_13c=(77.16,), water_1h=1.56,
    ),
    DeuteratedSolvent(
        "DMSO-d6", ("dmso-d6", "dmso", "(cd3)2so", "d6-dmso"),
        residual_1h=(2.50,), residual_13c=(39.52,), water_1h=3.33,
    ),
    DeuteratedSolvent(
        "CD3OD", ("cd3od", "methanol-d4", "meod", "methanol-d", "cd3od4"),
        residual_1h=(3.31,), residual_13c=(49.00,), water_1h=4.87,
    ),
    DeuteratedSolvent(
        "D2O", ("d2o", "deuterium oxide", "heavy water"),
        residual_1h=(), residual_13c=(), water_1h=4.79,
    ),
    DeuteratedSolvent(
        "acetone-d6", ("acetone-d6", "(cd3)2co", "d6-acetone"),
        residual_1h=(2.05,), residual_13c=(29.84, 206.26), water_1h=2.84,
    ),
    DeuteratedSolvent(
        "CD3CN", ("cd3cn", "acetonitrile-d3", "mecn-d3"),
        residual_1h=(1.94,), residual_13c=(1.32, 118.26), water_1h=2.13,
    ),
    DeuteratedSolvent(
        "C6D6", ("c6d6", "benzene-d6"),
        residual_1h=(7.16,), residual_13c=(128.06,), water_1h=0.40,
    ),
    DeuteratedSolvent(
        "pyridine-d5", ("pyridine-d5", "c5d5n"),
        residual_1h=(8.74, 7.58, 7.22), residual_13c=(150.35, 135.91, 123.87),
        water_1h=4.99, tol_1h_ppm=0.10,
    ),
    DeuteratedSolvent(
        "THF-d8", ("thf-d8", "tetrahydrofuran-d8"),
        residual_1h=(3.58, 1.72), residual_13c=(67.21, 25.31),
        water_1h=2.46, tol_1h_ppm=0.08,
    ),
    DeuteratedSolvent(
        "toluene-d8", ("toluene-d8", "c7d8"),
        residual_1h=(7.09, 7.00, 6.98, 2.08),
        residual_13c=(137.86, 129.24, 128.33, 125.49, 20.43),
        water_1h=0.43, tol_1h_ppm=0.08,
    ),
    DeuteratedSolvent(
        "CD2Cl2", ("cd2cl2", "dichloromethane-d2", "methylene chloride-d2", "dcm-d2"),
        residual_1h=(5.32,), residual_13c=(53.84,), water_1h=1.52,
    ),
    DeuteratedSolvent(
        "DMF-d7", ("dmf-d7", "n,n-dimethylformamide-d7", "dimethylformamide-d7"),
        residual_1h=(8.03, 2.92, 2.75), residual_13c=(163.15, 34.89, 29.76),
        water_1h=3.46, tol_1h_ppm=0.08,
    ),
    DeuteratedSolvent(
        "dioxane-d8", ("dioxane-d8", "1,4-dioxane-d8", "p-dioxane-d8"),
        residual_1h=(3.53,), residual_13c=(66.50,), water_1h=2.43,
    ),
    DeuteratedSolvent(
        "C2D2Cl4", ("c2d2cl4", "1,1,2,2-tetrachloroethane-d2", "tetrachloroethane-d2"),
        residual_1h=(6.00,), residual_13c=(73.78,), water_1h=None,
    ),
)


@dataclass(slots=True, frozen=True)
class ImpurityShift:
    """One diagnostic resonance of a common impurity in a given solvent.

    ``kind`` is ``"residual_solvent"`` for leftover volatile process solvents
    and ``"impurity"`` for non-solvent contaminants (water, greases, antioxidant
    additives, the TMS reference).  ``solvent`` is the canonical deuterated
    solvent column the shift was tabulated in (``None`` for the solvent-agnostic
    ¹³C entries, whose carbon shifts vary little with solvent).
    """

    label: str
    proton: str
    kind: Literal["residual_solvent", "impurity"]
    shift_ppm: float
    solvent: str | None
    tol_ppm: float = 0.05


# Fulmer ¹H impurity table columns, in the published order.
_H1_COLUMNS: tuple[str, ...] = (
    "CDCl3", "acetone-d6", "DMSO-d6", "C6D6", "CD3CN", "CD3OD", "D2O",
)
# 7-tuple of per-column ppm; ``None`` where the impurity is not tabulated.
_H1Cells = tuple[float | None, ...]


def _h1_rows(
    name: str,
    proton: str,
    kind: Literal["residual_solvent", "impurity"],
    values: _H1Cells,
    *,
    tol_ppm: float = 0.05,
) -> tuple[ImpurityShift, ...]:
    """Expand one Fulmer ¹H table row into per-solvent :class:`ImpurityShift`s."""
    label = f"{name} {proton}".strip()
    rows: list[ImpurityShift] = []
    for solvent, value in zip(_H1_COLUMNS, values, strict=True):
        if value is None:
            continue
        rows.append(ImpurityShift(label, proton, kind, float(value), solvent, tol_ppm))
    return tuple(rows)


_RS = "residual_solvent"
_IM = "impurity"

# Common ¹H impurities, Fulmer 2010 Table 1 (CDCl3, acetone-d6, DMSO-d6, C6D6,
# CD3CN, CD3OD, D2O).  Process solvents are tagged residual_solvent; non-solvent
# contaminants are tagged impurity.
COMMON_IMPURITIES: tuple[ImpurityShift, ...] = (
    *_h1_rows("water", "H2O", _IM, (1.56, 2.84, 3.33, 0.40, 2.13, 4.87, None), tol_ppm=0.10),
    *_h1_rows("TMS", "Si(CH3)4", _IM, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), tol_ppm=0.03),
    *_h1_rows("acetic acid", "CH3", _RS, (2.10, 1.96, 1.91, 1.55, 1.96, 1.99, 2.08)),
    *_h1_rows("acetone", "CH3", _RS, (2.17, 2.09, 2.09, 1.55, 2.08, 2.15, 2.22)),
    *_h1_rows("acetonitrile", "CH3", _RS, (2.10, 2.05, 2.07, 1.55, 1.96, 2.03, 2.06)),
    *_h1_rows("benzene", "CH", _RS, (7.36, 7.36, 7.37, 7.15, 7.37, 7.33, None)),
    *_h1_rows("BHT", "ArCH3", _IM, (2.27, 2.22, 2.18, 2.24, 2.22, 2.21, None)),
    *_h1_rows("BHT", "C(CH3)3", _IM, (1.43, 1.41, 1.36, 1.38, 1.39, 1.40, None)),
    *_h1_rows("tert-butyl methyl ether", "OCH3", _RS, (3.22, 3.13, 3.08, 3.04, 3.13, 3.20, 3.22)),
    *_h1_rows("tert-butyl methyl ether", "CCH3", _RS, (1.19, 1.13, 1.11, 1.07, 1.14, 1.15, 1.21)),
    *_h1_rows("chloroform", "CH", _RS, (7.26, 8.02, 8.32, 6.15, 7.58, 7.90, None)),
    *_h1_rows("cyclohexane", "CH2", _RS, (1.43, 1.43, 1.40, 1.40, 1.44, 1.45, None)),
    *_h1_rows("1,2-dichloroethane", "CH2", _RS, (3.73, 3.87, 3.90, 2.90, 3.81, 3.78, None)),
    *_h1_rows("dichloromethane", "CH2", _RS, (5.30, 5.63, 5.76, 4.27, 5.44, 5.49, None)),
    *_h1_rows("diethyl ether", "CH3", _RS, (1.21, 1.11, 1.09, 1.11, 1.12, 1.18, 1.17)),
    *_h1_rows("diethyl ether", "CH2", _RS, (3.48, 3.41, 3.38, 3.26, 3.42, 3.49, 3.56)),
    *_h1_rows("1,2-dimethoxyethane", "OCH3", _RS, (3.40, 3.28, 3.24, 3.12, 3.28, 3.35, 3.37)),
    *_h1_rows("1,2-dimethoxyethane", "CH2", _RS, (3.55, 3.46, 3.43, 3.33, 3.45, 3.52, 3.60)),
    *_h1_rows("dimethylformamide", "CH", _RS, (8.02, 7.96, 7.95, 7.63, 7.92, 7.97, 7.92)),
    *_h1_rows("dimethylformamide", "CH3", _RS, (2.96, 2.94, 2.89, 2.36, 2.89, 2.99, 3.01)),
    *_h1_rows("dimethyl sulfoxide", "CH3", _RS, (2.62, 2.52, 2.54, 1.68, 2.50, 2.65, 2.71)),
    *_h1_rows("dioxane", "CH2", _RS, (3.71, 3.59, 3.57, 3.35, 3.60, 3.66, 3.75)),
    *_h1_rows("ethanol", "CH3", _RS, (1.25, 1.12, 1.06, 0.96, 1.12, 1.19, 1.17)),
    *_h1_rows("ethanol", "CH2", _RS, (3.72, 3.57, 3.44, 3.34, 3.54, 3.60, 3.65)),
    *_h1_rows("ethyl acetate", "CH3CO", _RS, (2.05, 1.97, 1.99, 1.65, 1.97, 2.01, 2.07)),
    *_h1_rows("ethyl acetate", "OCH2CH3", _RS, (4.12, 4.05, 4.03, 3.89, 4.06, 4.09, 4.14)),
    *_h1_rows("ethyl acetate", "CH3", _RS, (1.26, 1.20, 1.17, 0.92, 1.20, 1.24, 1.24)),
    *_h1_rows("ethylene glycol", "CH", _IM, (3.76, 3.28, 3.34, 3.41, 3.51, 3.59, 3.65)),
    *_h1_rows("grease", "CH2", _IM, (1.26, 1.29, None, 1.36, 1.27, 1.29, None), tol_ppm=0.08),
    *_h1_rows("n-hexane", "CH3", _RS, (0.88, 0.88, 0.86, 0.89, 0.89, 0.90, None)),
    *_h1_rows("n-hexane", "CH2", _RS, (1.26, 1.28, 1.25, 1.24, 1.28, 1.29, None)),
    *_h1_rows("methanol", "CH3", _RS, (3.49, 3.31, 3.16, None, 3.28, 3.34, 3.34)),
    *_h1_rows("nitromethane", "CH3", _RS, (4.33, 4.43, 4.42, 2.94, 4.31, 4.34, 4.40)),
    *_h1_rows("n-pentane", "CH3", _RS, (0.88, 0.88, 0.86, 0.87, 0.89, 0.90, None)),
    *_h1_rows("n-pentane", "CH2", _RS, (1.27, 1.27, 1.27, 1.23, 1.29, 1.29, None)),
    *_h1_rows("2-propanol", "CH3", _RS, (1.22, 1.10, 1.04, 0.95, 1.09, 1.50, 1.17)),
    *_h1_rows("2-propanol", "CH", _RS, (4.04, 3.90, 3.78, 3.67, 3.87, 3.92, 4.02)),
    *_h1_rows("pyridine", "CH(2)", _RS, (8.62, 8.58, 8.58, 8.53, 8.57, 8.53, 8.52)),
    *_h1_rows(
        "silicone grease", "CH3", _IM, (0.07, 0.13, None, 0.29, 0.08, 0.10, None), tol_ppm=0.08
    ),
    *_h1_rows("tetrahydrofuran", "CH2", _RS, (1.85, 1.79, 1.76, 1.40, 1.80, 1.87, 1.88)),
    *_h1_rows("tetrahydrofuran", "OCH2", _RS, (3.76, 3.63, 3.60, 3.57, 3.64, 3.71, 3.74)),
    *_h1_rows("toluene", "CH3", _RS, (2.36, 2.32, 2.30, 2.11, 2.33, 2.32, None)),
    *_h1_rows("triethylamine", "CH3", _RS, (1.03, 0.96, 0.93, 0.96, 0.96, 1.05, 0.99)),
    *_h1_rows("triethylamine", "CH2", _RS, (2.53, 2.45, 2.43, 2.40, 2.45, 2.58, 2.57)),
)


# Common ¹³C impurity carbons (Fulmer 2010 Table 2).  ¹³C shifts are far less
# solvent-dependent than ¹H, so a single representative value per carbon with a
# generous tolerance is used (``solvent=None`` => matches in any solvent).
_C13_IMPURITIES: tuple[ImpurityShift, ...] = (
    ImpurityShift("acetone CH3", "CH3", _RS, 30.92, None, 0.6),
    ImpurityShift("acetone C=O", "C=O", _RS, 206.68, None, 1.0),
    ImpurityShift("acetic acid CH3", "CH3", _RS, 20.81, None, 0.6),
    ImpurityShift("acetic acid C=O", "C=O", _RS, 175.99, None, 1.0),
    ImpurityShift("acetonitrile CN", "CN", _RS, 118.26, None, 0.6),
    ImpurityShift("benzene CH", "CH", _RS, 128.36, None, 0.6),
    ImpurityShift("tert-butyl methyl ether OCH3", "OCH3", _RS, 49.45, None, 0.6),
    ImpurityShift("chloroform CH", "CH", _RS, 77.36, None, 0.7),
    ImpurityShift("cyclohexane CH2", "CH2", _RS, 26.94, None, 0.6),
    ImpurityShift("dichloromethane CH2", "CH2", _RS, 53.52, None, 0.6),
    ImpurityShift("diethyl ether CH3", "CH3", _RS, 15.20, None, 0.6),
    ImpurityShift("diethyl ether CH2", "CH2", _RS, 65.91, None, 0.6),
    ImpurityShift("dimethylformamide C=O", "C=O", _RS, 162.62, None, 1.0),
    ImpurityShift("dioxane CH2", "CH2", _RS, 67.14, None, 0.6),
    ImpurityShift("ethanol CH3", "CH3", _RS, 18.41, None, 0.6),
    ImpurityShift("ethanol CH2", "CH2", _RS, 58.28, None, 0.6),
    ImpurityShift("ethyl acetate C=O", "C=O", _RS, 171.36, None, 1.0),
    ImpurityShift("ethyl acetate OCH2", "OCH2", _RS, 60.49, None, 0.6),
    ImpurityShift("ethyl acetate CH3CO", "CH3CO", _RS, 21.04, None, 0.6),
    ImpurityShift("n-hexane CH3", "CH3", _RS, 14.14, None, 0.6),
    ImpurityShift("n-hexane CH2", "CH2", _RS, 22.70, None, 0.6),
    ImpurityShift("methanol CH3", "CH3", _RS, 50.41, None, 0.6),
    ImpurityShift("2-propanol CH3", "CH3", _RS, 25.14, None, 0.6),
    ImpurityShift("2-propanol CH", "CH", _RS, 64.50, None, 0.6),
    ImpurityShift("tetrahydrofuran OCH2", "OCH2", _RS, 67.97, None, 0.6),
    ImpurityShift("tetrahydrofuran CH2", "CH2", _RS, 25.62, None, 0.6),
    ImpurityShift("toluene CH3", "CH3", _RS, 21.46, None, 0.6),
    ImpurityShift("triethylamine CH3", "CH3", _IM, 11.61, None, 0.6),
    ImpurityShift("triethylamine CH2", "CH2", _IM, 46.25, None, 0.6),
    ImpurityShift("silicone grease CH3", "CH3", _IM, 1.04, None, 0.6),
    ImpurityShift("grease CH2", "CH2", _IM, 29.76, None, 1.2),
)


# --------------------------------------------------------------------------- #
# Solvent-name normalisation
# --------------------------------------------------------------------------- #

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _solv in DEUTERATED_SOLVENTS:
    _ALIAS_TO_CANONICAL[_solv.canonical_name.lower()] = _solv.canonical_name
    for _alias in _solv.aliases:
        _ALIAS_TO_CANONICAL[_alias.lower()] = _solv.canonical_name
_SOLVENT_BY_CANONICAL: dict[str, DeuteratedSolvent] = {
    _solv.canonical_name: _solv for _solv in DEUTERATED_SOLVENTS
}


def _canonical_solvent(name: str | None) -> str | None:
    """Map any spelling/alias of a deuterated solvent to its canonical name."""
    if not name:
        return None
    key = str(name).strip().lower()
    if not key:
        return None
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    # Tolerate punctuation/spacing differences (e.g. "DMSO_d6", "CDCl3 ").
    squashed = key.replace("-", "").replace("_", "").replace(" ", "")
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if alias.replace("-", "").replace("_", "").replace(" ", "") == squashed:
            return canonical
    return None


# --------------------------------------------------------------------------- #
# Nucleus / field inference (classify_peak gets no spectrum, only peaks)
# --------------------------------------------------------------------------- #


def _normalise_nucleus(nucleus: str | None) -> str:
    value = str(nucleus or "").strip().upper().replace("¹³", "13").replace("¹", "1")
    if value in {"1H", "H1", "PROTON"}:
        return "1H"
    if value in {"13C", "C13", "CARBON13", "CARBON-13"}:
        return "13C"
    return value or "1H"


def _infer_nucleus(peaks: list[Peak]) -> str:
    """¹H vs ¹³C from the distribution of peak positions.

    ¹H spectra essentially never exceed ~16 ppm and cluster at 0–10; ¹³C
    routinely spans 0–220 ppm with carbons rarely below ~14.  The *median*
    position is the robust discriminator (a single downfield ¹H artifact must
    not flip the whole spectrum to ¹³C), backed up by a max-position rule that
    catches sparse ¹³C spectra whose median happens to land low.
    """
    positions = [abs(float(p.position_ppm)) for p in peaks if math.isfinite(float(p.position_ppm))]
    if not positions:
        return "1H"
    if float(median(positions)) > 16.0:
        return "13C"
    if len(positions) >= 2 and max(positions) > 30.0:
        return "13C"
    return "1H"


def _infer_field_mhz(peaks: list[Peak]) -> float:
    """Recover the spectrometer field from ``position_hz / position_ppm``."""
    ratios = [
        abs(float(p.position_hz) / float(p.position_ppm))
        for p in peaks
        if abs(float(p.position_ppm)) > 0.5
        and math.isfinite(float(p.position_hz))
        and math.isfinite(float(p.position_ppm))
    ]
    if not ratios:
        return _DEFAULT_FIELD_MHZ
    value = float(median(ratios))
    return value if math.isfinite(value) and value > 0 else _DEFAULT_FIELD_MHZ


def _proximity(delta: float, tol: float) -> float | None:
    """Match-closeness in ``(0.5, 1.0]`` if within ``tol``, else ``None``.

    A dead-on hit scores 1.0; a hit at the tolerance edge scores 0.5 (so even an
    edge match × ``_SCORE_HIGH`` = 0.45 still clears the decision threshold).
    """
    if tol <= 0:
        return 1.0 if delta == 0 else None
    if delta > tol:
        return None
    return max(0.5, 1.0 - 0.5 * (delta / tol))


# --------------------------------------------------------------------------- #
# Per-category evidence
# --------------------------------------------------------------------------- #


def _match_bulk_solvent(peak_ppm: float, solvent: str | None, nucleus: str) -> float | None:
    """Proximity if ``peak_ppm`` is the in-use solvent's residual line."""
    canonical = _canonical_solvent(solvent)
    if canonical is None:
        return None
    profile = _SOLVENT_BY_CANONICAL[canonical]
    shifts = profile.residual_1h if nucleus == "1H" else profile.residual_13c
    tol = profile.tol_1h_ppm if nucleus == "1H" else profile.tol_13c_ppm
    best: float | None = None
    for shift in shifts:
        prox = _proximity(abs(peak_ppm - shift), tol)
        if prox is not None and (best is None or prox > best):
            best = prox
    return best


def _match_impurity(
    peak_ppm: float, solvent: str | None, nucleus: str
) -> tuple[str, str, float] | None:
    """Best impurity-table hit as ``(category, label, proximity)`` or ``None``.

    ¹³C shifts are solvent-agnostic, so any entry within tolerance matches.  For
    ¹H, when the in-use solvent is one of the tabulated Fulmer columns the match
    is restricted to *that* column (no cross-column leakage — a CDCl3 spectrum
    must not borrow a DMSO-d6 shift).  Only when the solvent has no column of its
    own (an unknown solvent, or one of the extended deuterated solvents not in
    the Fulmer ¹H table) do we fall back to the best cross-column hit.
    """
    if nucleus == "13C":
        best: tuple[str, str, float] | None = None
        for entry in _C13_IMPURITIES:
            prox = _proximity(abs(peak_ppm - entry.shift_ppm), entry.tol_ppm)
            if prox is not None and (best is None or prox > best[2]):
                best = (entry.kind, entry.label, prox)
        return best

    canonical = _canonical_solvent(solvent)
    column = canonical if canonical in _H1_COLUMNS else None
    same_column: tuple[str, str, float] | None = None
    cross_column: tuple[str, str, float] | None = None
    for entry in COMMON_IMPURITIES:
        prox = _proximity(abs(peak_ppm - entry.shift_ppm), entry.tol_ppm)
        if prox is None:
            continue
        candidate = (entry.kind, entry.label, prox)
        if column is not None and entry.solvent == column:
            if same_column is None or prox > same_column[2]:
                same_column = candidate
        if cross_column is None or prox > cross_column[2]:
            cross_column = candidate
    return same_column if column is not None else cross_column


def _looks_like_13c_satellite(peak: Peak, all_peaks: list[Peak], field_mhz: float) -> bool:
    """True if ``peak`` is one wing of a symmetric ¹³C-satellite pair.

    Requires a much stronger parent at ``±½·¹J(C,H)`` and its mirror line on the
    opposite side, with both wings carrying ~0.3–2.5 % of the parent intensity.
    """
    if field_mhz <= 0 or peak.intensity <= 0:
        return False
    for parent in all_peaks:
        if parent is peak or parent.intensity <= 0:
            continue
        ratio = float(peak.intensity) / float(parent.intensity)
        if not (_MIN_SATELLITE_RATIO <= ratio <= _MAX_SATELLITE_RATIO):
            continue
        offset_ppm = peak.position_ppm - parent.position_ppm
        if abs(offset_ppm) < 1e-6:
            continue
        for j_ch in _J_CH_HZ:
            expected = 0.5 * j_ch / field_mhz
            tol = max(0.01, expected * 0.12)
            if abs(abs(offset_ppm) - expected) > tol:
                continue
            mirror_ppm = parent.position_ppm - offset_ppm
            for other in all_peaks:
                if other is peak or other is parent:
                    continue
                if abs(other.position_ppm - mirror_ppm) > tol:
                    continue
                mirror_ratio = float(other.intensity) / float(parent.intensity)
                if _MIN_SATELLITE_RATIO <= mirror_ratio <= _MAX_SATELLITE_RATIO:
                    return True
    return False


def _below_noise(peak: Peak, all_peaks: list[Peak]) -> bool:
    """Whether the peak sits at/below the detection floor (weak ``+low`` signal)."""
    snr = peak.metadata.get("signal_to_noise") if isinstance(peak.metadata, dict) else None
    if snr is not None:
        try:
            return float(snr) < _MIN_SIGNAL_TO_NOISE
        except (TypeError, ValueError):
            pass
    max_intensity = max((float(p.intensity) for p in all_peaks), default=0.0)
    if max_intensity <= 0:
        return False
    return float(peak.intensity) < max_intensity * _BELOW_NOISE_INTENSITY_FRACTION


def _width_anomaly(peak: Peak, all_peaks: list[Peak], nucleus: str) -> bool:
    """Anomalous line width: a digital spike, or broad beyond the nucleus floor."""
    width = float(peak.width_hz)
    if not math.isfinite(width) or width <= 0:
        return True
    widths = [float(p.width_hz) for p in all_peaks if float(p.width_hz) > 0]
    med = float(median(widths)) if widths else width
    floor = _BROAD_WIDTH_FLOOR_HZ.get(nucleus, 25.0)
    if med > 0 and width > 2.0 * med and width > floor:
        return True
    if med > 0 and width < 0.2 * med and width < _SPIKE_WIDTH_FLOOR_HZ:
        return True
    return False


def _out_of_range(peak_ppm: float, nucleus: str) -> bool:
    low, high = _REASONABLE_RANGE_PPM.get(nucleus, _REASONABLE_RANGE_PPM["1H"])
    return not (low <= peak_ppm <= high)


def _artifact_score(peak: Peak, all_peaks: list[Peak], nucleus: str) -> float:
    """Additive artifact evidence: out-of-range (high) + width (med) + noise (low)."""
    score = 0.0
    if _out_of_range(peak.position_ppm, nucleus):
        score += _SCORE_HIGH
    if _width_anomaly(peak, all_peaks, nucleus):
        score += _SCORE_MED
    if _below_noise(peak, all_peaks):
        score += _SCORE_LOW
    return min(score, 0.99)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def detect_solvent(spectrum: NMRSpectrum, peaks: list[Peak]) -> str:
    """Return the most likely deuterated solvent from the peak position pattern.

    Each of the 14 reference solvents is scored by how well the observed peaks
    cover its residual signature: a residual line that coincides with a peak
    scores, weighted up when that peak is among the more prominent lines (real
    residual-solvent peaks usually are).  The solvent declared in
    ``spectrum.solvent`` (if any) contributes a modest prior so the result
    agrees with acquisition metadata on ambiguous spectra but can be overridden
    when the peaks point elsewhere.  Returns the canonical solvent name, the
    declared solvent, or ``"unknown"``.
    """
    nucleus = _normalise_nucleus(spectrum.nucleus)
    declared = _canonical_solvent(spectrum.solvent)
    if nucleus not in {"1H", "13C"}:
        return declared or "unknown"

    positions = [float(p.position_ppm) for p in peaks]
    intensities = [float(p.intensity) for p in peaks]
    max_intensity = max(intensities, default=0.0)

    best_name: str | None = None
    best_score = 0.0
    for profile in DEUTERATED_SOLVENTS:
        shifts = profile.residual_1h if nucleus == "1H" else profile.residual_13c
        if not shifts:
            continue
        tol = profile.tol_1h_ppm if nucleus == "1H" else profile.tol_13c_ppm
        covered = 0.0
        for shift in shifts:
            best_prox = 0.0
            best_prom = 0.0
            for ppm, intensity in zip(positions, intensities, strict=True):
                prox = _proximity(abs(ppm - shift), tol)
                if prox is None:
                    continue
                prominence = intensity / max_intensity if max_intensity > 0 else 0.0
                if prox > best_prox or (prox == best_prox and prominence > best_prom):
                    best_prox = prox
                    best_prom = prominence
            if best_prox > 0:
                covered += best_prox * (0.5 + 0.5 * best_prom)
        score = covered / float(len(shifts))
        if declared is not None and profile.canonical_name == declared:
            score += 0.15  # prior toward the declared acquisition solvent
        if score > best_score:
            best_score = score
            best_name = profile.canonical_name

    if best_name is not None and best_score > 0:
        return best_name
    return declared or "unknown"


def classify_peak(
    peak: Peak, spectrum_solvent: str, all_peaks: list[Peak]
) -> tuple[str, float]:
    """Classify one peak as compound/solvent/residual_solvent/impurity/satellite/artifact.

    Returns ``(category, confidence)``.  Evidence is gathered per the Prompt 10
    scoring scheme and the highest-scoring category that clears the decision
    threshold wins; otherwise the peak is ``compound`` with a confidence that
    reports how cleanly it cleared every alternative.  Category precedence on
    ties: solvent > residual_solvent > impurity > 13C_satellite > artifact.
    """
    peers = all_peaks if all_peaks else [peak]
    nucleus = _infer_nucleus(peers)
    field_mhz = _infer_field_mhz(peers)
    ppm = float(peak.position_ppm)
    max_intensity = max((float(p.intensity) for p in peers), default=0.0)
    prominence = float(peak.intensity) / max_intensity if max_intensity > 0 else 0.0

    # (priority, category, confidence) — higher priority breaks confidence ties.
    candidates: list[tuple[int, str, float]] = []

    solvent_prox = _match_bulk_solvent(ppm, spectrum_solvent, nucleus)
    if solvent_prox is not None:
        candidates.append((5, "solvent", _SCORE_HIGH * solvent_prox))

    impurity = _match_impurity(ppm, spectrum_solvent, nucleus)
    # A contaminant must be a minority signal: skip the impurity/residual-solvent
    # route for peaks too prominent to be trace contamination (only when there is
    # context to judge prominence against).
    too_dominant = len(peers) >= 2 and prominence >= _IMPURITY_MAX_PROMINENCE
    if impurity is not None and not too_dominant:
        kind, _label, prox = impurity
        priority = 4 if kind == "residual_solvent" else 3
        confidence = _SCORE_HIGH * prox * (1.0 - 0.25 * prominence)
        candidates.append((priority, kind, confidence))

    if nucleus == "1H" and _looks_like_13c_satellite(peak, peers, field_mhz):
        candidates.append((2, "13C_satellite", _SCORE_MED))

    artifact = _artifact_score(peak, peers, nucleus)
    if artifact > 0:
        candidates.append((1, "artifact", artifact))

    if candidates:
        candidates.sort(key=lambda item: (item[2], item[0]), reverse=True)
        _priority, category, confidence = candidates[0]
        if confidence >= _DECISION_THRESHOLD:
            return category, _clamp(confidence)

    best_alt = max((conf for _p, _c, conf in candidates), default=0.0)
    return "compound", _clamp(max(_COMPOUND_CONFIDENCE_FLOOR, 1.0 - best_alt))


def classify_peaks(
    peaks: list[Peak], spectrum_solvent: str
) -> list[tuple[str, float]]:
    """Batch :func:`classify_peak` over a peak list (the auto_classify entry point)."""
    return [classify_peak(peak, spectrum_solvent, peaks) for peak in peaks]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
