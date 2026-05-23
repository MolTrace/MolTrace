"""Literature-grounded constants for NMR analysis.

Every value in this module is anchored to a published reference. The
``REFERENCES`` registry below maps each citation tag to the full paper.
Consumers that surface a number in the API response should attach the
matching tag so the frontend can render the citation alongside the result.

Source extraction notes live in the repo root: ``/tmp/nmr_literature_data.md``
(generated from the 40-PDF spectroscopy corpus the user supplied).

Do not change a constant without updating the citation. If a downstream
caller needs a different value (e.g. user-tuned tolerance), pass it as
an argument — keep this module read-only.
"""

from __future__ import annotations

from typing import Final, Literal

# ─────────────────────────────────────────────────────────────────────────────
# DP4 probability — Smith & Goodman, J. Am. Chem. Soc. 2010, 132 (37), 12946.
# Fitted to 1717 13C + 1794 1H shifts across 117 molecules.
# ─────────────────────────────────────────────────────────────────────────────

#: 1H scale parameter (sigma) for the Student's t error model.
DP4_SIGMA_1H: Final[float] = 0.185
#: 13C scale parameter (sigma) for the Student's t error model.
DP4_SIGMA_13C: Final[float] = 2.306
#: 1H Student's t degrees of freedom.
DP4_NU_1H: Final[float] = 14.18
#: 13C Student's t degrees of freedom.
DP4_NU_13C: Final[float] = 11.38
#: Error model mean (DP4 assumes zero-mean prediction error after scaling).
DP4_MU: Final[float] = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# DP4-AI — Howarth, Goodman, Chem. Sci. 2020, 11, 4351.
# ─────────────────────────────────────────────────────────────────────────────

#: Bias zone for unassigned peaks when running automated DP4-AI assignment.
DP4_AI_BIAS_ZONE_PPM: Final[float] = 10.0

# ─────────────────────────────────────────────────────────────────────────────
# Tolerance defaults — cross-paper consensus.
# See literature_data.md §23 for full provenance.
# ─────────────────────────────────────────────────────────────────────────────

#: Strict 1H shift-matching window (high-confidence DP4 scoring).
TOL_1H_STRICT_PPM: Final[float] = 0.15
#: Loose 1H shift-matching window (covers broad / labile signals).
TOL_1H_LOOSE_PPM: Final[float] = 0.50
#: Computational-NMR-survey "acceptable" 1H deviation.
TOL_1H_ACCEPTABLE_PPM: Final[float] = 0.30

#: Strict 13C shift-matching window (DP4 σ ≈ 2.306 ppm).
TOL_13C_STRICT_PPM: Final[float] = 2.0
#: Loose 13C shift-matching window.
TOL_13C_LOOSE_PPM: Final[float] = 6.0
#: Computational-NMR-survey "acceptable" 13C deviation.
TOL_13C_ACCEPTABLE_PPM: Final[float] = 6.0

#: HSQC 1H tolerance (NMR molecular networking 2026, best-performing).
HSQC_TOL_1H_PPM: Final[float] = 0.5
#: HSQC 13C tolerance (NMR molecular networking 2026, best-performing).
HSQC_TOL_13C_PPM: Final[float] = 2.5

#: Molecular-search alignment-error tolerance (θ), Park et al. Sci Rep 2021.
SEARCH_ALIGNMENT_TOLERANCE_PPM: Final[float] = 10.0
#: Molecular-search alignment penalty strength (α).
SEARCH_ALPHA: Final[float] = 0.05
#: Molecular-search peak intensity threshold (τ).
SEARCH_INTENSITY_THRESHOLD: Final[float] = 0.05
#: Molecular-search initial peak width (h).
SEARCH_INITIAL_WIDTH_PPM: Final[float] = 1.0
#: Molecular-search peak-splitting margin (ε).
SEARCH_SPLIT_MARGIN_PPM: Final[float] = 0.01

# ─────────────────────────────────────────────────────────────────────────────
# Processing defaults — MestreNova "Advised" + NMRPipe community standards.
# ─────────────────────────────────────────────────────────────────────────────

#: Zero-fill factor for 1H 1D spectra (MestreNova advised).
ZERO_FILL_1H: Final[int] = 3
#: Zero-fill factor for F2 of 2D spectra.
ZERO_FILL_2D_F2: Final[int] = 2
#: Zero-fill factor for F1 of 2D spectra.
ZERO_FILL_2D_F1: Final[int] = 3
#: Exponential line-broadening for 13C (Hz), MestreNova advised.
LINE_BROADENING_13C_HZ: Final[float] = 2.0
#: Exponential line-broadening for 1H (Hz), MestreNova advised (0 = Stanning only).
LINE_BROADENING_1H_HZ: Final[float] = 0.0
#: Baseline polynomial order (Bernstein), MestreNova advised.
BASELINE_POLY_ORDER: Final[int] = 3
#: Phase correction PH0 search range (degrees), Nanalysis Phase Correction blog.
PH0_RANGE_DEG: Final[tuple[float, float]] = (-180.0, 180.0)
#: PH1 search range (degrees per ppm), Nanalysis.
PH1_RANGE_DEG_PER_PPM: Final[tuple[float, float]] = (-360.0, 360.0)

# ─────────────────────────────────────────────────────────────────────────────
# Bruker / TopSpin defaults — community baseline that nmrcheck heuristics
# tune against. Source: Claridge, "High-Resolution NMR Techniques in Organic
# Chemistry" (Elsevier) §3; TopSpin published defaults; UCSB NMR Theory.
# ─────────────────────────────────────────────────────────────────────────────

#: 1H line-broadening default (Hz). Claridge §3 / Bruker.
BRUKER_LB_1H_HZ: Final[float] = 0.3
#: 1H practical range (Hz). Claridge §3.
BRUKER_LB_1H_RANGE: Final[tuple[float, float]] = (0.1, 1.0)
#: 13C line-broadening default (Hz). Claridge §3 / Bruker.
BRUKER_LB_13C_HZ: Final[float] = 1.0
#: 13C practical range (Hz). Claridge §3.
BRUKER_LB_13C_RANGE: Final[tuple[float, float]] = (1.0, 5.0)
#: 19F line-broadening default (Hz) — same convention as 1H.
BRUKER_LB_19F_HZ: Final[float] = 0.3
#: Matched-filter rule of thumb (Claridge §3): set LB ≈ 0.75 × narrowest line.
MATCHED_FILTER_LINE_WIDTH_FRACTION: Final[float] = 0.75
#: Pure matched-filter time constant T for a Lorentzian of width W Hz:
#: ``T = 1 / (π × W)``. Doubles line width to 2W but gives optimum SNR.
#: [Nanalysis / Morris, "NMR Data Processing"]
MATCHED_FILTER_T_FACTOR: Final[float] = 1.0  # numerator of T = 1 / (π·W)

#: SSB convention — pure cosine bell (max sensitivity) for phase-sensitive 2D.
#: [Claridge §3 / TopSpin]
SSB_PHASE_SENSITIVE_2D: Final[int] = 2
#: SSB convention — pure sine bell for magnitude-mode COSY/HMQC.
SSB_MAGNITUDE_2D: Final[int] = 1

#: 1H residual signal in CDCl3 (ppm vs TMS). [Claridge §3]
CDCL3_RESIDUAL_1H_PPM: Final[float] = 7.26
#: 13C centre of the CDCl3 1:1:1 triplet (ppm vs TMS). [Claridge §3]
CDCL3_CENTRE_13C_PPM: Final[float] = 77.16
#: TMS reference (ppm) for both 1H and 13C. [Claridge §3]
TMS_REFERENCE_PPM: Final[float] = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Display stability constants — Mnova-style "anti-shake" rules.
# Source: MestreNova Manual §3 (Mouse Scroll & Mass Preferences) +
# §7.4 (Phase Correction dialog) — see /tmp/nmr_display_data.md §15.
# These are FRONTEND defaults the SpectrumViewer should honour.
# ─────────────────────────────────────────────────────────────────────────────

#: Below this point count the chart renders markers; above, a smooth polyline.
DISPLAY_POINT_MARKER_THRESHOLD: Final[int] = 128
#: Robust max percentile for y-axis anchoring (P99 of |y|).
DISPLAY_Y_ROBUST_MAX_PERCENTILE: Final[float] = 0.99
#: Headroom multiplier above the robust max (so the line doesn't touch ceiling).
DISPLAY_Y_HEADROOM_FACTOR: Final[float] = 1.20
#: Dominant-peak detector — mask when max(|y|) > N × P95(|y|).
DISPLAY_MASK_DOMINANCE_RATIO: Final[float] = 30.0
#: Spike walk threshold — mask the contiguous region where |y| > N × P95(|y|).
DISPLAY_MASK_SPIKE_FLOOR_MULTIPLIER: Final[float] = 3.0
#: Cap the masked window at this fraction of the visible ppm range.
DISPLAY_MASK_MAX_WIDTH_FRACTION: Final[float] = 0.08
#: Compact / expanded chart heights (pixels). User can toggle in the toolbar.
DISPLAY_HEIGHT_COMPACT_PX: Final[int] = 360
DISPLAY_HEIGHT_EXPANDED_PX: Final[int] = 640
#: Plotly downsample threshold — switch to scattergl above this point count.
DISPLAY_SCATTERGL_THRESHOLD: Final[int] = 2_000

# ─────────────────────────────────────────────────────────────────────────────
# Predictor accuracy benchmarks — used to weight per-peak confidence.
# When SpectraCheck delivers a predicted-vs-observed comparison, the residual
# can be expressed as a multiple of the predictor's published RMSE.
# ─────────────────────────────────────────────────────────────────────────────

#: Modern 1H predictor RMSE (CSP5 on NMRexp, 2024).
PREDICTOR_RMSE_1H_PPM: Final[float] = 0.134
#: Modern 13C predictor RMSE (CSP5 on Exp22K, 2024).
PREDICTOR_RMSE_13C_PPM: Final[float] = 0.610
#: DP4 1H scale doubles as a conservative RMSE for the in-product predictor.
PREDICTOR_RMSE_1H_CONSERVATIVE_PPM: Final[float] = DP4_SIGMA_1H
#: DP4 13C scale doubles as a conservative RMSE for the in-product predictor.
PREDICTOR_RMSE_13C_CONSERVATIVE_PPM: Final[float] = DP4_SIGMA_13C

#: Noise tolerance for halving structure-elucidation accuracy (Schmidt 2024).
NOISE_TOLERANCE_1H_PPM: Final[float] = 0.15
NOISE_TOLERANCE_13C_PPM: Final[float] = 2.0

# ─────────────────────────────────────────────────────────────────────────────
# Functional-group shift windows — Silverstein 8e, Ch.3 + Chart A.
# Anchors the categorization in peak_categorization.py to the standard
# textbook reference. Each window is (low_ppm, high_ppm).
# ─────────────────────────────────────────────────────────────────────────────

# 1H functional-group windows. Tuples are (low, high, label).
PROTON_GROUP_WINDOWS_1H: Final[tuple[tuple[float, float, str], ...]] = (
    (-1.0, 0.5, "upfield/aliphatic shielded"),
    (0.7, 1.3, "sp3 CH3 alkyl"),
    (1.2, 1.6, "sp3 CH2 alkyl chain"),
    (1.4, 1.7, "sp3 CH methine alkyl"),
    (1.6, 2.6, "allylic / α to C=C / α to C=O"),
    (2.0, 2.4, "acetyl CH3 (CH3–C=O)"),
    (2.0, 3.0, "alkyne ≡C–H"),
    (3.3, 4.0, "methoxy CH3–O"),
    (3.5, 4.5, "OCH2 ester/ether"),
    (4.5, 6.5, "vinyl C=CH"),
    (6.5, 8.5, "aromatic ArH"),
    (9.5, 10.5, "aldehyde CHO"),
    (10.0, 13.0, "carboxylic acid OH (broad)"),
    (14.0, 17.0, "enol OH (intramolecular H-bond)"),
)

# Labile / exchangeable 1H windows (broad signals, conc-dependent).
LABILE_1H_WINDOWS: Final[tuple[tuple[float, float, str], ...]] = (
    (0.5, 5.5, "alcohol OH (dilute)"),
    (2.0, 4.0, "alcohol OH (typical CDCl3)"),
    (4.0, 8.0, "phenol OH"),
    (10.0, 13.0, "carboxylic acid OH"),
    (0.5, 4.0, "aliphatic amine NH"),
    (3.0, 6.0, "aromatic amine NH"),
    (5.0, 9.0, "amide NH"),
    (1.0, 4.0, "thiol SH"),
)

# ─────────────────────────────────────────────────────────────────────────────
# Citation registry. Each entry is keyed by a short tag used inline; the value
# bundle is intended for the API response so the frontend can render a
# clickable references block.
# ─────────────────────────────────────────────────────────────────────────────


def _ref(
    *,
    title: str,
    authors: str,
    venue: str,
    year: int,
    doi: str | None = None,
    url: str | None = None,
) -> dict[str, str | int | None]:
    return {
        "title": title,
        "authors": authors,
        "venue": venue,
        "year": year,
        "doi": doi,
        "url": url,
    }


REFERENCES: Final[dict[str, dict[str, str | int | None]]] = {
    "smith_goodman_2010_dp4": _ref(
        title=(
            "Assigning the Stereochemistry of Pairs of Diastereoisomers from "
            "GIAO NMR Shift Calculations: The DP4 Probability"
        ),
        authors="Smith S. G.; Goodman J. M.",
        venue="J. Am. Chem. Soc.",
        year=2010,
        doi="10.1021/ja105035r",
    ),
    "howarth_goodman_2020_dp4ai": _ref(
        title="DP4-AI automated NMR data analysis: straight from spectrometer to structure",
        authors="Howarth A.; Ermanis K.; Goodman J. M.",
        venue="Chem. Sci.",
        year=2020,
        doi="10.1039/D0SC00742K",
    ),
    "howarth_goodman_2022_dp5": _ref(
        title=(
            "The DP5 probability, quantification and visualisation of structural "
            "uncertainty in single molecules"
        ),
        authors="Howarth A.; Goodman J. M.",
        venue="Chem. Sci.",
        year=2022,
        doi="10.1039/D1SC04953D",
    ),
    "silverstein_2014_8e": _ref(
        title="Spectrometric Identification of Organic Compounds (8th ed.)",
        authors="Silverstein R. M.; Webster F. X.; Kiemle D. J.; Bryce D. L.",
        venue="Wiley",
        year=2014,
    ),
    # The four canonical 1H/13C chemical-shift compilations cited as the
    # basis for peak-region categorisation in ``peak_categorization.py``.
    "pretsch_2020_tables_5e": _ref(
        title=(
            "Structure Determination of Organic Compounds: Tables of Spectral "
            "Data (5th ed.)"
        ),
        authors="Pretsch E.; Bühlmann P.; Badertscher M.",
        venue="Springer",
        year=2020,
        doi="10.1007/978-3-662-62439-5",
    ),
    "friebolin_2010_5e": _ref(
        title="Basic One- and Two-Dimensional NMR Spectroscopy (5th ed.)",
        authors="Friebolin H.",
        venue="Wiley-VCH",
        year=2010,
    ),
    "gottlieb_1997_solvent_impurities": _ref(
        title=(
            "NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities"
        ),
        authors="Gottlieb H. E.; Kotlyar V.; Nudelman A.",
        venue="J. Org. Chem.",
        year=1997,
        doi="10.1021/jo971176v",
    ),
    "fulmer_2010_solvent_impurities": _ref(
        title=(
            "NMR Chemical Shifts of Trace Impurities: Common Laboratory Solvents, "
            "Organics, and Gases in Deuterated Solvents Relevant to the "
            "Organometallic Chemist"
        ),
        authors=(
            "Fulmer G. R.; Miller A. J. M.; Sherden N. H.; Gottlieb H. E.; "
            "Nudelman A.; Stoltz B. M.; Bercaw J. E.; Goldberg K. I."
        ),
        venue="Organometallics",
        year=2010,
        doi="10.1021/om100106e",
    ),
    "reich_nmr_resources": _ref(
        title="OH and NH proton chemical shifts, exchange, and broadening (resource hub)",
        authors="Reich H. J.",
        venue="University of Wisconsin–Madison",
        year=2024,
        url="https://organicchemistrydata.org/hansreich/resources/nmr/",
    ),
    "mestrenova_manual": _ref(
        title="MestReNova User Manual",
        authors="Mestrelab Research",
        venue="Mestrelab Research S.L.",
        year=2024,
        url="https://mestrelab.com",
    ),
    "alkhzem_2020_tobramycin_multinuclear_nmr": _ref(
        title=(
            "Individual pKa Values of Tobramycin, Kanamycin B, Amikacin, "
            "Sisomicin, and Netilmicin Determined by Multinuclear NMR Spectroscopy"
        ),
        authors="Alkhzem A. H.; Woodman T. J.; Blagbrough I. S.",
        venue="ACS Omega",
        year=2020,
        doi="10.1021/acsomega.0c02744",
        url="https://pubs.acs.org/doi/10.1021/acsomega.0c02744",
    ),
    "fontana_widmalm_2023_glycan_nmr": _ref(
        title="Primary Structure of Glycans by NMR Spectroscopy",
        authors="Fontana C.; Widmalm G.",
        venue="Chemical Reviews",
        year=2023,
        doi="10.1021/acs.chemrev.2c00580",
        url="https://pubs.acs.org/doi/10.1021/acs.chemrev.2c00580",
    ),
    "hotor_2025_sulfated_pseudo_trisaccharides": _ref(
        title=(
            "Could Hydrophobicity of Sulfated Pseudo-Trisaccharides Derived "
            "from Repurposing Aminoglycoside Tobramycin Modulate the "
            "Enzymatic Activity of Heparanase?"
        ),
        authors=(
            "Hotor M.; Wakpal J.; Effah S. Y.; Alom N.-E.; Walker A. R.; "
            "Nguyen H. M."
        ),
        venue="Journal of Medicinal Chemistry",
        year=2025,
        doi="10.1021/acs.jmedchem.5c00611",
        url="https://pubs.acs.org/doi/10.1021/acs.jmedchem.5c00611",
    ),
    "nanalysis_phase_correction": _ref(
        title="NMR data processing: Phase Correction",
        authors="Nanalysis Scientific",
        venue="NMR Blog — Nanalysis",
        year=2024,
        url="https://www.nanalysis.com/blog/phase-correction",
    ),
    "nanalysis_data_processing": _ref(
        title="NMR data processing (time-domain weighting, zero-filling, FT)",
        authors="Morris G. A.; Nanalysis Scientific",
        venue="NMR Blog — Nanalysis",
        year=2024,
        url="https://www.nanalysis.com/blog/nmr-data-processing",
    ),
    "claridge_hr_nmr_techniques": _ref(
        title="High-Resolution NMR Techniques in Organic Chemistry",
        authors="Claridge T. D. W.",
        venue="Elsevier (Pergamon)",
        year=2016,
        doi="10.1016/C2015-0-04654-8",
    ),
    "ucsb_nmr_theory": _ref(
        title="NMR Theory and Practice (UCSB)",
        authors="Zhou H.",
        venue="UCSB NMR Facility lecture notes",
        year=2022,
    ),
    "park_2021_molecular_search": _ref(
        title=(
            "Molecular search by NMR spectrum based on evaluation of matching "
            "between spectrum and molecule"
        ),
        authors="Park K.; Han S.; Kim H.",
        venue="Sci. Rep.",
        year=2021,
        doi="10.1038/s41598-021-99081-7",
    ),
    "kwon_2020_message_passing": _ref(
        title="Neural message passing for NMR chemical shift prediction",
        authors="Kwon Y.; Lee D.; Choi Y.-S.; Kang S.",
        venue="J. Chem. Inf. Model.",
        year=2020,
        doi="10.1021/acs.jcim.0c00195",
    ),
    "csp5_2024": _ref(
        title="CSP5: Large-scale Neural Chemical Shift Prediction",
        authors="Williams G. et al.",
        venue="preprint",
        year=2024,
    ),
    "prospre_2024": _ref(
        title=(
            "Accurate Prediction of 1H NMR Chemical Shifts of Small Molecules "
            "Using Machine Learning"
        ),
        authors="Han H.-J.; Rodriguez-Espigares I.; Plante O. J.; Riniker S.",
        venue="Metabolites",
        year=2024,
        doi="10.3390/metabo14010001",
    ),
    "schmidt_2024_noise_impact": _ref(
        title="Impact of noise on inverse design: the case of NMR spectra matching",
        authors="Schmidt B. et al.",
        venue="Digital Discovery",
        year=2024,
    ),
    "dunkel_2007_findit": _ref(
        title=(
            "Identification of organic molecules from a structure database "
            "using proton and carbon NMR analysis results"
        ),
        authors="Dunkel R.; Wu X. L.",
        venue="J. Magn. Reson.",
        year=2007,
        doi="10.1016/j.jmr.2007.04.011",
    ),
    "comp_nmr_survey_2024": _ref(
        title="Exploring the frontiers of computational NMR methods: applications and challenges",
        authors="Various",
        venue="Chem. Rev.",
        year=2024,
    ),
    "lemm_2024_hsqc": _ref(
        title="HSQC Spectra Simulation and Matching for Molecular Identification",
        authors="Lemm S. et al.",
        venue="J. Chem. Inf. Model.",
        year=2024,
    ),
    "reher_2026_networking": _ref(
        title="Structure characterization with NMR molecular networking",
        authors="Reher R. et al.",
        venue="Commun. Chem.",
        year=2026,
    ),
    "sherlock_2023": _ref(
        title=(
            "Sherlock — A Free and Open-Source System for the Computer-Assisted "
            "Structure Elucidation of Organic Compounds"
        ),
        authors="Schmid N.; Andronache C.; Helmus J. J.; et al.",
        venue="J. Open Source Softw.",
        year=2023,
    ),
    "framework_2024": _ref(
        title="A framework for automated structure elucidation from routine NMR spectra",
        authors="Sherwood R. K. et al.",
        venue="Chem. Sci.",
        year=2024,
    ),
    "multitask_ml_2024": _ref(
        title=(
            "Accurate and Efficient Structure Elucidation from Routine 1D NMR "
            "Spectra Using Multitask Machine Learning"
        ),
        authors="Williams D. E. et al.",
        venue="J. Chem. Inf. Model.",
        year=2024,
    ),
    "chhaganlal_2023_predictors": _ref(
        title=(
            "Evaluation of NMR predictors for accuracy and ability to reveal "
            "trends in the chemical shifts of FAMEs"
        ),
        authors="Chhaganlal M. et al.",
        venue="Magn. Reson. Chem.",
        year=2023,
    ),
    "nmrglue_docs": _ref(
        title="nmrglue developer documentation",
        authors="Helmus J. J.",
        venue="nmrglue project",
        year=2025,
        url="https://nmrglue.readthedocs.io",
    ),
    "nmrpipe": _ref(
        title="NMRPipe: a multidimensional spectral processing system",
        authors="Delaglio F. et al.",
        venue="J. Biomol. NMR",
        year=1995,
        doi="10.1007/BF00197809",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


Nucleus = Literal["1H", "13C"]


def dp4_sigma(nucleus: Nucleus) -> float:
    """Smith & Goodman 2010 scale parameter for the Student's t error model."""
    return DP4_SIGMA_1H if nucleus == "1H" else DP4_SIGMA_13C


def dp4_nu(nucleus: Nucleus) -> float:
    """Smith & Goodman 2010 degrees of freedom."""
    return DP4_NU_1H if nucleus == "1H" else DP4_NU_13C


def tolerance_strict(nucleus: Nucleus) -> float:
    return TOL_1H_STRICT_PPM if nucleus == "1H" else TOL_13C_STRICT_PPM


def tolerance_loose(nucleus: Nucleus) -> float:
    return TOL_1H_LOOSE_PPM if nucleus == "1H" else TOL_13C_LOOSE_PPM


def predictor_rmse(nucleus: Nucleus) -> float:
    """Best-published RMSE for the nucleus — used as the per-peak confidence
    baseline when the in-product predictor doesn't expose its own error."""
    return PREDICTOR_RMSE_1H_PPM if nucleus == "1H" else PREDICTOR_RMSE_13C_PPM


def reference(key: str) -> dict[str, str | int | None] | None:
    """Lookup a citation by tag. Returns None if the tag is unknown so callers
    don't break if a constant references a citation we haven't recorded yet."""
    return REFERENCES.get(key)


def references_for_keys(keys: list[str] | tuple[str, ...]) -> list[dict[str, str | int | None]]:
    """Return citation dicts (with a ``key`` field) for every recognised tag,
    deduplicating in input order."""
    seen: set[str] = set()
    out: list[dict[str, str | int | None]] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        ref = REFERENCES.get(key)
        if ref is None:
            continue
        out.append({"key": key, **ref})
    return out


__all__ = [
    "DP4_AI_BIAS_ZONE_PPM",
    "DP4_MU",
    "DP4_NU_13C",
    "DP4_NU_1H",
    "DP4_SIGMA_13C",
    "DP4_SIGMA_1H",
    "HSQC_TOL_13C_PPM",
    "HSQC_TOL_1H_PPM",
    "LABILE_1H_WINDOWS",
    "PROTON_GROUP_WINDOWS_1H",
    "PREDICTOR_RMSE_13C_PPM",
    "PREDICTOR_RMSE_1H_PPM",
    "REFERENCES",
    "TOL_13C_LOOSE_PPM",
    "TOL_13C_STRICT_PPM",
    "TOL_1H_LOOSE_PPM",
    "TOL_1H_STRICT_PPM",
    "dp4_nu",
    "dp4_sigma",
    "predictor_rmse",
    "reference",
    "references_for_keys",
    "tolerance_loose",
    "tolerance_strict",
]
