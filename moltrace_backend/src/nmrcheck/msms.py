from __future__ import annotations

import math
import re
from dataclasses import dataclass
from collections.abc import Iterable

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from .chemistry import mol_from_smiles
from .exceptions import StructureParseError
from .hrms import MONOISOTOPIC_MASS, PROTON_MASS, formula_from_smiles, normalize_adduct, ppm_error, ppm_score, theoretical_mz
from .models import (
    HRMSAdductInfo,
    MSMSAnnotationRequest,
    MSMSAnnotationResult,
    MSMSCandidateAnnotation,
    MSMSFragmentMatch,
    MSMSNeutralLossHit,
    MSMSPeak,
)


class MSMSError(ValueError):
    pass


@dataclass(frozen=True)
class NeutralLossRule:
    name: str
    mass: float
    explanation: str
    requires_any: tuple[str, ...] = ()


NEUTRAL_LOSS_RULES: tuple[NeutralLossRule, ...] = (
    NeutralLossRule("H2O", 18.010565, "water loss; common from alcohols, acids, hydrates, and dehydrating ions", ("oxygen", "hydroxyl", "carboxyl")),
    NeutralLossRule("NH3", 17.026549, "ammonia loss; common from amines, amides, and amino compounds", ("nitrogen", "amine", "amide")),
    NeutralLossRule("CO", 27.994915, "carbon monoxide loss; common from carbonyl-containing fragments", ("carbonyl", "aldehyde", "ketone", "ester", "amide")),
    NeutralLossRule("C2H4", 28.031300, "ethylene loss; common alkyl-chain fragmentation / rearrangement loss", ("alkyl",)),
    NeutralLossRule("CH3OH", 32.026215, "methanol loss; common from methoxy groups and methyl esters", ("methoxy", "ester")),
    NeutralLossRule("H2S", 33.987721, "hydrogen sulfide loss; sulfur-containing candidate support", ("sulfur", "thiol")),
    NeutralLossRule("HCl", 35.976678, "hydrogen chloride loss; chlorine-containing candidate support", ("chlorine",)),
    NeutralLossRule("C2H2O", 42.010565, "ketene loss; common from acetate/ester-related fragmentation", ("ester", "acetyl")),
    NeutralLossRule("CO2", 43.989830, "carbon dioxide loss; common from carboxylic acids, esters, carbonates, and decarboxylation", ("carboxyl", "ester", "carbonate")),
    NeutralLossRule("CH3COOH", 60.021129, "acetic acid loss; common from acetate esters", ("acetate", "ester")),
    NeutralLossRule("SO2", 63.961901, "sulfur dioxide loss; sulfone/sulfonyl-related diagnostic loss", ("sulfur", "sulfone", "sulfonyl")),
    NeutralLossRule("HBr", 79.926160, "hydrogen bromide loss; bromine-containing candidate support", ("bromine",)),
)

FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def parse_msms_peak_text(text: str) -> list[MSMSPeak]:
    peaks: list[MSMSPeak] = []
    for line_no, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        lowered = line.lower()
        if ("mz" in lowered or "m/z" in lowered) and ("int" in lowered or "abund" in lowered):
            continue
        numbers = FLOAT_RE.findall(line.replace("%", " "))
        if len(numbers) < 2:
            if numbers:
                raise MSMSError(f"MS/MS peak line {line_no} must contain both m/z and intensity.")
            continue
        mz = float(numbers[0])
        intensity = float(numbers[1])
        if mz <= 0:
            raise MSMSError(f"MS/MS peak line {line_no} has non-positive m/z.")
        if intensity < 0:
            raise MSMSError(f"MS/MS peak line {line_no} has negative intensity.")
        peaks.append(MSMSPeak(mz=mz, intensity=intensity))
    if not peaks:
        raise MSMSError("No MS/MS peaks were parsed. Provide lines like 'm/z,intensity'.")
    return peaks


def _normalize_peaks(peaks: Iterable[MSMSPeak], *, min_relative_intensity: float, max_peaks: int) -> tuple[list[MSMSPeak], int]:
    raw = [peak for peak in peaks if peak.intensity >= 0.0]
    if not raw:
        raise MSMSError("At least one MS/MS peak is required.")
    max_intensity = max((peak.relative_intensity if peak.relative_intensity is not None else peak.intensity) for peak in raw)
    if max_intensity <= 0:
        raise MSMSError("At least one MS/MS peak must have positive intensity.")
    normalized: list[MSMSPeak] = []
    for peak in raw:
        relative = peak.relative_intensity if peak.relative_intensity is not None else peak.intensity / max_intensity * 100.0
        if relative >= min_relative_intensity:
            normalized.append(peak.model_copy(update={"relative_intensity": round(float(relative), 4)}))
    normalized.sort(key=lambda peak: (peak.relative_intensity or 0.0, peak.intensity), reverse=True)
    return normalized[:max_peaks], len(raw)


def _peak_tolerance(mz: float, *, mz_tolerance_da: float, ppm_tolerance: float) -> float:
    return max(float(mz_tolerance_da), abs(float(mz)) * float(ppm_tolerance) / 1_000_000.0)


def _feature_set_for_mol(mol: Chem.Mol, counts: dict[str, int]) -> set[str]:
    features: set[str] = set()
    if counts.get("C", 0):
        features.add("alkyl")
    if counts.get("O", 0):
        features.add("oxygen")
    if counts.get("N", 0):
        features.add("nitrogen")
    if counts.get("S", 0):
        features.add("sulfur")
    if counts.get("Cl", 0):
        features.add("chlorine")
    if counts.get("Br", 0):
        features.add("bromine")
    smarts = {
        "hydroxyl": "[OX2H]",
        "carboxyl": "[CX3](=O)[OX2H1]",
        "carbonyl": "[CX3]=[OX1]",
        "aldehyde": "[CX3H1](=O)[#6]",
        "ketone": "[#6][CX3](=O)[#6]",
        "ester": "[CX3](=O)[OX2][#6]",
        "amide": "[NX3][CX3](=O)",
        "amine": "[NX3;!$(N=*)]",
        "methoxy": "[OX2]C",
        "acetyl": "CC(=O)",
        "acetate": "CC(=O)O",
        "carbonate": "O=C(O)O",
        "thiol": "[SX2H]",
        "sulfone": "S(=O)(=O)",
        "sulfonyl": "S(=O)(=O)",
    }
    for name, pattern in smarts.items():
        substructure = Chem.MolFromSmarts(pattern)
        if substructure is not None and mol.HasSubstructMatch(substructure):
            features.add(name)
    return features


def _loss_plausible(rule: NeutralLossRule, features: set[str] | None) -> bool:
    if features is None or not rule.requires_any:
        return True
    return any(feature in features for feature in rule.requires_any)


def _neutral_loss_hits(
    peaks: list[MSMSPeak],
    *,
    precursor_mz: float,
    mz_tolerance_da: float,
    ppm_tolerance: float,
    features: set[str] | None = None,
) -> list[MSMSNeutralLossHit]:
    hits: list[MSMSNeutralLossHit] = []
    seen: set[tuple[float, str]] = set()
    for peak in peaks:
        if peak.mz >= precursor_mz:
            continue
        observed_loss = precursor_mz - peak.mz
        for rule in NEUTRAL_LOSS_RULES:
            error = observed_loss - rule.mass
            tolerance = _peak_tolerance(rule.mass, mz_tolerance_da=mz_tolerance_da, ppm_tolerance=ppm_tolerance)
            if abs(error) > tolerance:
                continue
            key = (round(peak.mz, 5), rule.name)
            if key in seen:
                continue
            seen.add(key)
            plausible = _loss_plausible(rule, features)
            hits.append(
                MSMSNeutralLossHit(
                    fragment_mz=round(peak.mz, 6),
                    intensity=peak.intensity,
                    relative_intensity=round(float(peak.relative_intensity or 0.0), 4),
                    loss_name=rule.name,
                    observed_loss_da=round(observed_loss, 6),
                    expected_loss_da=round(rule.mass, 6),
                    error_da=round(error, 6),
                    ppm_error=round(error / rule.mass * 1_000_000.0, 3) if rule.mass > 0 else None,
                    chemically_plausible=plausible,
                    interpretation=rule.explanation if plausible else f"{rule.explanation}; candidate lacks the usual supporting feature.",
                )
            )
    hits.sort(key=lambda hit: (hit.chemically_plausible, hit.relative_intensity), reverse=True)
    return hits


def _clean_formula(formula: str) -> str:
    return formula.replace("*", "")


def _fragment_hypotheses(
    mol: Chem.Mol,
    adduct: HRMSAdductInfo,
    precursor_theory_mz: float,
    features: set[str],
) -> list[dict[str, object]]:
    hypotheses: list[dict[str, object]] = [
        {
            "mz": precursor_theory_mz,
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "fragment_type": f"precursor {adduct.name}",
            "explanation": "Observed peak is consistent with the precursor/adduct ion.",
        }
    ]
    add_positive = adduct.ion_mode in {"positive", "neutral"}
    add_negative = adduct.ion_mode in {"negative", "neutral"}
    seen: set[tuple[str, str, float]] = set()

    for bond in mol.GetBonds():
        if bond.IsInRing() or bond.GetBondTypeAsDouble() > 1.5:
            continue
        try:
            broken = Chem.FragmentOnBonds(mol, [bond.GetIdx()], addDummies=True)
            fragments = Chem.GetMolFrags(broken, asMols=True, sanitizeFrags=True)
        except Exception:
            continue
        for fragment in fragments:
            try:
                formula = _clean_formula(rdMolDescriptors.CalcMolFormula(fragment))
                mass = float(rdMolDescriptors.CalcExactMolWt(fragment))
            except Exception:
                continue
            if not formula or mass < 10.0:
                continue
            ion_options: list[tuple[float, str]] = []
            if add_positive:
                ion_options.append((mass + PROTON_MASS, "[fragment+H]+"))
                ion_options.append((mass, "fragment radical/nominal cation"))
                if adduct.name == "[M+Na]+":
                    ion_options.append((mass + MONOISOTOPIC_MASS["Na"] - 0.000548579909065, "[fragment+Na]+"))
            if add_negative:
                if mass > PROTON_MASS:
                    ion_options.append((mass - PROTON_MASS, "[fragment-H]-"))
                ion_options.append((mass, "fragment radical/nominal anion"))
            for mz_value, fragment_type in ion_options:
                key = (formula, fragment_type, round(mz_value, 5))
                if key in seen:
                    continue
                seen.add(key)
                hypotheses.append(
                    {
                        "mz": mz_value,
                        "formula": formula,
                        "fragment_type": fragment_type,
                        "explanation": f"Single-bond candidate fragment {formula} assigned as {fragment_type}.",
                    }
                )

    for rule in NEUTRAL_LOSS_RULES:
        if not _loss_plausible(rule, features):
            continue
        mz_value = precursor_theory_mz - rule.mass / max(abs(adduct.charge or 1), 1)
        if mz_value <= 0:
            continue
        hypotheses.append(
            {
                "mz": mz_value,
                "formula": None,
                "fragment_type": f"precursor neutral loss {rule.name}",
                "explanation": f"Precursor ion minus {rule.name}: {rule.explanation}.",
            }
        )
    hypotheses.sort(key=lambda item: float(item["mz"]))
    return hypotheses


def _match_peak_to_hypothesis(
    peak: MSMSPeak,
    hypotheses: list[dict[str, object]],
    *,
    mz_tolerance_da: float,
    ppm_tolerance: float,
) -> MSMSFragmentMatch | None:
    tolerance = _peak_tolerance(peak.mz, mz_tolerance_da=mz_tolerance_da, ppm_tolerance=ppm_tolerance)
    best: tuple[float, dict[str, object]] | None = None
    for hypothesis in hypotheses:
        theoretical = float(hypothesis["mz"])
        delta = abs(peak.mz - theoretical)
        if delta <= tolerance and (best is None or delta < best[0]):
            best = (delta, hypothesis)
    if best is None:
        return None
    theoretical = float(best[1]["mz"])
    error = ppm_error(peak.mz, theoretical)
    return MSMSFragmentMatch(
        peak_mz=round(peak.mz, 6),
        intensity=peak.intensity,
        relative_intensity=round(float(peak.relative_intensity or 0.0), 4),
        theoretical_mz=round(theoretical, 6),
        ppm_error=round(error, 3),
        formula=best[1].get("formula") if isinstance(best[1].get("formula"), str) else None,
        fragment_type=str(best[1].get("fragment_type") or "fragment"),
        explanation=str(best[1].get("explanation") or "Peak matched a candidate fragment hypothesis."),
        metadata={"abs_error_da": round(abs(peak.mz - theoretical), 6)},
    )


def _candidate_label(score: float, precursor_score: float, valid: bool) -> str:
    if not valid:
        return "invalid_structure"
    if score >= 0.65 and precursor_score >= 0.40:
        return "consistent_with_msms"
    if score >= 0.35:
        return "partial_msms_support"
    return "weak_or_no_msms_support"


def annotate_msms(request: MSMSAnnotationRequest) -> MSMSAnnotationResult:
    adduct = normalize_adduct(request.adduct)
    warnings: list[str] = []
    if request.ion_mode and adduct.ion_mode != "neutral" and request.ion_mode != adduct.ion_mode:
        warnings.append(f"Requested ion mode {request.ion_mode!r} differs from adduct mode {adduct.ion_mode!r}; adduct mode was used.")

    peaks_input = list(request.peaks or [])
    if request.peak_list_text:
        peaks_input.extend(parse_msms_peak_text(request.peak_list_text))
    if not peaks_input:
        raise MSMSError("Provide MS/MS peaks either as 'peaks' or 'peak_list_text'.")

    peaks, raw_peak_count = _normalize_peaks(
        peaks_input,
        min_relative_intensity=request.min_relative_intensity,
        max_peaks=request.max_peaks_to_annotate,
    )
    if not peaks:
        raise MSMSError("No MS/MS peaks remain after the relative-intensity filter.")

    global_losses = _neutral_loss_hits(
        peaks,
        precursor_mz=request.precursor_mz,
        mz_tolerance_da=request.mz_tolerance_da,
        ppm_tolerance=request.ppm_tolerance,
        features=None,
    )

    ranked: list[MSMSCandidateAnnotation] = []
    total_relative_intensity = sum(float(peak.relative_intensity or 0.0) for peak in peaks) or 1.0
    for candidate in request.candidates:
        item_warnings: list[str] = []
        evidence: list[str] = []
        valid = True
        formula = None
        precursor_theory = None
        precursor_err = None
        precursor_score = 0.0
        fragment_matches: list[MSMSFragmentMatch] = []
        candidate_losses: list[MSMSNeutralLossHit] = []
        score = 0.0
        explained_fraction = 0.0

        try:
            mol = mol_from_smiles(candidate.smiles)
            info = formula_from_smiles(candidate.smiles)
            formula = info.formula
            features = _feature_set_for_mol(mol, info.element_counts)
            precursor_theory = theoretical_mz(info.exact_mass, adduct)
            precursor_err = ppm_error(request.precursor_mz, precursor_theory)
            precursor_score = ppm_score(precursor_err, request.ppm_tolerance)
            hypotheses = _fragment_hypotheses(mol, adduct, precursor_theory, features)
            seen_peak_keys: set[float] = set()
            for peak in peaks:
                match = _match_peak_to_hypothesis(
                    peak,
                    hypotheses,
                    mz_tolerance_da=request.mz_tolerance_da,
                    ppm_tolerance=request.ppm_tolerance,
                )
                if match is not None:
                    key = round(peak.mz, 5)
                    if key not in seen_peak_keys:
                        fragment_matches.append(match)
                        seen_peak_keys.add(key)

            candidate_losses = _neutral_loss_hits(
                peaks,
                precursor_mz=request.precursor_mz,
                mz_tolerance_da=request.mz_tolerance_da,
                ppm_tolerance=request.ppm_tolerance,
                features=features,
            )
            plausible_loss_peak_keys = {round(hit.fragment_mz, 5) for hit in candidate_losses if hit.chemically_plausible}
            explained_peak_keys = {round(match.peak_mz, 5) for match in fragment_matches} | plausible_loss_peak_keys
            explained_intensity = sum(float(peak.relative_intensity or 0.0) for peak in peaks if round(peak.mz, 5) in explained_peak_keys)
            explained_fraction = round(max(0.0, min(1.0, explained_intensity / total_relative_intensity)), 4)
            coverage = len(explained_peak_keys) / max(len(peaks), 1)
            plausible_loss_count = sum(1 for hit in candidate_losses if hit.chemically_plausible)
            neutral_loss_score = min(1.0, plausible_loss_count / max(1, len(global_losses) or 2))
            score = round(max(0.0, min(1.0, 0.30 * precursor_score + 0.40 * explained_fraction + 0.20 * coverage + 0.10 * neutral_loss_score)), 4)
            evidence.append(f"{formula} theoretical {adduct.name} precursor m/z {precursor_theory:.6f}; precursor error {precursor_err:+.2f} ppm.")
            evidence.append(f"Explained {len(explained_peak_keys)} of {len(peaks)} filtered MS/MS peaks; explained intensity fraction {explained_fraction:.2%}.")
            if plausible_loss_count:
                evidence.append(f"Found {plausible_loss_count} chemically plausible neutral-loss annotation(s).")
            if fragment_matches:
                top = sorted(fragment_matches, key=lambda match: match.relative_intensity, reverse=True)[:3]
                evidence.append("Top fragment matches: " + "; ".join(f"{match.peak_mz:.4f}->{match.formula or match.fragment_type}" for match in top) + ".")
        except StructureParseError as exc:
            valid = False
            item_warnings.append(str(exc))
        except Exception as exc:
            valid = False
            item_warnings.append(f"MS/MS candidate annotation failed: {exc}")

        explained_peak_count = len({round(match.peak_mz, 5) for match in fragment_matches} | {round(hit.fragment_mz, 5) for hit in candidate_losses if hit.chemically_plausible})
        ranked.append(
            MSMSCandidateAnnotation(
                rank=0,
                name=candidate.name,
                role=candidate.role,
                smiles=candidate.smiles,
                label=_candidate_label(score, precursor_score, valid),
                formula=formula,
                precursor_theoretical_mz=round(precursor_theory, 6) if precursor_theory is not None else None,
                precursor_ppm_error=round(precursor_err, 3) if precursor_err is not None else None,
                precursor_score=round(precursor_score, 4),
                fragment_match_count=len(fragment_matches),
                neutral_loss_count=len(candidate_losses),
                explained_peak_count=explained_peak_count,
                explained_intensity_fraction=explained_fraction,
                candidate_score=score,
                fragment_matches=sorted(fragment_matches, key=lambda match: match.relative_intensity, reverse=True)[:50],
                neutral_loss_hits=candidate_losses[:50],
                evidence_summary=evidence,
                warnings=item_warnings,
                metadata={
                    "max_peaks_to_annotate": request.max_peaks_to_annotate,
                    "min_relative_intensity": request.min_relative_intensity,
                },
            )
        )

    ranked_raw = sorted(ranked, key=lambda item: (item.candidate_score, item.precursor_score, item.explained_intensity_fraction), reverse=True)
    ranked_final = [item.model_copy(update={"rank": idx + 1}) for idx, item in enumerate(ranked_raw)]
    best = ranked_final[0] if ranked_final else None

    annotated_global_peaks = {round(hit.fragment_mz, 5) for hit in global_losses}
    if best:
        annotated_global_peaks.update(round(match.peak_mz, 5) for match in best.fragment_matches)
    return MSMSAnnotationResult(
        sample_id=request.sample_id,
        precursor_mz=request.precursor_mz,
        adduct=adduct,
        mz_tolerance_da=request.mz_tolerance_da,
        ppm_tolerance=request.ppm_tolerance,
        peak_count=raw_peak_count,
        annotated_peak_count=len(annotated_global_peaks),
        candidate_count=len(ranked_final),
        best_candidate=best,
        ranked_candidates=ranked_final,
        neutral_loss_hits=global_losses[:100],
        warnings=warnings,
        notes=[
            "Processed MS/MS annotation is a complementary evidence layer: it explains fragments and neutral losses, but it does not prove a structure by itself.",
            "This beta layer uses transparent heuristic fragmentation, neutral-loss rules, exact precursor mass, and candidate-specific checks; raw vendor parsing and full fragmentation trees are intentionally deferred.",
        ],
        metadata={
            "filtered_peak_count": len(peaks),
            "min_relative_intensity": request.min_relative_intensity,
            "max_peaks_to_annotate": request.max_peaks_to_annotate,
        },
    )
