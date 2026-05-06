from __future__ import annotations

from typing import Any

from rdkit import Chem

from .carbon13 import parse_carbon13_text
from .chemistry import mol_from_smiles, structure_summary_from_smiles
from .evidence import greedy_set_similarity
from .exceptions import StructureParseError
from .models import PredictedNMRPeak, PredictedNMRReport, SpectralSimilarityLayerResult, SpectralSimilarityMatch
from .nmr2d import NMR2DPeak, NMR2DPreviewReport
from .parser import parse_nmr_text
from .spectral_similarity import (
    _clean_carbon13_text_for_similarity,
    _combine_vector_set,
    _cosine_similarity,
    gaussian_vectorize_1d,
    score_nmr2d_similarity,
)


HALOGENS = {9, 17, 35, 53}
HETERO = {7, 8, 16}


def _atom_neighbors(atom: Chem.Atom) -> list[Chem.Atom]:
    return [neighbor for neighbor in atom.GetNeighbors()]


def _bond_order(atom: Chem.Atom, neighbor: Chem.Atom) -> float:
    bond = atom.GetOwningMol().GetBondBetweenAtoms(atom.GetIdx(), neighbor.GetIdx())
    if bond is None:
        return 0.0
    return float(bond.GetBondTypeAsDouble())


def _has_double_bond_to(atom: Chem.Atom, atomic_num: int) -> bool:
    return any(neighbor.GetAtomicNum() == atomic_num and _bond_order(atom, neighbor) >= 1.8 for neighbor in _atom_neighbors(atom))


def _is_carbonyl_carbon(atom: Chem.Atom) -> bool:
    return atom.GetAtomicNum() == 6 and _has_double_bond_to(atom, 8)


def _attached_to(atom: Chem.Atom, atomic_nums: set[int]) -> bool:
    return any(neighbor.GetAtomicNum() in atomic_nums for neighbor in _atom_neighbors(atom))


def _alpha_to_carbonyl(atom: Chem.Atom) -> bool:
    return any(neighbor.GetAtomicNum() == 6 and _is_carbonyl_carbon(neighbor) for neighbor in _atom_neighbors(atom))


def _neighbor_carbon_attached_to(atom: Chem.Atom, atomic_nums: set[int]) -> bool:
    for neighbor in _atom_neighbors(atom):
        if neighbor.GetAtomicNum() != 6:
            continue
        if any(second.GetAtomicNum() in atomic_nums and second.GetIdx() != atom.GetIdx() for second in _atom_neighbors(neighbor)):
            return True
    return False


def _attached_to_aromatic(atom: Chem.Atom) -> bool:
    return any(neighbor.GetIsAromatic() for neighbor in _atom_neighbors(atom))


def _carbon_type(atom: Chem.Atom) -> str:
    attached_h = int(atom.GetTotalNumHs(includeNeighbors=False))
    if attached_h <= 0:
        return "C"
    if attached_h == 1:
        return "CH"
    if attached_h == 2:
        return "CH2"
    return "CH3"


def _experiment_label(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value")).upper()
    return str(value or "UNKNOWN").upper()


def _predict_carbon_shift(atom: Chem.Atom) -> tuple[float, float, str, list[str]]:
    warnings: list[str] = []
    attached_h = int(atom.GetTotalNumHs(includeNeighbors=False))
    hybrid = atom.GetHybridization()
    if _is_carbonyl_carbon(atom):
        attached = {neighbor.GetAtomicNum() for neighbor in _atom_neighbors(atom)}
        if attached & {8, 7, 16}:
            return 170.0, 4.5, "carbonyl_carboxylate_ester_amide", warnings
        if attached_h:
            return 195.0, 5.0, "aldehyde_carbonyl", warnings
        return 205.0, 5.0, "ketone_carbonyl", warnings
    if atom.GetIsAromatic():
        substituent_count = max(0, atom.GetDegree() - attached_h)
        shift = 126.0 + min(12.0, substituent_count * 3.0)
        if _attached_to(atom, HETERO):
            shift += 8.0
        return shift, 3.0, "aromatic_carbon", warnings
    if hybrid == Chem.rdchem.HybridizationType.SP2:
        shift = 122.0
        if _attached_to(atom, HETERO):
            shift += 20.0
        return shift, 4.0, "alkene_or_imine_carbon", warnings
    if hybrid == Chem.rdchem.HybridizationType.SP:
        return 78.0, 4.0, "alkyne_or_nitrile_carbon", warnings
    if _attached_to(atom, {8}):
        return 58.5 if attached_h >= 2 else 72.0, 2.0, "oxygenated_aliphatic_carbon", warnings
    if _attached_to(atom, {7}):
        return 48.0 if attached_h >= 2 else 56.0, 2.5, "nitrogenated_aliphatic_carbon", warnings
    if _attached_to(atom, {16}):
        return 35.0, 3.0, "sulfur_adjacent_aliphatic_carbon", warnings
    if _attached_to(atom, HALOGENS):
        return 42.0, 3.5, "halogenated_aliphatic_carbon", warnings
    if attached_h >= 3 and _neighbor_carbon_attached_to(atom, {8}):
        return 18.0, 2.5, "methyl_beta_to_oxygen", warnings
    if attached_h >= 3 and _neighbor_carbon_attached_to(atom, {7, 16}):
        return 16.0, 3.0, "methyl_beta_to_heteroatom", warnings
    if _alpha_to_carbonyl(atom):
        return 31.0 if attached_h >= 2 else 41.0, 3.0, "alpha_to_carbonyl_carbon", warnings
    if _attached_to_aromatic(atom):
        return 38.0 if attached_h >= 2 else 45.0, 3.0, "benzylic_carbon", warnings
    if attached_h >= 3:
        return 14.0, 2.5, "aliphatic_methyl", warnings
    if attached_h == 2:
        return 25.0, 2.5, "aliphatic_methylene", warnings
    if attached_h == 1:
        return 35.0, 3.0, "aliphatic_methine", warnings
    return 42.0, 4.0, "aliphatic_quaternary", warnings


def _predict_proton_shift_for_carbon(atom: Chem.Atom) -> tuple[float, float, str, str, list[str]]:
    warnings: list[str] = []
    attached_h = int(atom.GetTotalNumHs(includeNeighbors=False))
    if attached_h <= 0:
        return 0.0, 0.0, "", "", warnings
    hybrid = atom.GetHybridization()
    if atom.GetIsAromatic():
        return 7.20, 0.25, "aromatic_proton", "m", warnings
    if hybrid == Chem.rdchem.HybridizationType.SP2:
        if _is_carbonyl_carbon(atom):
            return 9.80, 0.35, "aldehydic_proton", "s", warnings
        return 5.60, 0.30, "vinylic_proton", "m", warnings
    if hybrid == Chem.rdchem.HybridizationType.SP:
        return 2.20, 0.30, "alkynyl_proton", "s", warnings
    if _attached_to(atom, {8}):
        return 3.65 if attached_h >= 2 else 4.10, 0.25, "oxygenated_aliphatic_proton", "m", warnings
    if _attached_to(atom, {7}):
        return 2.95 if attached_h >= 2 else 3.40, 0.30, "nitrogenated_aliphatic_proton", "m", warnings
    if _attached_to(atom, {16}):
        return 2.65, 0.35, "sulfur_adjacent_proton", "m", warnings
    if _attached_to(atom, HALOGENS):
        return 3.30, 0.35, "halogenated_aliphatic_proton", "m", warnings
    if attached_h >= 3 and _neighbor_carbon_attached_to(atom, {8}):
        return 1.25, 0.25, "methyl_beta_to_oxygen_proton", "t", warnings
    if attached_h >= 3 and _neighbor_carbon_attached_to(atom, {7, 16}):
        return 1.15, 0.30, "methyl_beta_to_heteroatom_proton", "m", warnings
    if _alpha_to_carbonyl(atom):
        return 2.30, 0.35, "alpha_to_carbonyl_proton", "m", warnings
    if _attached_to_aromatic(atom):
        return 2.45, 0.35, "benzylic_proton", "m", warnings
    if attached_h >= 3:
        return 0.95, 0.25, "aliphatic_methyl_proton", "m", warnings
    if attached_h == 2:
        return 1.35, 0.30, "aliphatic_methylene_proton", "m", warnings
    return 1.55, 0.35, "aliphatic_methine_proton", "m", warnings


def _predict_labile_protons(atom: Chem.Atom) -> PredictedNMRPeak | None:
    atomic_num = atom.GetAtomicNum()
    attached_h = int(atom.GetTotalNumHs(includeNeighbors=False))
    if attached_h <= 0 or atomic_num not in HETERO:
        return None
    if atomic_num == 8:
        if any(_is_carbonyl_carbon(neighbor) for neighbor in _atom_neighbors(atom)):
            shift, environment, uncertainty = 11.0, "carboxylic_acid_oh", 1.5
        elif any(neighbor.GetIsAromatic() for neighbor in _atom_neighbors(atom)):
            shift, environment, uncertainty = 6.5, "phenolic_oh", 1.5
        else:
            shift, environment, uncertainty = 2.5, "alcohol_oh", 1.2
    elif atomic_num == 7:
        shift, environment, uncertainty = 2.8, "amine_or_amide_nh", 1.2
    else:
        shift, environment, uncertainty = 1.5, "thiol_sh", 0.8
    return PredictedNMRPeak(
        nucleus="1H",
        shift_ppm=shift,
        uncertainty_ppm=uncertainty,
        atom_index=atom.GetIdx(),
        integration_h=float(attached_h),
        attached_h=attached_h,
        multiplicity_hint="br",
        environment=environment,
        warnings=["Labile proton shift is solvent, concentration, pH, and exchange dependent."],
    )


def predict_nmr_from_smiles(smiles: str, *, name: str | None = None, solvent: str | None = None) -> PredictedNMRReport:
    warnings: list[str] = []
    notes = [
        "Heuristic prediction uses RDKit atom environments and approximate shift regions.",
        "Use an external/ML predictor for production-grade candidate-specific NMR prediction.",
        "Predicted shifts are ranking evidence and require human review.",
    ]
    try:
        mol = mol_from_smiles(smiles)
        summary = structure_summary_from_smiles(smiles)
    except StructureParseError as exc:
        return PredictedNMRReport(
            name=name,
            smiles=smiles,
            prediction_method="heuristic_rdkit_region_model",
            confidence_label="invalid_structure",
            warnings=[str(exc)],
            notes=notes,
        )

    proton_peaks: list[PredictedNMRPeak] = []
    carbon_peaks: list[PredictedNMRPeak] = []
    carbon_by_atom: dict[int, PredictedNMRPeak] = {}
    proton_by_atom: dict[int, PredictedNMRPeak] = {}

    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 6:
            carbon_shift, carbon_uncertainty, carbon_environment, carbon_warnings = _predict_carbon_shift(atom)
            carbon_peak = PredictedNMRPeak(
                nucleus="13C",
                shift_ppm=round(float(carbon_shift), 3),
                uncertainty_ppm=round(float(carbon_uncertainty), 3),
                atom_index=atom.GetIdx(),
                attached_h=int(atom.GetTotalNumHs(includeNeighbors=False)),
                carbon_type=_carbon_type(atom),
                environment=carbon_environment,
                warnings=carbon_warnings,
            )
            carbon_peaks.append(carbon_peak)
            carbon_by_atom[atom.GetIdx()] = carbon_peak

            attached_h = int(atom.GetTotalNumHs(includeNeighbors=False))
            if attached_h > 0:
                proton_shift, proton_uncertainty, proton_environment, multiplicity, proton_warnings = _predict_proton_shift_for_carbon(atom)
                proton_peak = PredictedNMRPeak(
                    nucleus="1H",
                    shift_ppm=round(float(proton_shift), 3),
                    uncertainty_ppm=round(float(proton_uncertainty), 3),
                    atom_index=atom.GetIdx(),
                    attached_h=attached_h,
                    integration_h=float(attached_h),
                    carbon_type=_carbon_type(atom),
                    multiplicity_hint=multiplicity,
                    environment=proton_environment,
                    warnings=proton_warnings,
                )
                proton_peaks.append(proton_peak)
                proton_by_atom[atom.GetIdx()] = proton_peak
        else:
            labile_peak = _predict_labile_protons(atom)
            if labile_peak is not None:
                proton_peaks.append(labile_peak)

    predicted_hsqc: list[dict[str, Any]] = []
    for atom_idx, proton_peak in proton_by_atom.items():
        carbon_peak = carbon_by_atom.get(atom_idx)
        if carbon_peak is None:
            continue
        predicted_hsqc.append(
            {
                "experiment": "HSQC",
                "f2_ppm": proton_peak.shift_ppm,
                "f1_ppm": carbon_peak.shift_ppm,
                "atom_index": atom_idx,
                "carbon_type": carbon_peak.carbon_type,
                "environment": f"{proton_peak.environment}/{carbon_peak.environment}",
            }
        )

    if len(carbon_peaks) > 20:
        warnings.append("Large candidate: heuristic prediction uncertainty may be high.")
    if any("aromatic" in str(peak.environment or "") for peak in carbon_peaks):
        warnings.append("Aromatic substitution patterns can require ML/DFT prediction for reliable discrimination.")

    uncertainty_values = [peak.uncertainty_ppm for peak in proton_peaks + carbon_peaks]
    avg_uncertainty = sum(uncertainty_values) / len(uncertainty_values) if uncertainty_values else 0.0
    confidence = "high" if avg_uncertainty < 1.0 else "medium" if avg_uncertainty < 3.0 else "low"

    return PredictedNMRReport(
        name=name,
        smiles=smiles,
        formula=summary.formula,
        molecular_weight=summary.molecular_weight,
        prediction_method="heuristic_rdkit_region_model",
        confidence_label=confidence,
        proton_peaks=proton_peaks,
        carbon13_peaks=carbon_peaks,
        predicted_hsqc_crosspeaks=predicted_hsqc,
        warnings=warnings,
        notes=notes,
        metadata={
            "solvent": solvent,
            "heavy_atom_count": mol.GetNumHeavyAtoms(),
            "proton_prediction_count": len(proton_peaks),
            "carbon13_prediction_count": len(carbon_peaks),
            "predicted_hsqc_count": len(predicted_hsqc),
            "average_uncertainty_ppm": round(avg_uncertainty, 4),
        },
    )


def _matches_to_models(matches: list[Any]) -> list[SpectralSimilarityMatch]:
    return [
        SpectralSimilarityMatch(
            observed_ppm=round(match.observed_ppm, 4),
            reference_ppm=round(match.expected_ppm, 4),
            delta_ppm=round(match.delta_ppm, 4),
            score=round(match.score, 4),
        )
        for match in matches[:50]
    ]


def score_observed_against_predicted_proton(observed_text: str, predicted: PredictedNMRReport) -> SpectralSimilarityLayerResult:
    observed = parse_nmr_text(observed_text)
    observed_multiset: list[float] = []
    predicted_multiset: list[float] = []
    for peak in observed:
        observed_multiset.extend([peak.shift_ppm] * max(1, int(round(peak.integration_h))))
    for peak in predicted.proton_peaks:
        if peak.integration_h is None:
            continue
        predicted_multiset.extend([peak.shift_ppm] * max(1, int(round(peak.integration_h))))

    set_score, matches, unmatched_observed, unmatched_predicted = greedy_set_similarity(observed_multiset, predicted_multiset, sigma=0.16)
    vector_score = _cosine_similarity(
        gaussian_vectorize_1d(
            [peak.shift_ppm for peak in observed],
            weights=[peak.integration_h for peak in observed],
            ppm_min=-1.0,
            ppm_max=12.0,
            bins=256,
            sigma=0.10,
        ),
        gaussian_vectorize_1d(
            [peak.shift_ppm for peak in predicted.proton_peaks],
            weights=[peak.integration_h or 1 for peak in predicted.proton_peaks],
            ppm_min=-1.0,
            ppm_max=12.0,
            bins=256,
            sigma=0.10,
        ),
    )
    return SpectralSimilarityLayerResult(
        layer="1H",
        vector_score=vector_score,
        set_score=set_score,
        combined_score=_combine_vector_set(vector_score, set_score),
        observed_count=len(observed_multiset),
        reference_count=len(predicted_multiset),
        matched_count=len(matches),
        unmatched_observed_count=len(unmatched_observed),
        unmatched_reference_count=len(unmatched_predicted),
        matches=_matches_to_models(matches),
        notes=["Observed 1H peaks were matched against candidate-specific predicted 1H shifts."],
        metadata={"reference_kind": "candidate_prediction", "sigma_set_ppm": 0.16},
    )


def score_observed_against_predicted_carbon13(
    observed_text: str,
    predicted: PredictedNMRReport,
    *,
    solvent: str | None = None,
) -> SpectralSimilarityLayerResult:
    cleaned_text = _clean_carbon13_text_for_similarity(observed_text)
    observed = [peak for peak in parse_carbon13_text(cleaned_text, solvent=solvent) if not peak.is_likely_solvent]
    observed_shifts = [peak.shift_ppm for peak in observed]
    predicted_shifts = [peak.shift_ppm for peak in predicted.carbon13_peaks]

    set_score, matches, unmatched_observed, unmatched_predicted = greedy_set_similarity(observed_shifts, predicted_shifts, sigma=3.0)
    vector_score = _cosine_similarity(
        gaussian_vectorize_1d(observed_shifts, ppm_min=0.0, ppm_max=230.0, bins=256, sigma=2.0),
        gaussian_vectorize_1d(predicted_shifts, ppm_min=0.0, ppm_max=230.0, bins=256, sigma=2.0),
    )
    return SpectralSimilarityLayerResult(
        layer="13C",
        vector_score=vector_score,
        set_score=set_score,
        combined_score=_combine_vector_set(vector_score, set_score),
        observed_count=len(observed_shifts),
        reference_count=len(predicted_shifts),
        matched_count=len(matches),
        unmatched_observed_count=len(unmatched_observed),
        unmatched_reference_count=len(unmatched_predicted),
        matches=_matches_to_models(matches),
        notes=["Observed 13C peaks were matched against candidate-specific predicted 13C shifts."],
        warnings=["Heuristic 13C prediction tolerances are broader than experimental/library matching."],
        metadata={"reference_kind": "candidate_prediction", "sigma_set_ppm": 3.0, "solvent": solvent},
    )


def predicted_hsqc_preview(predicted: PredictedNMRReport) -> NMR2DPreviewReport:
    peaks = [
        NMR2DPeak(
            experiment="HSQC",
            f2_ppm=float(crosspeak["f2_ppm"]),
            f1_ppm=float(crosspeak["f1_ppm"]),
            intensity=None,
            assignment=str(crosspeak.get("environment") or ""),
            f2_region=None,
            f1_region=None,
            is_diagonal=False,
            warnings=[],
        )
        for crosspeak in predicted.predicted_hsqc_crosspeaks
    ]
    return NMR2DPreviewReport(
        filename=f"predicted_hsqc_{predicted.name or predicted.smiles}.json",
        experiment_detected="HSQC",
        peak_count=len(peaks),
        peaks=peaks,
        warnings=list(predicted.warnings),
        metadata={"source": "candidate_prediction", "smiles": predicted.smiles},
    )


def score_observed_2d_against_predicted_hsqc(
    observed_preview: NMR2DPreviewReport,
    predicted: PredictedNMRReport,
) -> SpectralSimilarityLayerResult | None:
    if not predicted.predicted_hsqc_crosspeaks:
        return None
    experiment = _experiment_label(observed_preview.experiment_detected)
    if experiment not in {"HSQC", "HMQC", "UNKNOWN"}:
        return None
    return score_nmr2d_similarity(observed_preview, predicted_hsqc_preview(predicted))
