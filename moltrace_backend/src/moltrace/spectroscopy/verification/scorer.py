"""Multi-test structure-verification scorer (Prompt 7).

MolTrace's automated structure-verification (ASV) layer.  Given an
experimental 1-D NMR spectrum and a *proposed* structure (SMILES), it runs
a battery of independent tests — each asking a different question of the
data — and combines them into a single posterior confidence that the
proposed structure is consistent with the evidence.

Literature grounding
====================
The multi-test ASV / computer-assisted structure-elucidation (CASE)
methodology is well established in the *public* literature:

* S. S. Golotvin, E. Vodopianov, B. A. Lefebvre, A. J. Williams, et al.,
  on automated structure verification of small molecules by 1-D/2-D NMR —
  the idea of verifying a proposed structure with several independent
  consistency tests, each contributing a fit score and a reliability.
* M. E. Elyashberg, A. J. Williams, K. A. Blinov, *Contemporary
  Computer-Assisted Approaches to Molecular Structure Elucidation*, RSC
  (2012); and M. E. Elyashberg et al., *Prog. Nucl. Magn. Reson.
  Spectrosc.* — CASE ranking of candidate structures by consistency with
  the experimental data (good-list / bad-list, match factors).
* Natural isotopic abundances used by the MS test: J. Meija et al.,
  "Isotopic compositions of the elements 2013", *Pure Appl. Chem.* 88, 293
  (2016) (IUPAC).

IP note
-------
This module is designed from first principles plus the cited *public*
ASV/CASE literature.  It deliberately contains **no** vendor scoring
scheme — no formulas, thresholds, weights, or text are taken from any
proprietary structure-verification product or its manuals.  The
score / significance / quality decomposition and the Bayesian log-odds
combination below are MolTrace's own transparent formulation, exposed in
full (``VerificationResult.combination``) so every number is auditable
(feeds the Prompt 12 audit trail).  No constant is hidden behind the math.

Scoring model
=============
Each test returns a :class:`TestResult` carrying

* ``score``        ∈ [-1, +1] — signed fit quality (+1 corroborates, -1 refutes),
* ``significance``  ≥ 0        — how much the verdict should count
  (0-2 low, 3-5 medium, 5+ high), driven by a test-specific reliability
  proxy (shift-prediction uncertainty, impurity level, number of
  correlations, m/z accuracy, …),
* ``quality = score · tanh(significance / 3)`` — the score attenuated by a
  smooth bounded function of significance, so a confident test moves the
  needle and an unreliable one barely does.

Tests are combined by a Bayesian update in log-odds space.  From the
caller's ``prior_confidence`` p0 the posterior log-odds is

    logit(p_post) = logit(p0) + Σ_i  quality_i · LN10

i.e. each test contributes a log-likelihood-ratio bounded by one order of
magnitude (``LN10``) and scaled by its ``quality``.  ``LN10`` is the single
documented evidence unit: a maximally confident corroborating test
(quality = +1) multiplies the odds by ~10; a maximally confident
contradicting one (quality = -1) divides them by ~10.  The posterior is the
logistic of that sum.  Tests that lack their required data (no 2-D
spectrum, no MS) *abstain* (quality = 0) and leave the posterior unchanged
— the framework never fabricates evidence it does not have.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.multiplet.analysis import Multiplet, detect_multiplets
from moltrace.spectroscopy.peaks.gsd import Peak, gsd_peak_pick
from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    ShiftPrediction,
    predict_shifts,
)

# --------------------------------------------------------------------------- #
# Documented scoring constants (every tunable lives here; nothing is hidden).
# --------------------------------------------------------------------------- #
LN10 = math.log(10.0)
"""Evidence unit: one order of magnitude of odds per unit of test quality."""

VERDICT_CONSISTENT_AT = 0.80
"""Posterior confidence at/above which the verdict is ``"consistent"``."""
VERDICT_INCONSISTENT_AT = 0.20
"""Posterior confidence at/below which the verdict is ``"inconsistent"``."""

_SIG_MAX = 8.0  # significance cap (well inside the "high" band)
_SIG_DEFAULT = 3.0  # significance when a reliability proxy is unavailable
_SIGMA_REF_PPM = {"1H": 0.10, "13C": 2.0}  # per-nucleus reference prediction sigma
_IMPURITY_REF_PCT = 25.0  # impurity at which AssignmentsTest significance -> 0

_SHIFT_TOL_PPM = {"1H": 0.30, "13C": 4.0}  # base match tolerance (no per-shift sigma)
_EQUIV_EPS_PPM = {"1H": 0.03, "13C": 0.50}  # chemical-equivalence grouping epsilon
_TOL_SIGMA_K = 3.0  # match tolerance = max(base, K * sigma)

_HSQC_TOL_H = 0.15  # HSQC rectangle half-width, 1H axis (ppm)
_HSQC_TOL_C = 2.0  # HSQC rectangle half-width, 13C axis (ppm)
_HSQC_SAT = 6.0  # saturation constant of the HSQC significance curve

# Mass spectrometry (single charge, z = 1 assumed).
_PROTON_MASS = 1.0072765
_NA_MASS = 22.9897693
_C13_GAP = 1.0033548  # 13C - 12C mass difference
_AB_13C = 0.0107  # IUPAC 2016 natural abundances
_AB_15N = 0.00364
_AB_34S = 0.0425
_AB_37CL = 0.2424
_AB_81BR = 0.4931
_MS_REF_TOL_DA = 0.5  # reference m/z window for the MS significance curve


# --------------------------------------------------------------------------- #
# Small numeric / labelling helpers
# --------------------------------------------------------------------------- #
def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _normalise_nucleus(nucleus: str | None) -> str:
    text = (nucleus or "").strip()
    if text in ("1H", "13C"):
        return text
    low = text.lower()
    if low in ("h", "1h", "proton"):
        return "1H"
    if low in ("c", "13c", "carbon"):
        return "13C"
    return "1H"  # sensible default for an unlabelled spectrum


def _sig_band(significance: float) -> str:
    if significance < 3.0:
        return "low"
    if significance <= 5.0:
        return "medium"
    return "high"


def _significance_from_sigma(sigma: float, nucleus: str) -> float:
    """Map a shift-prediction uncertainty (ppm) to a significance in [0, _SIG_MAX].

    Monotone-decreasing in ``sigma``: sigma = sigma_ref -> 4 (medium),
    sigma -> 0 -> _SIG_MAX (high), sigma = 3*sigma_ref -> 2 (low).  When the
    NMRNet backend is unavailable the wrapper falls back to a HOSE-code
    knowledge base whose per-atom ``uncertainty_ppm`` is the spread of the
    matched reference shifts — a monotone proxy for the HOSE match sphere
    (a deeper, more specific sphere gives a tighter spread), so the same
    mapping applies to both backends.
    """

    ref = _SIGMA_REF_PPM.get(nucleus, _SIGMA_REF_PPM["1H"])
    if sigma is None or not math.isfinite(sigma) or sigma <= 0.0:
        return _SIG_DEFAULT
    return _SIG_MAX * ref / (ref + float(sigma))


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class TestResult:
    """The outcome of one verification test (fields per the Prompt 7 spec)."""

    __test__ = False  # a result type, not a pytest test class (name starts with "Test")

    score: float  # -1.0 .. +1.0, fit quality
    significance: float  # 0-2 low, 3-5 medium, 5+ high
    quality: float  # score * tanh(significance / 3)
    prior_confidence: float
    diagnostic: str  # human-readable explanation
    name: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    applicable: bool = True  # False => the test abstained (no data); quality forced 0

    @classmethod
    def create(
        cls,
        *,
        name: str,
        score: float,
        significance: float,
        prior_confidence: float,
        diagnostic: str,
        details: dict[str, Any] | None = None,
    ) -> TestResult:
        score = float(_clip(score, -1.0, 1.0))
        significance = float(max(0.0, significance))
        quality = score * math.tanh(significance / 3.0)
        return cls(
            score=score,
            significance=significance,
            quality=quality,
            prior_confidence=float(prior_confidence),
            diagnostic=diagnostic,
            name=name,
            details=dict(details or {}),
            applicable=True,
        )

    @classmethod
    def abstain(
        cls,
        *,
        name: str,
        prior_confidence: float,
        diagnostic: str,
        details: dict[str, Any] | None = None,
    ) -> TestResult:
        return cls(
            score=0.0,
            significance=0.0,
            quality=0.0,
            prior_confidence=float(prior_confidence),
            diagnostic=diagnostic,
            name=name,
            details=dict(details or {}),
            applicable=False,
        )

    @property
    def significance_band(self) -> str:
        return _sig_band(self.significance)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "significance": self.significance,
            "significance_band": self.significance_band,
            "quality": self.quality,
            "prior_confidence": self.prior_confidence,
            "applicable": self.applicable,
            "diagnostic": self.diagnostic,
            "details": self.details,
        }


@dataclass
class VerificationOptions:
    """Optional inputs / knobs for :func:`verify_structure`.

    The 2-D and MS tests need experimental data that a 1-D ``NMRSpectrum``
    does not carry; supply it here.  Absent that data those tests abstain.
    """

    hsqc_peaks: Sequence[tuple[float, float]] | None = None  # (delta_H, delta_C) ppm
    ms_peaks: Sequence[tuple[float, float]] | None = None  # (m/z, intensity)
    ms_adduct: str = "[M+H]+"  # [M+H]+ | [M-H]- | [M+Na]+ | [M]+
    ms_mz_tolerance_da: float = 0.5  # user m/z accuracy spec
    gsd_level: int = 2  # GSD peak-pick level for the experimental spectrum
    predict_n_conformers: int = 8  # conformer ensemble for predict_shifts
    nucleus: str | None = None  # override spectrum.nucleus ("1H" / "13C")


@dataclass
class VerificationResult:
    """Combined verification outcome, fully auditable."""

    proposed_smiles: str
    prior_confidence: float
    posterior_confidence: float
    verdict: str  # "consistent" | "inconsistent" | "inconclusive"
    test_results: list[TestResult]
    diagnostic: str
    combination: dict[str, Any]  # the entire posterior computation, exposed
    warnings: list[str] = field(default_factory=list)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "proposed_smiles": self.proposed_smiles,
            "prior_confidence": self.prior_confidence,
            "posterior_confidence": self.posterior_confidence,
            "verdict": self.verdict,
            "diagnostic": self.diagnostic,
            "warnings": list(self.warnings),
            "tests": [t.as_dict() for t in self.test_results],
            "combination": self.combination,
        }


# --------------------------------------------------------------------------- #
# Shared feature extraction
# --------------------------------------------------------------------------- #
def _shift_index(prediction: ShiftPrediction) -> dict[int, Any]:
    return {s.atom_index: s for s in prediction.shifts}


def _group_resonances(prediction: ShiftPrediction, nucleus: str) -> list[dict[str, Any]]:
    """Collapse predicted per-atom shifts of ``nucleus`` into chemically
    equivalent resonances (atoms with near-equal predicted shift).

    Each resonance is ``{delta_ppm, count, sigma_ppm}`` where ``count`` is the
    number of equivalent nuclei (the expected integral, in protons, for 1H).
    """

    eps = _EQUIV_EPS_PPM.get(nucleus, 0.03)
    items = sorted(
        (s for s in prediction.shifts if s.nucleus == nucleus),
        key=lambda s: s.predicted_ppm,
    )
    groups: list[dict[str, Any]] = []
    for s in items:
        sig = s.uncertainty_ppm
        if groups and abs(s.predicted_ppm - groups[-1]["_last"]) <= eps:
            g = groups[-1]
            g["count"] += 1
            g["_sum"] += s.predicted_ppm
            g["_last"] = s.predicted_ppm
            if math.isfinite(sig):
                g["_sigs"].append(float(sig))
        else:
            groups.append(
                {
                    "count": 1,
                    "_sum": s.predicted_ppm,
                    "_last": s.predicted_ppm,
                    "_sigs": [float(sig)] if math.isfinite(sig) else [],
                }
            )
    out: list[dict[str, Any]] = []
    for g in groups:
        sigs = g["_sigs"]
        out.append(
            {
                "delta_ppm": g["_sum"] / g["count"],
                "count": g["count"],
                "sigma_ppm": (sum(sigs) / len(sigs)) if sigs else float("nan"),
            }
        )
    return out


def _multiplet_area(m: Multiplet) -> float:
    return sum(max(0.0, float(p.area)) for p in m.peaks)


def _exp_units(
    nucleus: str, multiplets: list[Multiplet], peaks: list[Peak]
) -> list[dict[str, Any]]:
    """Normalise experimental resonances to a common shape for the tests.

    For 1H we use detected multiplets (so integration and multiplicity are
    available); for 13C (non-quantitative, singlets) we use the GSD peaks
    directly.
    """

    if nucleus == "1H" and multiplets:
        return [
            {
                "center_ppm": float(m.center_ppm),
                "area": _multiplet_area(m),
                "label": str(m.multiplicity_label),
            }
            for m in multiplets
        ]
    return [
        {
            "center_ppm": float(p.position_ppm),
            "area": max(0.0, float(p.area)),
            "label": "s",
        }
        for p in peaks
    ]


def _units_area(units: list[dict[str, Any]]) -> float:
    return sum(u["area"] for u in units)


# --------------------------------------------------------------------------- #
# Test 1 — PredictionBoundsTest
# --------------------------------------------------------------------------- #
class PredictionBoundsTest:
    """For each predicted shift, is there an experimental resonance with the
    correct nuclide count within tolerance?

    Significance scales with the shift-prediction confidence: NMRNet's
    per-atom ``uncertainty_ppm`` (narrower -> higher significance), falling
    back to the HOSE-code KB spread (a proxy for match sphere) when NMRNet is
    unavailable.  For 1H the "nuclide count" is checked against the multiplet
    integration (normalised to the molecule's proton count); 13C integration
    is not quantitative, so only peak presence is required there.
    """

    name = "prediction_bounds"

    def run(
        self,
        *,
        prediction: ShiftPrediction,
        units: list[dict[str, Any]],
        nucleus: str,
        total_h: int,
        prior_confidence: float,
    ) -> TestResult:
        resonances = _group_resonances(prediction, nucleus)
        if not resonances:
            return TestResult.abstain(
                name=self.name,
                prior_confidence=prior_confidence,
                diagnostic=f"No predicted {nucleus} shifts available to bound.",
            )
        total_area = _units_area(units)
        used = [False] * len(units)
        good = 0
        partial = 0
        matched_sigs: list[float] = []
        rows: list[dict[str, Any]] = []
        for r in resonances:
            sigma = r["sigma_ppm"]
            base = _SHIFT_TOL_PPM.get(nucleus, 0.30)
            tol = max(base, _TOL_SIGMA_K * sigma) if math.isfinite(sigma) else base
            best = None
            best_d = tol
            for j, u in enumerate(units):
                if used[j]:
                    continue
                d = abs(u["center_ppm"] - r["delta_ppm"])
                if d <= best_d:
                    best = j
                    best_d = d
            if best is None:
                rows.append({"delta_pred": round(r["delta_ppm"], 3), "matched": False})
                continue
            used[best] = True
            matched_sigs.append(_significance_from_sigma(sigma, nucleus))
            count_ok = True
            obs_protons = None
            if nucleus == "1H" and total_area > 0 and total_h > 0:
                obs_protons = total_h * units[best]["area"] / total_area
                count_tol = 0.5 + 0.15 * r["count"]
                count_ok = abs(obs_protons - r["count"]) <= count_tol
            if count_ok:
                good += 1
            else:
                partial += 1
            rows.append(
                {
                    "delta_pred": round(r["delta_ppm"], 3),
                    "count_pred": r["count"],
                    "delta_obs": round(units[best]["center_ppm"], 3),
                    "protons_obs": round(obs_protons, 2) if obs_protons is not None else None,
                    "matched": True,
                    "count_ok": count_ok,
                }
            )
        total = len(resonances)
        frac = (good + 0.5 * partial) / total
        score = 2.0 * frac - 1.0
        significance = sum(matched_sigs) / len(matched_sigs) if matched_sigs else 0.5
        proxy = (
            " (HOSE-KB spread as match-sphere proxy)"
            if prediction.method == "hose_fallback"
            else ""
        )
        diagnostic = (
            f"{good}/{total} predicted {nucleus} resonances matched an experimental "
            f"peak within tolerance with consistent nuclide count"
            f"{f' ({partial} matched with off integration)' if partial else ''}; "
            f"prediction method={prediction.method}{proxy}, mean significance "
            f"{significance:.1f} ({_sig_band(significance)})."
        )
        return TestResult.create(
            name=self.name,
            score=score,
            significance=significance,
            prior_confidence=prior_confidence,
            diagnostic=diagnostic,
            details={
                "matched_good": good,
                "matched_partial": partial,
                "total_resonances": total,
                "method": prediction.method,
                "resonances": rows,
            },
        )


# --------------------------------------------------------------------------- #
# Test 2 — AssignmentsTest
# --------------------------------------------------------------------------- #
def _multiplicity_consistency(coupling_set: Any, units: list[dict[str, Any]]) -> float:
    """Coarse global check: does the proposed structure's predicted coupling
    richness match how split the observed resonances are?

    ``pred_richness`` in [0, 1] is the predicted maximum J normalised to a
    typical vicinal coupling (~12 Hz); ``obs_split_frac`` is the fraction of
    observed resonances that are not singlets.  Returns ``1 - |difference|``.
    This is a deliberately conservative, index-free heuristic (the per-atom
    multiplet -> proton mapping is not asserted).
    """

    if not units:
        return 0.5
    obs_split = sum(1 for u in units if u["label"] != "s") / len(units)
    if coupling_set is None or getattr(coupling_set, "invalid_structure", False):
        return 1.0 - obs_split  # no couplings predicted -> expect singlets
    pred_richness = _clip(float(getattr(coupling_set, "max_predicted_hz", 0.0)) / 12.0, 0.0, 1.0)
    return 1.0 - abs(pred_richness - obs_split)


class AssignmentsTest:
    """Build the proposed structure's resonance set, assign experimental
    resonances to it, and score the assignment with a merit function.

    Significance scales inversely with the impurity level: the experimental
    integral that no predicted resonance explains is treated as impurity, and
    a high impurity fraction lowers how much the assignment should count.
    """

    name = "assignments"

    def run(
        self,
        *,
        prediction: ShiftPrediction,
        units: list[dict[str, Any]],
        coupling_set: Any,
        nucleus: str,
        total_h: int,
        prior_confidence: float,
    ) -> TestResult:
        resonances = _group_resonances(prediction, nucleus)
        if not resonances or not units:
            return TestResult.abstain(
                name=self.name,
                prior_confidence=prior_confidence,
                diagnostic="No predicted resonances or no experimental peaks to assign.",
            )
        total_area = _units_area(units) or 1.0
        base_tol = _SHIFT_TOL_PPM.get(nucleus, 0.30)

        # Greedy optimal-by-distance bipartite assignment (deterministic).
        candidates: list[tuple[float, int, int]] = []
        for i, r in enumerate(resonances):
            for j, u in enumerate(units):
                d = abs(u["center_ppm"] - r["delta_ppm"])
                if d <= 3.0 * base_tol:
                    candidates.append((d, i, j))
        candidates.sort()
        assign: dict[int, int] = {}
        used_units: set[int] = set()
        for _d, i, j in candidates:
            if i in assign or j in used_units:
                continue
            assign[i] = j
            used_units.add(j)

        mult_consistency = _multiplicity_consistency(coupling_set, units)
        merits: list[float] = []
        explained_area = 0.0
        for i, r in enumerate(resonances):
            if i not in assign:
                merits.append(0.0)
                continue
            u = units[assign[i]]
            d = abs(u["center_ppm"] - r["delta_ppm"])
            shift_merit = math.exp(-0.5 * (d / base_tol) ** 2)
            integ_merit = 1.0
            if nucleus == "1H" and total_h > 0:
                obs = total_h * u["area"] / total_area
                integ_merit = math.exp(-0.5 * ((obs - r["count"]) / (0.5 + 0.15 * r["count"])) ** 2)
            merits.append(shift_merit * (0.5 + 0.5 * integ_merit))
            explained_area += u["area"]
        merit = (sum(merits) / len(resonances)) * (0.5 + 0.5 * mult_consistency)
        score = 2.0 * merit - 1.0
        impurity_pct = 100.0 * (total_area - explained_area) / total_area
        significance = _SIG_MAX * _clip(1.0 - impurity_pct / _IMPURITY_REF_PCT, 0.0, 1.0)
        diagnostic = (
            f"Assigned {len(assign)}/{len(resonances)} predicted {nucleus} resonances "
            f"(merit {merit:.2f}, multiplicity consistency {mult_consistency:.2f}); "
            f"unexplained integral {impurity_pct:.0f}% -> significance "
            f"{significance:.1f} ({_sig_band(significance)})."
        )
        return TestResult.create(
            name=self.name,
            score=score,
            significance=significance,
            prior_confidence=prior_confidence,
            diagnostic=diagnostic,
            details={
                "assigned": len(assign),
                "total_resonances": len(resonances),
                "merit": round(merit, 3),
                "impurity_pct": round(impurity_pct, 1),
                "multiplicity_consistency": round(mult_consistency, 3),
            },
        )


# --------------------------------------------------------------------------- #
# Test 3 — HSQC2DRangesTest
# --------------------------------------------------------------------------- #
class HSQC2DRangesTest:
    """Predict one-bond C-H (HSQC) cross-peak rectangles and check coverage.

    Requires experimental HSQC peaks ``[(delta_H, delta_C), ...]`` via
    :class:`VerificationOptions`; abstains if none are supplied.  Returns the
    matched / missing / extra cross-peak counts in ``details``.
    """

    name = "hsqc_2d_ranges"

    def run(
        self,
        *,
        prediction: ShiftPrediction,
        mol_h: Chem.Mol,
        options: VerificationOptions,
        prior_confidence: float,
    ) -> TestResult:
        hsqc = options.hsqc_peaks
        if not hsqc:
            return TestResult.abstain(
                name=self.name,
                prior_confidence=prior_confidence,
                diagnostic="No experimental HSQC / 2-D peaks supplied; test abstains.",
            )
        shifts = _shift_index(prediction)
        rects: list[tuple[float, float, float, float]] = []
        for atom in mol_h.GetAtoms():
            if atom.GetSymbol() != "H":
                continue
            neighbours = atom.GetNeighbors()
            if len(neighbours) != 1 or neighbours[0].GetSymbol() != "C":
                continue
            hs = shifts.get(atom.GetIdx())
            cs = shifts.get(neighbours[0].GetIdx())
            if hs is None or cs is None:
                continue
            tol_h = (
                max(_HSQC_TOL_H, _TOL_SIGMA_K * hs.uncertainty_ppm)
                if math.isfinite(hs.uncertainty_ppm)
                else _HSQC_TOL_H
            )
            tol_c = (
                max(_HSQC_TOL_C, _TOL_SIGMA_K * cs.uncertainty_ppm)
                if math.isfinite(cs.uncertainty_ppm)
                else _HSQC_TOL_C
            )
            rects.append((hs.predicted_ppm, cs.predicted_ppm, tol_h, tol_c))
        if not rects:
            return TestResult.abstain(
                name=self.name,
                prior_confidence=prior_confidence,
                diagnostic="Proposed structure has no C-H correlations to predict.",
            )
        exp = [(float(h), float(c)) for h, c in hsqc]
        covered = [False] * len(exp)
        matched = 0
        for dh, dc, th, tc in rects:
            hit = False
            for k, (eh, ec) in enumerate(exp):
                if abs(eh - dh) <= th and abs(ec - dc) <= tc:
                    covered[k] = True
                    hit = True
            if hit:
                matched += 1
        missing = len(rects) - matched
        extra = sum(1 for c in covered if not c)
        n = len(rects)
        score = _clip((matched - missing - extra) / n, -1.0, 1.0)
        significance = _SIG_MAX * n / (n + _HSQC_SAT)
        diagnostic = (
            f"HSQC coverage: {matched}/{n} predicted C-H correlations matched, "
            f"{missing} missing, {extra} unexplained experimental cross-peaks -> "
            f"significance {significance:.1f} ({_sig_band(significance)})."
        )
        return TestResult.create(
            name=self.name,
            score=score,
            significance=significance,
            prior_confidence=prior_confidence,
            diagnostic=diagnostic,
            details={"matched": matched, "missing": missing, "extra": extra, "predicted": n},
        )


# --------------------------------------------------------------------------- #
# Test 4 — MSMoleculeMatchTest
# --------------------------------------------------------------------------- #
def _predict_ms(mol: Chem.Mol, adduct: str) -> list[tuple[float, float]]:
    """First-principles low-resolution isotope envelope for ``[M, M+1, M+2]``.

    The molecular-ion m/z is the monoisotopic mass plus the requested adduct
    (z = 1).  The envelope is a first-order natural-abundance model: M+1 from
    13C / 15N, M+2 from two 13C and from the M+2 elements (34S, 37Cl, 81Br),
    using IUPAC-2016 abundances.  Intensities are normalised so the base peak
    is 1.0.  This is a coarse corroboration model — not a high-resolution
    isotope simulation — and is documented as such.
    """

    mol_h = Chem.AddHs(mol)
    counts: dict[str, int] = {}
    for atom in mol_h.GetAtoms():
        counts[atom.GetSymbol()] = counts.get(atom.GetSymbol(), 0) + 1
    neutral = Descriptors.ExactMolWt(mol_h)

    key = adduct.replace(" ", "")
    if key in ("[M-H]-", "[M-H]"):
        m0 = neutral - _PROTON_MASS
    elif key in ("[M+Na]+", "[M+Na]"):
        m0 = neutral + _NA_MASS
    elif key in ("[M]+", "[M]", "M"):
        m0 = neutral
    else:  # default [M+H]+
        m0 = neutral + _PROTON_MASS

    n_c = counts.get("C", 0)
    i0 = 1.0
    i1 = n_c * _AB_13C + counts.get("N", 0) * _AB_15N
    i2 = (
        (n_c * (n_c - 1) / 2.0) * _AB_13C**2
        + counts.get("S", 0) * _AB_34S
        + counts.get("Cl", 0) * _AB_37CL
        + counts.get("Br", 0) * _AB_81BR
    )
    raw = [(m0, i0), (m0 + _C13_GAP, i1), (m0 + 2 * _C13_GAP, i2)]
    scale = max(i for _, i in raw) or 1.0
    return [(mz, i / scale) for mz, i in raw if i > 1e-6]


def _ms_cosine(
    predicted: list[tuple[float, float]],
    experimental: list[tuple[float, float]],
    tol: float,
) -> tuple[float, float, float | None]:
    """Intensity-weighted cosine of predicted vs experimental MS within ``tol``.

    Returns ``(cosine, matched_predicted_intensity_fraction, mol_ion_ppm_error)``.
    """

    used: set[int] = set()
    pred_vec: list[float] = []
    exp_vec: list[float] = []
    matched_int = 0.0
    total_pred_int = sum(i for _, i in predicted) or 1.0
    for mz, ip in predicted:
        best = None
        best_d = tol
        for k, (emz, _ie) in enumerate(experimental):
            if k in used:
                continue
            d = abs(emz - mz)
            if d <= best_d:
                best = k
                best_d = d
        pred_vec.append(ip)
        if best is None:
            exp_vec.append(0.0)
        else:
            used.add(best)
            exp_vec.append(experimental[best][1])
            matched_int += ip
    pv = np.asarray(pred_vec, dtype=float)
    ev = np.asarray(exp_vec, dtype=float)
    denom = float(np.linalg.norm(pv) * np.linalg.norm(ev))
    cosine = float(pv.dot(ev) / denom) if denom > 0 else 0.0

    mol_ion_ppm: float | None = None
    if predicted:
        mz0 = predicted[0][0]
        best_d = tol
        for emz, _ie in experimental:
            d = abs(emz - mz0)
            if d <= best_d:
                mol_ion_ppm = round(1e6 * (emz - mz0) / mz0, 1)
                best_d = d
    return cosine, matched_int / total_pred_int, mol_ion_ppm


class MSMoleculeMatchTest:
    """Intensity-weighted dot product of predicted vs experimental MS.

    Requires experimental MS peaks ``[(m/z, intensity), ...]`` via
    :class:`VerificationOptions`; abstains if none are supplied.  The m/z
    accuracy (``ms_mz_tolerance_da``) comes from the user spec and drives both
    the match window and the significance (a tighter accuracy that still
    matches counts for more).
    """

    name = "ms_molecule_match"

    def run(
        self,
        *,
        mol: Chem.Mol,
        options: VerificationOptions,
        prior_confidence: float,
    ) -> TestResult:
        ms = options.ms_peaks
        if not ms:
            return TestResult.abstain(
                name=self.name,
                prior_confidence=prior_confidence,
                diagnostic="No experimental MS peaks supplied; test abstains.",
            )
        try:
            predicted = _predict_ms(mol, options.ms_adduct)
        except Exception as exc:  # pragma: no cover - defensive
            return TestResult.abstain(
                name=self.name,
                prior_confidence=prior_confidence,
                diagnostic=f"Could not predict an MS pattern: {exc}.",
            )
        experimental = [(float(mz), max(0.0, float(i))) for mz, i in ms]
        tol = max(1e-4, float(options.ms_mz_tolerance_da))
        cosine, matched_frac, mol_ion_ppm = _ms_cosine(predicted, experimental, tol)
        score = 2.0 * cosine - 1.0
        accuracy = _clip(_MS_REF_TOL_DA / tol, 0.0, 1.0)
        significance = _SIG_MAX * matched_frac * accuracy
        ion_text = f"{mol_ion_ppm:.0f} ppm" if mol_ion_ppm is not None else "n/a (ion absent)"
        diagnostic = (
            f"MS match (adduct {options.ms_adduct}): intensity-weighted cosine "
            f"{cosine:.2f} within {tol:g} Da; molecular-ion error {ion_text} -> "
            f"significance {significance:.1f} ({_sig_band(significance)})."
        )
        return TestResult.create(
            name=self.name,
            score=score,
            significance=significance,
            prior_confidence=prior_confidence,
            diagnostic=diagnostic,
            details={
                "cosine": round(cosine, 3),
                "matched_predicted_fraction": round(matched_frac, 3),
                "molecular_ion_ppm_error": mol_ion_ppm,
                "predicted_envelope": [(round(mz, 4), round(i, 3)) for mz, i in predicted],
            },
        )


# --------------------------------------------------------------------------- #
# Combination + public entry point
# --------------------------------------------------------------------------- #
_ALL_TESTS = ("prediction_bounds", "assignments", "hsqc_2d_ranges", "ms_molecule_match")


def _combine(prior_confidence: float, results: list[TestResult]) -> tuple[float, dict[str, Any]]:
    p0 = _clip(float(prior_confidence), 1e-6, 1.0 - 1e-6)
    prior_logit = math.log(p0 / (1.0 - p0))
    total = prior_logit
    contributions: list[dict[str, Any]] = []
    for r in results:
        llr = r.quality * LN10 if r.applicable else 0.0
        total += llr
        contributions.append(
            {
                "name": r.name,
                "applicable": r.applicable,
                "score": round(r.score, 4),
                "significance": round(r.significance, 3),
                "quality": round(r.quality, 4),
                "log_likelihood_ratio": round(llr, 4),
            }
        )
    posterior = 1.0 / (1.0 + math.exp(-total))
    combination = {
        "model": "bayesian_log_odds",
        "evidence_unit_ln": round(LN10, 6),
        "prior_confidence": p0,
        "prior_logit": round(prior_logit, 4),
        "posterior_logit": round(total, 4),
        "posterior_confidence": posterior,
        "contributions": contributions,
        "parameters": {
            "verdict_consistent_at": VERDICT_CONSISTENT_AT,
            "verdict_inconsistent_at": VERDICT_INCONSISTENT_AT,
            "sig_max": _SIG_MAX,
            "sigma_ref_ppm": dict(_SIGMA_REF_PPM),
            "impurity_ref_pct": _IMPURITY_REF_PCT,
        },
    }
    return posterior, combination


def _verdict(posterior: float, results: list[TestResult]) -> str:
    if not any(r.applicable for r in results):
        return "inconclusive"
    if posterior >= VERDICT_CONSISTENT_AT:
        return "consistent"
    if posterior <= VERDICT_INCONSISTENT_AT:
        return "inconsistent"
    return "inconclusive"


def verify_structure(
    spectrum: NMRSpectrum,
    proposed_smiles: str,
    prior_confidence: float = 0.5,
    tests: list[str] | None = None,
    options: VerificationOptions | None = None,
) -> VerificationResult:
    """Verify a proposed structure against an experimental 1-D NMR spectrum.

    Runs the requested ``tests`` (default: all) and combines their
    :class:`TestResult` s into a posterior confidence via the transparent
    Bayesian log-odds model documented at the top of this module.  Every
    test's score, significance, quality, and diagnostic — plus the full
    combination arithmetic — is exposed on the returned
    :class:`VerificationResult` for audit (Prompt 12 audit trail).

    Tests whose required data is absent (no HSQC/2-D peaks, no MS peaks in
    ``options``) abstain and do not move the posterior.  Unknown test names
    raise ``ValueError``.
    """

    options = options or VerificationOptions()
    selected = list(tests) if tests else list(_ALL_TESTS)
    unknown = [t for t in selected if t not in _ALL_TESTS]
    if unknown:
        raise ValueError(
            f"Unknown verification test(s) {unknown}; valid tests are {list(_ALL_TESTS)}."
        )

    warnings: list[str] = []
    nucleus = _normalise_nucleus(options.nucleus or getattr(spectrum, "nucleus", None))

    mol = Chem.MolFromSmiles(proposed_smiles)
    if mol is None:
        return VerificationResult(
            proposed_smiles=proposed_smiles,
            prior_confidence=float(prior_confidence),
            posterior_confidence=float(_clip(prior_confidence, 0.0, 1.0)),
            verdict="inconclusive",
            test_results=[],
            diagnostic="Invalid SMILES; cannot verify.",
            combination={},
            warnings=["invalid_smiles"],
        )
    mol_h = Chem.AddHs(mol)
    total_h = sum(1 for a in mol_h.GetAtoms() if a.GetSymbol() == "H")

    # Shared, guarded feature extraction (a failure abstains the dependent test
    # rather than crashing the whole verification).
    prediction: ShiftPrediction | None = None
    coupling_set: Any = None
    peaks: list[Peak] = []
    multiplets: list[Multiplet] = []
    try:
        prediction = predict_shifts(proposed_smiles, n_conformers=options.predict_n_conformers)
        warnings.extend(prediction.warnings)
    except Exception as exc:
        warnings.append(f"predict_shifts failed: {exc}")
    try:
        from nmrcheck.jcoupling_prediction import predict_proton_couplings_from_smiles

        coupling_set = predict_proton_couplings_from_smiles(proposed_smiles)
    except Exception as exc:
        warnings.append(f"coupling prediction failed: {exc}")
    try:
        peaks = gsd_peak_pick(spectrum, level=options.gsd_level)
        multiplets = detect_multiplets(peaks) if nucleus == "1H" else []
    except Exception as exc:
        warnings.append(f"peak picking failed: {exc}")

    units = _exp_units(nucleus, multiplets, peaks)

    results: list[TestResult] = []
    for name in selected:
        try:
            if name == "prediction_bounds":
                result = (
                    PredictionBoundsTest().run(
                        prediction=prediction,
                        units=units,
                        nucleus=nucleus,
                        total_h=total_h,
                        prior_confidence=prior_confidence,
                    )
                    if prediction is not None
                    else TestResult.abstain(
                        name=name,
                        prior_confidence=prior_confidence,
                        diagnostic="No shift prediction available.",
                    )
                )
            elif name == "assignments":
                result = (
                    AssignmentsTest().run(
                        prediction=prediction,
                        units=units,
                        coupling_set=coupling_set,
                        nucleus=nucleus,
                        total_h=total_h,
                        prior_confidence=prior_confidence,
                    )
                    if prediction is not None
                    else TestResult.abstain(
                        name=name,
                        prior_confidence=prior_confidence,
                        diagnostic="No shift prediction available.",
                    )
                )
            elif name == "hsqc_2d_ranges":
                result = (
                    HSQC2DRangesTest().run(
                        prediction=prediction,
                        mol_h=mol_h,
                        options=options,
                        prior_confidence=prior_confidence,
                    )
                    if prediction is not None
                    else TestResult.abstain(
                        name=name,
                        prior_confidence=prior_confidence,
                        diagnostic="No shift prediction available.",
                    )
                )
            else:  # ms_molecule_match
                result = MSMoleculeMatchTest().run(
                    mol=mol, options=options, prior_confidence=prior_confidence
                )
        except Exception as exc:  # pragma: no cover - defensive per-test guard
            result = TestResult.abstain(
                name=name,
                prior_confidence=prior_confidence,
                diagnostic=f"Test errored and was skipped: {exc}.",
            )
        results.append(result)

    posterior, combination = _combine(prior_confidence, results)
    verdict = _verdict(posterior, results)
    n_applicable = sum(1 for r in results if r.applicable)
    diagnostic = (
        f"{verdict.upper()}: posterior confidence {posterior:.2f} from prior "
        f"{float(prior_confidence):.2f} using {n_applicable}/{len(results)} applicable "
        f"test(s) on the {nucleus} spectrum."
    )
    return VerificationResult(
        proposed_smiles=proposed_smiles,
        prior_confidence=float(prior_confidence),
        posterior_confidence=posterior,
        verdict=verdict,
        test_results=results,
        diagnostic=diagnostic,
        combination=combination,
        warnings=warnings,
    )
