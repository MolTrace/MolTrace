from __future__ import annotations

import math
import re

from rdkit.Chem import rdMolDescriptors

from .chemistry import mol_from_smiles
from .exceptions import StructureParseError
from .models import (
    HRMSAdductInfo,
    HRMSCandidateMatch,
    HRMSCandidateMatchRequest,
    HRMSCandidateMatchResult,
    HRMSFormulaInfo,
    HRMSFormulaSearchRequest,
    HRMSFormulaSearchResult,
)


ELECTRON_MASS = 0.000548579909065
PROTON_MASS = 1.007276466812

MONOISOTOPIC_MASS = {
    "H": 1.00782503223,
    "B": 11.00930536,
    "C": 12.0000000,
    "N": 14.00307400443,
    "O": 15.99491461957,
    "F": 18.99840316273,
    "Na": 22.9897692820,
    "Si": 27.97692653465,
    "P": 30.97376199842,
    "S": 31.9720711744,
    "Cl": 34.968852682,
    "K": 38.9637064864,
    "Br": 78.9183376,
    "I": 126.9044719,
}

ADDUCTS: dict[str, HRMSAdductInfo] = {
    "[M+H]+": HRMSAdductInfo(name="[M+H]+", ion_mode="positive", charge=1, mass_shift=PROTON_MASS, description="protonated molecule"),
    "[M+Na]+": HRMSAdductInfo(
        name="[M+Na]+",
        ion_mode="positive",
        charge=1,
        mass_shift=MONOISOTOPIC_MASS["Na"] - ELECTRON_MASS,
        description="sodium adduct",
    ),
    "[M+K]+": HRMSAdductInfo(
        name="[M+K]+",
        ion_mode="positive",
        charge=1,
        mass_shift=MONOISOTOPIC_MASS["K"] - ELECTRON_MASS,
        description="potassium adduct",
    ),
    "[M+NH4]+": HRMSAdductInfo(name="[M+NH4]+", ion_mode="positive", charge=1, mass_shift=18.033823, description="ammonium adduct"),
    "[M-H]-": HRMSAdductInfo(name="[M-H]-", ion_mode="negative", charge=-1, mass_shift=-PROTON_MASS, description="deprotonated molecule"),
    "[M+Cl]-": HRMSAdductInfo(
        name="[M+Cl]-",
        ion_mode="negative",
        charge=-1,
        mass_shift=MONOISOTOPIC_MASS["Cl"] + ELECTRON_MASS,
        description="chloride adduct",
    ),
    "[M+FA-H]-": HRMSAdductInfo(name="[M+FA-H]-", ion_mode="negative", charge=-1, mass_shift=44.998201, description="formate adduct"),
    "[M+Ac-H]-": HRMSAdductInfo(name="[M+Ac-H]-", ion_mode="negative", charge=-1, mass_shift=59.013851, description="acetate adduct"),
    "M": HRMSAdductInfo(name="M", ion_mode="neutral", charge=1, mass_shift=0.0, description="neutral exact mass"),
}

ADDUCT_ALIASES = {
    "m+h": "[M+H]+",
    "[m+h]+": "[M+H]+",
    "mh+": "[M+H]+",
    "m+na": "[M+Na]+",
    "[m+na]+": "[M+Na]+",
    "m+k": "[M+K]+",
    "[m+k]+": "[M+K]+",
    "m+nh4": "[M+NH4]+",
    "[m+nh4]+": "[M+NH4]+",
    "m-h": "[M-H]-",
    "[m-h]-": "[M-H]-",
    "m+cl": "[M+Cl]-",
    "[m+cl]-": "[M+Cl]-",
    "m+fa-h": "[M+FA-H]-",
    "[m+fa-h]-": "[M+FA-H]-",
    "m+ac-h": "[M+Ac-H]-",
    "[m+ac-h]-": "[M+Ac-H]-",
    "neutral": "M",
    "m": "M",
}

FORMULA_RE = re.compile(r"([A-Z][a-z]?)(\d*)")


class HRMSError(ValueError):
    pass


def normalize_adduct(value: str | None) -> HRMSAdductInfo:
    raw = (value or "[M+H]+").strip()
    if raw in ADDUCTS:
        return ADDUCTS[raw]
    key = raw.lower().replace(" ", "")
    if key in ADDUCT_ALIASES:
        return ADDUCTS[ADDUCT_ALIASES[key]]
    supported = ", ".join(sorted(ADDUCTS))
    raise HRMSError(f"Unsupported HRMS adduct: {raw!r}. Supported adducts: {supported}")


def parse_formula(formula: str) -> dict[str, int]:
    text = formula.strip()
    if not text:
        raise HRMSError("Formula cannot be empty.")
    pos = 0
    counts: dict[str, int] = {}
    for match in FORMULA_RE.finditer(text):
        if match.start() != pos:
            raise HRMSError(f"Could not parse formula near: {text[pos:]!r}")
        element, raw_count = match.groups()
        if element not in MONOISOTOPIC_MASS:
            raise HRMSError(f"Unsupported element in formula: {element}")
        count = int(raw_count) if raw_count else 1
        counts[element] = counts.get(element, 0) + count
        pos = match.end()
    if pos != len(text):
        raise HRMSError(f"Could not parse formula near: {text[pos:]!r}")
    return counts


def format_formula(counts: dict[str, int]) -> str:
    order = ["C", "H", "B", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I"]
    parts: list[str] = []
    for element in order:
        count = int(counts.get(element, 0))
        if count <= 0:
            continue
        parts.append(element if count == 1 else f"{element}{count}")
    for element in sorted(set(counts) - set(order)):
        count = int(counts[element])
        if count > 0:
            parts.append(element if count == 1 else f"{element}{count}")
    return "".join(parts)


def exact_mass_from_formula(formula: str | dict[str, int]) -> float:
    counts = parse_formula(formula) if isinstance(formula, str) else formula
    return sum(MONOISOTOPIC_MASS[element] * count for element, count in counts.items())


def dbe_from_counts(counts: dict[str, int]) -> float | None:
    carbon = counts.get("C", 0)
    hydrogen = counts.get("H", 0)
    halogens = counts.get("F", 0) + counts.get("Cl", 0) + counts.get("Br", 0) + counts.get("I", 0)
    nitrogen = counts.get("N", 0)
    phosphorus = counts.get("P", 0)
    if carbon <= 0:
        return None
    return round(carbon - (hydrogen + halogens) / 2 + (nitrogen + phosphorus) / 2 + 1, 3)


def estimate_isotope_pattern(counts: dict[str, int]) -> tuple[float, float]:
    """Transparent rough M+1/M+2 estimates for formula triage, not full convolution."""
    carbon = counts.get("C", 0)
    hydrogen = counts.get("H", 0)
    nitrogen = counts.get("N", 0)
    oxygen = counts.get("O", 0)
    sulfur = counts.get("S", 0)
    silicon = counts.get("Si", 0)
    chlorine = counts.get("Cl", 0)
    bromine = counts.get("Br", 0)
    m1 = 1.1 * carbon + 0.016 * hydrogen + 0.38 * nitrogen + 0.78 * sulfur + 5.1 * silicon
    m2 = (m1 * m1) / 200.0 + 0.2 * oxygen + 4.4 * sulfur + 3.35 * silicon + 32.5 * chlorine + 98.0 * bromine
    return round(m1, 3), round(m2, 3)


def theoretical_mz(neutral_mass: float, adduct: HRMSAdductInfo) -> float:
    charge = abs(int(adduct.charge or 1))
    return (float(neutral_mass) + adduct.mass_shift) / charge


def neutral_mass_from_mz(observed_mz: float, adduct: HRMSAdductInfo) -> float:
    charge = abs(int(adduct.charge or 1))
    return float(observed_mz) * charge - adduct.mass_shift


def ppm_error(observed_mz: float, expected_mz: float) -> float:
    return (float(observed_mz) - float(expected_mz)) / float(expected_mz) * 1_000_000.0


def ppm_score(error_ppm: float, tolerance_ppm: float) -> float:
    if tolerance_ppm <= 0:
        return 0.0
    scaled = abs(error_ppm) / tolerance_ppm
    return round(max(0.0, min(1.0, math.exp(-0.5 * scaled * scaled))), 4)


def isotope_similarity_score(
    counts: dict[str, int],
    *,
    observed_m_plus_1_percent: float | None = None,
    observed_m_plus_2_percent: float | None = None,
) -> float | None:
    if observed_m_plus_1_percent is None and observed_m_plus_2_percent is None:
        return None
    predicted_m1, predicted_m2 = estimate_isotope_pattern(counts)
    scores: list[float] = []
    if observed_m_plus_1_percent is not None:
        tolerance = max(2.0, predicted_m1 * 0.20)
        scores.append(max(0.0, min(1.0, 1.0 - abs(observed_m_plus_1_percent - predicted_m1) / tolerance)))
    if observed_m_plus_2_percent is not None:
        tolerance = max(2.0, predicted_m2 * 0.20)
        scores.append(max(0.0, min(1.0, 1.0 - abs(observed_m_plus_2_percent - predicted_m2) / tolerance)))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def formula_info(formula: str) -> HRMSFormulaInfo:
    counts = parse_formula(formula)
    m1, m2 = estimate_isotope_pattern(counts)
    return HRMSFormulaInfo(
        formula=format_formula(counts),
        exact_mass=round(exact_mass_from_formula(counts), 6),
        dbe=dbe_from_counts(counts),
        element_counts=counts,
        isotope_m_plus_1_percent=m1,
        isotope_m_plus_2_percent=m2,
    )


def formula_from_smiles(smiles: str) -> HRMSFormulaInfo:
    mol = mol_from_smiles(smiles)
    formula = rdMolDescriptors.CalcMolFormula(mol)
    info = formula_info(formula)
    exact_mass = float(rdMolDescriptors.CalcExactMolWt(mol))
    return info.model_copy(update={"exact_mass": round(exact_mass, 6)})


def _label_match(abs_ppm: float, tolerance: float, valid: bool) -> str:
    if not valid:
        return "invalid_structure"
    if abs_ppm <= tolerance:
        return "exact_mass_match"
    if abs_ppm <= max(tolerance * 2.0, tolerance + 2.0):
        return "possible_match"
    return "outside_tolerance"


def match_hrms_candidates(request: HRMSCandidateMatchRequest) -> HRMSCandidateMatchResult:
    adduct = normalize_adduct(request.adduct)
    warnings: list[str] = []
    if request.ion_mode and adduct.ion_mode != "neutral" and request.ion_mode != adduct.ion_mode:
        warnings.append(f"Requested ion mode {request.ion_mode!r} differs from adduct mode {adduct.ion_mode!r}; adduct mode was used.")

    matches: list[HRMSCandidateMatch] = []
    for candidate in request.candidates:
        evidence: list[str] = []
        item_warnings: list[str] = []
        valid = True
        formula = None
        formula_exact_mass = None
        expected_mz = None
        error = None
        score = 0.0
        iso_score = None
        dbe = None
        try:
            info = formula_from_smiles(candidate.smiles)
            formula = info.formula
            formula_exact_mass = info.exact_mass
            expected_mz = theoretical_mz(formula_exact_mass, adduct)
            error = ppm_error(request.observed_mz, expected_mz)
            score = ppm_score(error, request.ppm_tolerance)
            dbe = info.dbe
            iso_score = isotope_similarity_score(
                info.element_counts,
                observed_m_plus_1_percent=request.observed_m_plus_1_percent,
                observed_m_plus_2_percent=request.observed_m_plus_2_percent,
            )
            if iso_score is not None:
                score = round(0.75 * score + 0.25 * iso_score, 4)
            evidence.append(f"{formula} theoretical {adduct.name} m/z {expected_mz:.6f}; observed error {error:+.2f} ppm.")
            evidence.append(
                "Exact-mass evidence is within tolerance."
                if abs(error) <= request.ppm_tolerance
                else "Exact-mass evidence is outside the requested tolerance."
            )
            if dbe is not None:
                evidence.append(f"DBE/IHD estimate: {dbe:g}.")
        except StructureParseError as exc:
            valid = False
            item_warnings.append(str(exc))

        matches.append(
            HRMSCandidateMatch(
                rank=0,
                name=candidate.name,
                role=candidate.role,
                smiles=candidate.smiles,
                label=_label_match(abs(error) if error is not None else 1e9, request.ppm_tolerance, valid),
                formula=formula,
                neutral_exact_mass=formula_exact_mass,
                theoretical_mz=round(expected_mz, 6) if expected_mz is not None else None,
                observed_mz=request.observed_mz,
                ppm_error=round(error, 4) if error is not None else None,
                abs_mass_error_da=round(abs(request.observed_mz - expected_mz), 6) if expected_mz is not None else None,
                ppm_score=score,
                isotope_score=iso_score,
                dbe=dbe,
                evidence_summary=evidence,
                warnings=item_warnings,
                metadata={"adduct": adduct.model_dump(), "ppm_tolerance": request.ppm_tolerance},
            )
        )

    ranked_raw = sorted(
        matches,
        key=lambda item: (item.ppm_score, -(abs(item.ppm_error) if item.ppm_error is not None else 1e9)),
        reverse=True,
    )
    ranked = [item.model_copy(update={"rank": idx + 1}) for idx, item in enumerate(ranked_raw)]
    exact = sum(1 for item in ranked if item.label == "exact_mass_match")
    possible = sum(1 for item in ranked if item.label == "possible_match")
    return HRMSCandidateMatchResult(
        sample_id=request.sample_id,
        observed_mz=request.observed_mz,
        adduct=adduct,
        ppm_tolerance=request.ppm_tolerance,
        candidate_count=len(ranked),
        best_match=ranked[0] if ranked else None,
        ranked_candidates=ranked,
        exact_match_count=exact,
        possible_match_count=possible,
        warnings=warnings,
        notes=[
            "HRMS exact mass is a constraint layer; it can rule candidates in/out but does not prove structure alone.",
            "Use NMR evidence, isotope pattern, adduct plausibility, and human review together.",
        ],
        metadata={
            "observed_m_plus_1_percent": request.observed_m_plus_1_percent,
            "observed_m_plus_2_percent": request.observed_m_plus_2_percent,
        },
    )


def _formula_search_counts(request: HRMSFormulaSearchRequest):
    target = neutral_mass_from_mz(request.observed_mz, normalize_adduct(request.adduct))
    tolerance_da = target * request.ppm_tolerance / 1_000_000.0
    for carbon in range(1, request.max_c + 1):
        mass_c = carbon * MONOISOTOPIC_MASS["C"]
        if mass_c - tolerance_da > target:
            break
        for nitrogen in range(0, request.max_n + 1):
            mass_cn = mass_c + nitrogen * MONOISOTOPIC_MASS["N"]
            if mass_cn - tolerance_da > target:
                break
            for oxygen in range(0, request.max_o + 1):
                mass_cno = mass_cn + oxygen * MONOISOTOPIC_MASS["O"]
                if mass_cno - tolerance_da > target:
                    break
                for sulfur in range(0, request.max_s + 1):
                    mass_cnos = mass_cno + sulfur * MONOISOTOPIC_MASS["S"]
                    if mass_cnos - tolerance_da > target:
                        break
                    for phosphorus in range(0, request.max_p + 1):
                        mass_cnosp = mass_cnos + phosphorus * MONOISOTOPIC_MASS["P"]
                        if mass_cnosp - tolerance_da > target:
                            break
                        for chlorine in range(0, request.max_cl + 1):
                            mass_base = mass_cnosp + chlorine * MONOISOTOPIC_MASS["Cl"]
                            if mass_base - tolerance_da > target:
                                break
                            for bromine in range(0, request.max_br + 1):
                                mass_heavy = mass_base + bromine * MONOISOTOPIC_MASS["Br"]
                                if mass_heavy - tolerance_da > target:
                                    break
                                hydrogen_float = (target - mass_heavy) / MONOISOTOPIC_MASS["H"]
                                hydrogen_candidates = {
                                    int(round(hydrogen_float)),
                                    int(math.floor(hydrogen_float)),
                                    int(math.ceil(hydrogen_float)),
                                }
                                for hydrogen in hydrogen_candidates:
                                    if hydrogen < 0 or hydrogen > request.max_h:
                                        continue
                                    counts = {
                                        "C": carbon,
                                        "H": hydrogen,
                                        "N": nitrogen,
                                        "O": oxygen,
                                        "S": sulfur,
                                        "P": phosphorus,
                                        "Cl": chlorine,
                                        "Br": bromine,
                                    }
                                    mass = exact_mass_from_formula(counts)
                                    if abs(mass - target) <= tolerance_da:
                                        dbe = dbe_from_counts(counts)
                                        if request.require_nonnegative_dbe and dbe is not None and dbe < -0.001:
                                            continue
                                        yield counts, mass, target


def search_formulas_by_hrms(request: HRMSFormulaSearchRequest) -> HRMSFormulaSearchResult:
    adduct = normalize_adduct(request.adduct)
    neutral = neutral_mass_from_mz(request.observed_mz, adduct)
    warnings: list[str] = []
    formulas: list[HRMSFormulaInfo] = []
    for counts, mass, _target in _formula_search_counts(request):
        m1, m2 = estimate_isotope_pattern(counts)
        formulas.append(
            HRMSFormulaInfo(
                formula=format_formula(counts),
                exact_mass=round(mass, 6),
                dbe=dbe_from_counts(counts),
                element_counts={element: count for element, count in counts.items() if count},
                isotope_m_plus_1_percent=m1,
                isotope_m_plus_2_percent=m2,
            )
        )
        if len(formulas) >= request.max_results:
            warnings.append("Formula search reached max_results; narrow element constraints for exhaustive enumeration.")
            break
    formulas.sort(key=lambda item: abs(ppm_error(neutral, item.exact_mass)))
    return HRMSFormulaSearchResult(
        observed_mz=request.observed_mz,
        neutral_mass=round(neutral, 6),
        adduct=adduct,
        ppm_tolerance=request.ppm_tolerance,
        formula_count=len(formulas),
        formulas=formulas,
        warnings=warnings,
        metadata={
            "search_space": {
                "max_c": request.max_c,
                "max_h": request.max_h,
                "max_n": request.max_n,
                "max_o": request.max_o,
                "max_s": request.max_s,
                "max_p": request.max_p,
                "max_cl": request.max_cl,
                "max_br": request.max_br,
            }
        },
    )
