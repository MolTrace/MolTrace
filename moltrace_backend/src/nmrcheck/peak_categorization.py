"""Per-peak categorization, labile-hydrogen reasoning, and predicted-vs-observed
shift comparison.

The processed-spectrum analyze endpoint returns peaks as loose dicts so this
module enriches each dict in-place with:

  - ``category`` — high-level bucket (aromatic, aliphatic, labile, solvent,
    impurity, ...) that the UI can use for filtering/coloring.
  - ``chemical_region`` — the full descriptive label from
    :func:`classify_proton_region` / :func:`classify_carbon13_region`.
  - ``labile_hint`` — heuristic flag for OH/NH/SH protons.
  - ``solvent_hit`` — the matched solvent/water window dict, when applicable.
  - ``impurity_match`` — closest match from the embedded impurity library.
  - ``category_reason`` — short why-string for explainability.

It also exposes helpers to build the top-level analyze-response fields:

  - :func:`build_peak_category_summary` — per-category peak counts.
  - :func:`build_proton_inventory` — aggregated aromatic / aliphatic / labile /
    non-labile proton totals (observed integrations + structural expectation
    + deltas) including a per-element labile breakdown (OH / NH / SH).
  - :func:`build_impurity_candidates` — flattened impurity list across all peaks.
  - :func:`build_labile_hydrogen_summary` — narrative + observed-candidate list.
    The summary declares the EXACT labile subset present in the SMILES (OH only
    / OH+NH / OH+NH+SH / …) rather than the generic "OH/NH/SH" placeholder.
  - :func:`build_predicted_vs_observed` — greedy match against
    :func:`predict_nmr_from_smiles`.

All public functions accept and return plain dicts/lists so the analyze
endpoint can stay schema-stable (the response model uses
``list[dict[str, Any]]`` for peaks).

**Chemical-shift window references** (cited by both the per-peak categoriser
and the proton-inventory aggregator; lookup keys live in
``literature_data.REFERENCES``):

- ``silverstein_2014_8e`` — Silverstein, Webster, Kiemle & Bryce.
  *Spectrometric Identification of Organic Compounds*, 8e. Wiley (2014).
  Table 4.10 (1H shift correlations) and Table 5.3 (13C shift correlations).
- ``pretsch_2020_tables_5e`` — Pretsch, Bühlmann & Badertscher. *Structure
  Determination of Organic Compounds: Tables of Spectral Data*, 5e.
  Springer (2020). Section H (proton chemical shifts) and Section C
  (carbon-13 chemical shifts).
- ``friebolin_2010_5e`` — Friebolin. *Basic One- and Two-Dimensional NMR
  Spectroscopy*, 5e. Wiley-VCH (2010). Ch. 2 (1H), Ch. 3 (13C).
- ``gottlieb_1997_solvent_impurities`` / ``fulmer_2010_solvent_impurities`` —
  residual-solvent + water windows used by the solvent-hit matcher.
- ``reich_nmr_resources`` — Reich (UW-Madison) NMR resources, the standard
  open reference for OH/NH/SH proton behaviour, exchange broadening, and
  D2O-shake interpretation.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal, Sequence

from .dp4_scoring import pair_residual_dp4_score
from .impurities import match_c13_impurity_shifts, match_h1_impurity_shifts
from .literature_data import (
    TOL_13C_ACCEPTABLE_PPM,
    TOL_13C_STRICT_PPM,
    TOL_1H_ACCEPTABLE_PPM,
    TOL_1H_STRICT_PPM,
    predictor_rmse,
)
from .exceptions import PeakParseError
from .models import Peak, PredictedNMRPeak, StructureSummary
from .nmr_tables import (
    Nucleus,
    classify_carbon13_region,
    classify_proton_region,
    find_solvent_or_impurity_hits,
)
from .parser import ReferencePeakAssignment, parse_reference_nmr_text
from .solvents import find_solvent_peak_hit_indices

# Public peak categories. Keep the set small and visualisable; resist adding
# every flavour of chemical region — those live in ``chemical_region`` instead.
#
# Note on ``anomeric`` / ``olefinic`` / ``anomeric_or_olefinic``: the 4.4–6.0
# ppm 1H window covers both anomeric sugar protons and vinyl / olefinic CH.
# The categoriser uses the SMILES (when supplied) to pick the right label —
# tobramycin-style carbohydrates resolve to ``anomeric``, styrene-style
# vinyl groups resolve to ``olefinic``, and molecules carrying both motifs
# fall back to ``anomeric_or_olefinic``. When no SMILES is supplied we also
# use ``anomeric_or_olefinic`` rather than biasing toward either label.
PEAK_CATEGORIES = (
    "aromatic_alkene",
    "aliphatic",
    "labile_OH_NH_SH",
    "aldehyde",
    "carboxylic_acid",
    "anomeric",
    "carbohydrate_sugar",
    "anomeric_or_olefinic",
    "carbonyl",
    "oxygenated",
    "nitrogen_adjacent",
    "olefinic",
    "solvent",
    "impurity",
    "unknown",
)

AMINOGLYCOSIDE_SUGAR_LOW_PPM = 2.90
AMINOGLYCOSIDE_SUGAR_HIGH_PPM = 5.30
AMINOGLYCOSIDE_ANOMERIC_LOW_PPM = 4.40
AMINOGLYCOSIDE_ANOMERIC_HIGH_PPM = 5.55


def _formula_element_count(formula: str | None, element: str) -> int:
    if not formula:
        return 0
    match = re.search(rf"{re.escape(element)}(?![a-z])(\d*)", formula)
    if not match:
        return 0
    value = match.group(1)
    return int(value) if value else 1


def _is_carbohydrate_like_structure(structure: StructureSummary | None) -> bool:
    if structure is None:
        return False
    oxygen_count = _formula_element_count(getattr(structure, "formula", None), "O")
    anomeric_h = int(getattr(structure, "anomeric_proton_count", 0) or 0)
    olefinic_h = int(getattr(structure, "olefinic_proton_count", 0) or 0)
    aromatic_atoms = int(getattr(structure, "aromatic_atom_count", 0) or 0)
    return oxygen_count >= 4 and anomeric_h > 0 and olefinic_h == 0 and aromatic_atoms == 0


def is_aminoglycoside_like_structure(structure: StructureSummary | None) -> bool:
    """Return True for amino-sugar / aminoglycoside-like carbohydrate inputs.

    The structural test is deliberately conservative: anomeric/acetal protons,
    no olefinic protons, no aromatic atoms, oxygen-rich formula, and at least
    one nitrogen atom. This captures tobramycin-style pseudo-trisaccharides
    without changing ordinary aliphatic, aromatic, or alkene-containing cases.
    """
    if not _is_carbohydrate_like_structure(structure):
        return False
    nitrogen_count = _formula_element_count(getattr(structure, "formula", None), "N")
    return nitrogen_count >= 1


def _expected_anomeric_signal_count(structure: StructureSummary | None) -> int:
    if structure is None:
        return 0
    anomeric_h = int(getattr(structure, "anomeric_proton_count", 0) or 0)
    olefinic_h = int(getattr(structure, "olefinic_proton_count", 0) or 0)
    if is_aminoglycoside_like_structure(structure):
        # Tobramycin-class 4,6-disubstituted 2-deoxystreptamine compounds carry
        # two sugar anomeric signals in the 1H spectrum; remaining sugar-ring
        # CH/CH2 resonances belong to the oxygenated/nitrogenated backbone.
        return min(2, anomeric_h) if anomeric_h > 0 else 0
    return max(0, anomeric_h) + max(0, olefinic_h)


def _is_analyte_proton_category(category: str | None) -> bool:
    return category not in {"solvent", "impurity", "labile_OH_NH_SH", "aldehyde", "carboxylic_acid"}


def _peak_inventory_integration_value(peak: dict[str, Any]) -> float | None:
    for key in ("inventory_integration_h", "reference_integration_h", "integration_h"):
        value = peak.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _score_anomeric_candidate(peak: dict[str, Any]) -> float:
    shift = peak.get("shift_ppm")
    if not isinstance(shift, (int, float)):
        return -1.0
    shift_value = float(shift)
    score = 0.0
    if AMINOGLYCOSIDE_ANOMERIC_LOW_PPM <= shift_value <= AMINOGLYCOSIDE_ANOMERIC_HIGH_PPM:
        score += 4.0
    # In aminoglycoside 1H text, the two anomeric resonances are usually
    # discrete ~1H assignments, commonly doublet-like. Prefer text-backed
    # one-proton candidates, but keep spectrum-only fallbacks available.
    integration = _peak_inventory_integration_value(peak)
    if integration is not None:
        score += max(0.0, 2.0 - min(abs(integration - 1.0), 2.0))
    multiplicity = str(peak.get("multiplicity") or "").strip().lower()
    if multiplicity in {"d", "dd", "ddd", "br d"}:
        score += 0.75
    source = str(peak.get("pick_source") or "")
    if "nmr_text" in source:
        score += 0.75
    # Prefer the downfield edge of the anomeric band when all else is equal;
    # oxygenated H2-H6 sugar-ring protons then remain in the backbone bucket.
    score += max(0.0, shift_value - AMINOGLYCOSIDE_ANOMERIC_LOW_PPM) * 0.02
    return score


def _with_appended_reason(peak: dict[str, Any], reason: str) -> dict[str, Any]:
    updated = dict(peak)
    existing = str(updated.get("category_reason") or "").strip()
    updated["category_reason"] = f"{existing} {reason}".strip() if existing else reason
    return updated


def _refine_carbohydrate_peak_categories(
    peaks: Sequence[dict[str, Any]],
    structure: StructureSummary | None,
) -> list[dict[str, Any]]:
    if not _is_carbohydrate_like_structure(structure):
        return [dict(peak) for peak in peaks]

    expected_anomeric_count = _expected_anomeric_signal_count(structure)
    candidate_indices: list[int] = []
    for idx, peak in enumerate(peaks):
        shift = peak.get("shift_ppm")
        category = peak.get("category")
        if not isinstance(shift, (int, float)) or not isinstance(category, str):
            continue
        if not _is_analyte_proton_category(category):
            continue
        if AMINOGLYCOSIDE_ANOMERIC_LOW_PPM <= float(shift) <= AMINOGLYCOSIDE_ANOMERIC_HIGH_PPM:
            candidate_indices.append(idx)

    selected_anomeric = set(
        sorted(
            candidate_indices,
            key=lambda idx: _score_anomeric_candidate(peaks[idx]),
            reverse=True,
        )[:expected_anomeric_count]
    )

    refined: list[dict[str, Any]] = []
    aminoglycoside_like = is_aminoglycoside_like_structure(structure)
    for idx, original in enumerate(peaks):
        peak = dict(original)
        shift = peak.get("shift_ppm")
        category = peak.get("category")
        if not isinstance(shift, (int, float)) or not isinstance(category, str):
            refined.append(peak)
            continue
        shift_value = float(shift)
        if not _is_analyte_proton_category(category):
            refined.append(peak)
            continue

        if idx in selected_anomeric:
            peak["category"] = "anomeric"
            reason = (
                "Selected as one of the structure-supported anomeric 1H signals; "
                "the SMILES/formula are carbohydrate-like with no olefinic protons."
            )
            if aminoglycoside_like:
                reason += " Aminoglycoside-like inputs are capped at two anomeric peaks."
            refined.append(_with_appended_reason(peak, reason))
            continue

        if aminoglycoside_like and AMINOGLYCOSIDE_SUGAR_LOW_PPM <= shift_value <= AMINOGLYCOSIDE_SUGAR_HIGH_PPM:
            peak["category"] = "carbohydrate_sugar"
            refined.append(
                _with_appended_reason(
                    peak,
                    "Aminoglycoside sugar-backbone refinement: 2.9-5.3 ppm "
                    "belongs to the pseudo-trisaccharide CH/CH2 envelope unless "
                    "selected as one of the two anomeric signals.",
                )
            )
            continue

        if category in {"anomeric", "anomeric_or_olefinic", "olefinic"} and 4.4 <= shift_value < 6.0:
            peak["category"] = "oxygenated"
            refined.append(
                _with_appended_reason(
                    peak,
                    "Carbohydrate-like structure has no olefinic protons and this "
                    "peak was not selected as an anomeric signal, so it is treated "
                    "as heteroatom-adjacent sugar/protected-carbohydrate CH.",
                )
            )
            continue

        refined.append(peak)
    return refined


def _is_broad_multiplicity(multiplicity: str | None) -> bool:
    if not multiplicity:
        return False
    normalized = multiplicity.strip().lower()
    return normalized.startswith("br") or normalized in {"broad", "br s", "br d"}


def _classify_anomeric_vs_olefinic(
    structure: StructureSummary | None,
) -> tuple[str, str]:
    """Choose between ``anomeric`` / ``olefinic`` / ``anomeric_or_olefinic``
    based on what the SMILES actually contains.

    Decision rule (Silverstein 8e Table 4.10; Pretsch 5e §H.3.2):

    - Structure has olefinic H AND no anomeric H → "olefinic"
    - Structure has anomeric H AND no olefinic H → "anomeric"
    - Structure has both → "anomeric_or_olefinic" (ambiguous without 2D data)
    - No structure / empty SMILES → "anomeric_or_olefinic" (no bias)
    """
    base_reason = "Shift in the 4.4–6 ppm window; this band covers both anomeric sugar protons and non-aromatic vinyl / olefinic CH."
    if structure is None:
        return "anomeric_or_olefinic", base_reason + " No SMILES supplied — cannot disambiguate."
    olefinic_h = int(getattr(structure, "olefinic_proton_count", 0) or 0)
    anomeric_h = int(getattr(structure, "anomeric_proton_count", 0) or 0)
    if anomeric_h > 0 and olefinic_h == 0:
        return (
            "anomeric",
            f"Structure has {anomeric_h} anomeric / acetal proton(s) and no olefinic protons → anomeric assignment.",
        )
    if olefinic_h > 0 and anomeric_h == 0:
        return (
            "olefinic",
            f"Structure has {olefinic_h} olefinic proton(s) and no anomeric protons → olefinic assignment.",
        )
    if anomeric_h == 0 and olefinic_h == 0:
        return (
            "anomeric_or_olefinic",
            base_reason
            + " Structure carries neither olefinic nor anomeric protons — the peak may belong to a heteroatom-adjacent CH that drifts into this band, or to an unmodelled environment.",
        )
    # Both > 0
    return (
        "anomeric_or_olefinic",
        f"Structure has {anomeric_h} anomeric and {olefinic_h} olefinic proton(s); 1D 1H cannot resolve which one this peak belongs to.",
    )


def _proton_category(
    *,
    shift_ppm: float,
    multiplicity: str | None,
    is_solvent: bool,
    is_impurity: bool,
    structure: StructureSummary | None = None,
) -> tuple[str, str]:
    """Return ``(category, reason)`` for a 1H peak. ``solvent`` and ``impurity``
    short-circuit chemical-region classification.

    The 4.4–6.0 ppm window is the only window that uses ``structure`` —
    everywhere else the shift alone determines the category. See
    :func:`_classify_anomeric_vs_olefinic` for the per-SMILES decision rule.
    """
    if is_solvent:
        return "solvent", "Falls inside a known residual-solvent / water window for this solvent."
    if is_impurity:
        return "impurity", "Matches a curated impurity reference shift."
    broad = _is_broad_multiplicity(multiplicity)
    if 10.0 <= shift_ppm <= 13.5:
        if broad:
            return (
                "carboxylic_acid",
                "Broad signal in the 10–13 ppm region — consistent with a hydrogen-bonded COOH.",
            )
        return "carboxylic_acid", "Shift in the 10–13 ppm region typical of carboxylic-acid OH."
    if 9.0 <= shift_ppm < 10.0:
        return "aldehyde", "Shift in the 9–10 ppm region typical of an aldehydic proton."
    if 6.0 <= shift_ppm < 9.0:
        return "aromatic_alkene", "Shift in the 6–9 ppm aromatic/alkene window."
    if 4.4 <= shift_ppm < 6.0:
        return _classify_anomeric_vs_olefinic(structure)
    if 3.0 <= shift_ppm < 4.4:
        return (
            "oxygenated",
            "Shift in the 3–4.4 ppm O/N-bearing or heteroatom-adjacent window.",
        )
    if 2.0 <= shift_ppm < 3.0:
        return (
            "nitrogen_adjacent",
            "Shift in the 2–3 ppm allylic / benzylic / heteroatom-adjacent window.",
        )
    if 0.5 <= shift_ppm < 2.0:
        return "aliphatic", "Shift in the 0.5–2 ppm aliphatic window."
    if -1.0 <= shift_ppm < 0.5:
        return "aliphatic", "Upfield aliphatic / reference region."
    return "unknown", "Shift falls outside the standard 1H region table."


def _carbon_category(
    *,
    shift_ppm: float,
    is_solvent: bool,
    is_impurity: bool,
) -> tuple[str, str]:
    if is_solvent:
        return "solvent", "Falls inside a known residual-solvent carbon window for this solvent."
    if is_impurity:
        return "impurity", "Matches a curated 13C impurity reference shift."
    if 190.0 <= shift_ppm <= 220.0:
        return "carbonyl", "Ketone / aldehyde carbonyl region (190–220 ppm)."
    if 160.0 <= shift_ppm < 190.0:
        return "carbonyl", "Carboxyl / ester / amide / carbonate region (160–190 ppm)."
    if 110.0 <= shift_ppm < 160.0:
        return "aromatic_alkene", "Aromatic / alkene carbon region (110–160 ppm)."
    if 90.0 <= shift_ppm < 110.0:
        return "anomeric", "Anomeric / acetal carbon region (90–110 ppm)."
    if 55.0 <= shift_ppm < 90.0:
        return "oxygenated", "Oxygenated carbon region (55–90 ppm)."
    if 40.0 <= shift_ppm < 70.0:
        return "nitrogen_adjacent", "Nitrogen-bearing carbon region (40–70 ppm)."
    if 0.0 <= shift_ppm < 55.0:
        return "aliphatic", "Aliphatic carbon region (0–55 ppm)."
    if -10.0 <= shift_ppm < 0.0:
        return "aliphatic", "Unusual upfield carbon region."
    return "unknown", "Shift falls outside the standard 13C region table."


def _detect_labile_hint(
    *,
    nucleus: Nucleus,
    shift_ppm: float,
    multiplicity: str | None,
    structure: StructureSummary | None,
) -> tuple[bool, str | None]:
    if nucleus != "1H":
        return False, None
    broad = _is_broad_multiplicity(multiplicity)
    in_labile_window = (
        shift_ppm > 10.0  # COOH
        or (broad and shift_ppm >= 4.0)  # OH/NH/SH typically broad
        or (broad and 0.5 <= shift_ppm <= 3.0)  # SH and tertiary NH
    )
    if not in_labile_window:
        return False, None
    notes: list[str] = []
    if broad:
        notes.append("Broad lineshape is consistent with an exchangeable OH/NH/SH proton.")
    if shift_ppm > 10.0:
        notes.append("Downfield shift > 10 ppm is consistent with a strongly H-bonded OH/NH.")
    if structure is not None and structure.labile_hydrogens > 0:
        notes.append(
            f"Structure carries {structure.labile_hydrogens} labile H atom(s); exchange-driven "
            "broadening or D2O suppression should be expected."
        )
    if not notes:
        return True, "Heuristic match for labile OH/NH/SH window."
    return True, " ".join(notes)


def _impurity_match_for_peak(
    *, nucleus: Nucleus, shift_ppm: float, solvent: str | None
) -> dict[str, Any] | None:
    matcher = match_h1_impurity_shifts if nucleus == "1H" else match_c13_impurity_shifts
    matches = matcher(shift_ppm, solvent, max_matches=1)
    if not matches:
        return None
    best = matches[0]
    return {
        "label": best["label"],
        "expected_ppm": best["expected_ppm"],
        "observed_ppm": best["observed_ppm"],
        "delta_ppm": best["delta_ppm"],
        "solvent": best.get("solvent"),
        "kind": best["kind"],
    }


def _solvent_hit_for_peak(
    *, nucleus: Nucleus, shift_ppm: float, solvent: str | None
) -> dict[str, Any] | None:
    if not solvent:
        return None
    hits = find_solvent_or_impurity_hits(shift_ppm, solvent=solvent, nucleus=nucleus)
    if not hits:
        return None
    primary = hits[0]
    return {
        "label": primary.label,
        "kind": primary.kind,
        "low_ppm": primary.low,
        "high_ppm": primary.high,
    }


def categorize_peak(
    *,
    nucleus: Nucleus,
    shift_ppm: float,
    multiplicity: str | None = None,
    solvent: str | None = None,
    structure: StructureSummary | None = None,
) -> dict[str, Any]:
    """Compute the per-peak enrichment dict.

    The function is pure and does not mutate its inputs. Returns a dict whose
    keys can be merged into a peak record.
    """
    solvent_hit = _solvent_hit_for_peak(nucleus=nucleus, shift_ppm=shift_ppm, solvent=solvent)
    impurity_match = _impurity_match_for_peak(
        nucleus=nucleus, shift_ppm=shift_ppm, solvent=solvent
    )
    is_solvent_hit = bool(solvent_hit and solvent_hit.get("kind") in {"solvent", "water", "residual"})
    is_impurity_hit = bool(impurity_match and impurity_match["kind"] == "impurity")

    if nucleus == "1H":
        chemical_region = classify_proton_region(shift_ppm)
        category, reason = _proton_category(
            shift_ppm=shift_ppm,
            multiplicity=multiplicity,
            is_solvent=is_solvent_hit,
            is_impurity=is_impurity_hit,
            # Threading ``structure`` lets the 4.4–6.0 ppm window pick between
            # anomeric / olefinic / anomeric_or_olefinic from the SMILES
            # rather than blindly returning "olefinic". Other windows ignore
            # the structure argument.
            structure=structure,
        )
    else:
        chemical_region = classify_carbon13_region(shift_ppm)
        category, reason = _carbon_category(
            shift_ppm=shift_ppm,
            is_solvent=is_solvent_hit,
            is_impurity=is_impurity_hit,
        )

    labile_hint, labile_reason = _detect_labile_hint(
        nucleus=nucleus,
        shift_ppm=shift_ppm,
        multiplicity=multiplicity,
        structure=structure,
    )

    if labile_hint and category not in {"solvent", "impurity"}:
        category = "labile_OH_NH_SH"
        if labile_reason:
            reason = labile_reason

    return {
        "category": category,
        "chemical_region": chemical_region,
        "labile_hint": labile_hint,
        "solvent_hit": solvent_hit,
        "impurity_match": impurity_match,
        "category_reason": reason,
    }


def enrich_peaks(
    *,
    peaks: Sequence[dict[str, Any]],
    nucleus: Nucleus,
    solvent: str | None,
    structure: StructureSummary | None = None,
) -> list[dict[str, Any]]:
    """Return new peak dicts with categorization fields merged in.

    Pre-existing keys on each peak dict are preserved; new keys are added.
    """
    enriched: list[dict[str, Any]] = []
    for raw in peaks:
        shift = raw.get("shift_ppm")
        if not isinstance(shift, (int, float)):
            enriched.append(dict(raw))
            continue
        category = categorize_peak(
            nucleus=nucleus,
            shift_ppm=float(shift),
            multiplicity=str(raw.get("multiplicity") or "") or None,
            solvent=solvent,
            structure=structure,
        )
        if (
            nucleus == "1H"
            and raw.get("inventory_basis") == "nmr_text"
            and not raw.get("inventory_exclude")
            and category.get("category") in {"solvent", "impurity"}
        ):
            overlapping_solvent_hit = category.get("solvent_hit")
            overlapping_impurity_match = category.get("impurity_match")
            category = categorize_peak(
                nucleus=nucleus,
                shift_ppm=float(shift),
                multiplicity=str(raw.get("multiplicity") or "") or None,
                solvent=None,
                structure=structure,
            )
            category["overlapping_solvent_hit"] = overlapping_solvent_hit
            category["overlapping_impurity_match"] = overlapping_impurity_match
            category["category_reason"] = (
                f"{category.get('category_reason', '')} Supplied 1H text treats this "
                "assignment as analyte evidence, so overlapping residual-solvent or "
                "impurity-library windows are review flags rather than grounds to "
                "remove it from the proton inventory."
            ).strip()
        enriched.append({**raw, **category})
    if nucleus == "1H":
        return _refine_carbohydrate_peak_categories(enriched, structure)
    return enriched


def _reference_assignment_window(assignment: ReferencePeakAssignment) -> tuple[float, float]:
    if assignment.shift_start_ppm is not None and assignment.shift_end_ppm is not None:
        low = min(float(assignment.shift_start_ppm), float(assignment.shift_end_ppm)) - 0.035
        high = max(float(assignment.shift_start_ppm), float(assignment.shift_end_ppm)) + 0.035
        return (low, high)
    shift = float(assignment.shift_ppm)
    return (shift - 0.07, shift + 0.07)


def _reference_assignment_contains_peak(
    assignment: ReferencePeakAssignment,
    shift_ppm: float,
) -> bool:
    low, high = _reference_assignment_window(assignment)
    return low <= shift_ppm <= high


def _reference_assignment_delta(
    assignment: ReferencePeakAssignment,
    shift_ppm: float,
) -> float:
    if _reference_assignment_contains_peak(assignment, shift_ppm):
        return 0.0
    low, high = _reference_assignment_window(assignment)
    return min(abs(shift_ppm - low), abs(shift_ppm - high), abs(shift_ppm - float(assignment.shift_ppm)))


def _is_reference_solvent_assignment(
    assignment: ReferencePeakAssignment,
    solvent: str | None,
) -> bool:
    # Reference-text ranges often span a residual-solvent coordinate, especially
    # aromatic multiplets around CDCl3 at 7.26 ppm.  Do not exclude those from
    # adjusted observed H: only point-like solvent/water assignments are safe
    # to remove from the text-backed proton inventory.
    if assignment.shift_start_ppm is not None or assignment.shift_end_ppm is not None:
        return False
    if assignment.multiplicity not in {"s", "br", "br s", "broad"}:
        return False
    try:
        return bool(find_solvent_peak_hit_indices([assignment.as_peak()], solvent))
    except Exception:  # noqa: BLE001 - solvent heuristics must not block reconciliation
        return False


def _reference_shift_payload(assignment: ReferencePeakAssignment) -> dict[str, Any]:
    return {
        "reference_shift_ppm": float(assignment.shift_ppm),
        "reference_shift_start_ppm": assignment.shift_start_ppm,
        "reference_shift_end_ppm": assignment.shift_end_ppm,
        "reference_raw_text": assignment.raw_text,
    }


def _assignment_peak_dict(
    assignment: ReferencePeakAssignment,
    *,
    spectrum_confirmed: bool,
    linked_spectrum_shift_ppm: float | None,
    used_for_inventory: bool,
    solvent_excluded: bool,
    source: str,
) -> dict[str, Any]:
    peak = assignment.as_peak()
    return {
        "shift_ppm": float(peak.shift_ppm),
        "multiplicity": peak.multiplicity,
        "integration_h": float(peak.integration_h),
        "j_values_hz": list(peak.j_values_hz),
        **_reference_shift_payload(assignment),
        "reference_integration_h": float(assignment.integration_h),
        "inventory_integration_h": 0.0 if solvent_excluded else float(assignment.integration_h),
        "integration_source": "nmr_text",
        "inventory_basis": "nmr_text",
        "pick_source": source,
        "spectrum_confirmed": spectrum_confirmed,
        "linked_spectrum_shift_ppm": linked_spectrum_shift_ppm,
        "inventory_exclude": not used_for_inventory,
        "inventory_exclude_reason": (
            "reference solvent/water assignment excluded from adjusted observed H"
            if solvent_excluded
            else None
        ),
    }


def reconcile_proton_peaks_with_reference_text(
    *,
    peaks: Sequence[dict[str, Any]],
    reference_nmr_text: str | None,
    solvent: str | None,
    structure: StructureSummary | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Align picked 1H peaks with the authoritative parsed 1H text.

    This is deliberately evidence-based, not predictive: parsed NMR text is
    treated as observed analytical evidence, while the spectrum trace is used
    to mark whether each assignment was independently picked. The resulting
    list preserves all original spectrum peaks, but proton-inventory
    integration switches to the text-backed values when text is available.
    """
    source_peaks = [dict(peak) for peak in peaks]
    if not reference_nmr_text or not reference_nmr_text.strip():
        return source_peaks, {"applied": False, "reason": "no_reference_nmr_text"}

    try:
        normalized_text, assignments = parse_reference_nmr_text(reference_nmr_text)
    except PeakParseError as exc:
        return source_peaks, {
            "applied": False,
            "reason": "reference_parse_failed",
            "error": str(exc),
        }

    if not assignments:
        return source_peaks, {"applied": False, "reason": "reference_had_no_assignments"}

    indexed_spectrum: list[tuple[int, float, dict[str, Any]]] = []
    for idx, peak in enumerate(source_peaks):
        shift = peak.get("shift_ppm")
        if isinstance(shift, (int, float)):
            indexed_spectrum.append((idx, float(shift), peak))

    used_spectrum_indices: set[int] = set()
    reconciled: list[dict[str, Any]] = []
    matched_reference_count = 0
    spectrum_confirmed_reference_count = 0
    added_reference_count = 0
    solvent_reference_count = 0
    reference_total_h = 0.0
    adjusted_reference_total_h = 0.0

    for assignment in assignments:
        reference_total_h += float(assignment.integration_h)
        solvent_excluded = _is_reference_solvent_assignment(assignment, solvent)
        if solvent_excluded:
            solvent_reference_count += 1
        else:
            adjusted_reference_total_h += float(assignment.integration_h)

        best_unused: tuple[int, float, dict[str, Any], float] | None = None
        best_any: tuple[int, float, dict[str, Any], float] | None = None
        for idx, shift, spectrum_peak in indexed_spectrum:
            if not _reference_assignment_contains_peak(assignment, shift):
                continue
            delta = _reference_assignment_delta(assignment, shift)
            candidate = (idx, shift, spectrum_peak, delta)
            if best_any is None or delta < best_any[3]:
                best_any = candidate
            if idx not in used_spectrum_indices and (best_unused is None or delta < best_unused[3]):
                best_unused = candidate

        if best_unused is not None:
            idx, shift, spectrum_peak, delta = best_unused
            used_spectrum_indices.add(idx)
            matched_reference_count += 1
            spectrum_confirmed_reference_count += 1
            original_integration = spectrum_peak.get("integration_h")
            updated = {
                **spectrum_peak,
                **_reference_shift_payload(assignment),
                "shift_ppm": shift,
                "multiplicity": assignment.multiplicity or spectrum_peak.get("multiplicity"),
                "j_values_hz": list(assignment.j_values_hz),
                "spectrum_integration_h": original_integration,
                "integration_h": float(assignment.integration_h),
                "reference_integration_h": float(assignment.integration_h),
                "inventory_integration_h": 0.0 if solvent_excluded else float(assignment.integration_h),
                "integration_source": "nmr_text",
                "inventory_basis": "nmr_text",
                "pick_source": "spectrum_and_nmr_text",
                "spectrum_confirmed": True,
                "reference_match_delta_ppm": round(float(delta), 4),
                "inventory_exclude": solvent_excluded,
                "inventory_exclude_reason": (
                    "reference solvent/water assignment excluded from adjusted observed H"
                    if solvent_excluded
                    else spectrum_peak.get("inventory_exclude_reason")
                ),
            }
            reconciled.append(updated)
        else:
            matched_reference_count += 1 if best_any is not None else 0
            if best_any is not None:
                spectrum_confirmed_reference_count += 1
            added_reference_count += 1
            linked_shift = best_any[1] if best_any is not None else None
            reconciled.append(
                _assignment_peak_dict(
                    assignment,
                    spectrum_confirmed=best_any is not None,
                    linked_spectrum_shift_ppm=linked_shift,
                    used_for_inventory=not solvent_excluded,
                    solvent_excluded=solvent_excluded,
                    source=(
                        "nmr_text_split_from_overlapped_spectrum_peak"
                        if best_any is not None
                        else "nmr_text_unconfirmed_by_picker"
                    ),
                )
            )

    unmatched_spectrum_count = 0
    for idx, _, spectrum_peak in indexed_spectrum:
        if idx in used_spectrum_indices:
            continue
        unmatched_spectrum_count += 1
        extra = dict(spectrum_peak)
        extra.setdefault("pick_source", "spectrum_only_unmatched_to_nmr_text")
        extra.setdefault("integration_source", "spectrum")
        extra["inventory_exclude"] = True
        extra["inventory_exclude_reason"] = (
            "excluded from proton inventory because supplied 1H text is the integration basis"
        )
        reconciled.append(extra)

    expected_visible_h: float | None = None
    if structure is not None:
        expected_visible_h = (
            float(structure.non_labile_hydrogens)
            if solvent and solvent.upper() == "D2O"
            else float(structure.total_hydrogens)
        )

    metadata = {
        "applied": True,
        "policy": "reference_text_guides_integration; spectrum_only_peaks_preserved_but_excluded_from_proton_inventory",
        "reference_nmr_text_normalized": normalized_text,
        "reference_peak_count": len(assignments),
        "spectrum_peak_count_before": len(source_peaks),
        "peak_count_after_reconciliation": len(reconciled),
        "matched_reference_peak_count": matched_reference_count,
        "spectrum_confirmed_reference_peak_count": spectrum_confirmed_reference_count,
        "added_reference_peak_count": added_reference_count,
        "unmatched_spectrum_peak_count": unmatched_spectrum_count,
        "reference_solvent_peak_count": solvent_reference_count,
        "observed_total_h": round(reference_total_h, 4),
        "adjusted_observed_total_h": round(adjusted_reference_total_h, 4),
        "expected_visible_h": expected_visible_h,
        "delta_adjusted_observed_vs_expected_h": (
            round(adjusted_reference_total_h - expected_visible_h, 4)
            if expected_visible_h is not None
            else None
        ),
    }
    return reconciled, metadata


def build_peak_category_summary(peaks: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for peak in peaks:
        category = peak.get("category")
        if not isinstance(category, str) or not category:
            continue
        summary[category] = summary.get(category, 0) + 1
    return summary


# Categories that contribute to each observed-proton bucket. Sourced from the
# 1H region table consensus across Silverstein 8e (Table 4.10), Pretsch 5e
# (§H.5), Friebolin 5e (Ch. 2), and the live shift-window assignments in
# ``_proton_category`` above. Listed here as a single readable map so a
# reviewer can audit which peak categories roll up into which inventory bucket.
_AROMATIC_CATEGORIES: frozenset[str] = frozenset({"aromatic_alkene"})
# 4.4–6.0 ppm bucket: covers anomeric protons (sugars), olefinic / vinyl CH,
# AND the ambiguous case where the categoriser couldn't disambiguate.
_ANOMERIC_OR_OLEFINIC_CATEGORIES: frozenset[str] = frozenset(
    {"olefinic", "anomeric", "anomeric_or_olefinic"}
)
_ALDEHYDE_CATEGORIES: frozenset[str] = frozenset({"aldehyde"})
_CARBOXYL_CATEGORIES: frozenset[str] = frozenset({"carboxylic_acid"})
_LABILE_CATEGORIES: frozenset[str] = frozenset({"labile_OH_NH_SH"})
_CARBOHYDRATE_SUGAR_CATEGORIES: frozenset[str] = frozenset({"carbohydrate_sugar"})
_ALIPHATIC_CATEGORIES: frozenset[str] = frozenset(
    {"aliphatic", "oxygenated", "nitrogen_adjacent", "carbohydrate_sugar"}
)


def _inventory_integration(peak: dict[str, Any]) -> float | None:
    if peak.get("inventory_exclude"):
        return None
    integration = peak.get("inventory_integration_h")
    if not isinstance(integration, (int, float)):
        integration = peak.get("integration_h")
    if not isinstance(integration, (int, float)):
        return None
    return float(integration)


def _sum_integration(peaks: Iterable[dict[str, Any]], categories: frozenset[str]) -> float:
    total = 0.0
    for peak in peaks:
        category = peak.get("category")
        if not isinstance(category, str) or category not in categories:
            continue
        integration = _inventory_integration(peak)
        if integration is None:
            continue
        total += integration
    return total


def build_proton_inventory(
    *,
    peaks: Sequence[dict[str, Any]],
    structure: StructureSummary | None,
    nucleus: Nucleus,
) -> dict[str, Any]:
    """Aggregate observed + expected proton counts by chemical class.

    Returned dict shape (all numeric fields rounded to one decimal place where
    they are float-typed integrations):

      observed:
        aromatic, anomeric_or_olefinic, carbohydrate_sugar, aldehyde,
        carboxylic_acid, labile, aliphatic, total, non_labile
      expected (only populated when ``structure`` is supplied):
        aromatic, anomeric_or_olefinic, aliphatic, labile, non_labile,
        total, oh, nh, sh, labile_subset
      deltas (observed − expected; only populated when expected is non-empty):
        aromatic, anomeric_or_olefinic, aliphatic, labile, non_labile, total
      warnings: list[str] — qualitative deviations worth surfacing.

    Returns an empty dict for non-proton nuclei so the caller can attach it
    unconditionally without bloating 13C-only responses.

    Region bucketing follows the 1H chemical-shift consensus tables in:

    - Silverstein, Webster, Kiemle. *Spectrometric Identification of Organic
      Compounds*, 8th ed. Wiley, 2014. Table 4.10.
    - Pretsch, Bühlmann, Badertscher. *Structure Determination of Organic
      Compounds: Tables of Spectral Data*, 5th ed. Springer, 2020. Section H.5.
    - Friebolin. *Basic One- and Two-Dimensional NMR Spectroscopy*, 5th ed.
      Wiley-VCH, 2010. Chapter 2.
    - Gottlieb, Kotlyar, Nudelman. *NMR Chemical Shifts of Common Laboratory
      Solvents as Trace Impurities*, J. Org. Chem. 1997, 62, 7512 — used by
      the solvent / residual-water windows.
    """
    if nucleus != "1H":
        return {}

    observed_aromatic = _sum_integration(peaks, _AROMATIC_CATEGORIES)
    observed_anomeric_olefinic = _sum_integration(peaks, _ANOMERIC_OR_OLEFINIC_CATEGORIES)
    observed_aldehyde = _sum_integration(peaks, _ALDEHYDE_CATEGORIES)
    observed_carboxyl = _sum_integration(peaks, _CARBOXYL_CATEGORIES)
    observed_carbohydrate_sugar = _sum_integration(peaks, _CARBOHYDRATE_SUGAR_CATEGORIES)
    observed_labile = (
        _sum_integration(peaks, _LABILE_CATEGORIES) + observed_carboxyl
    )  # COOH is labile too
    observed_aliphatic = _sum_integration(peaks, _ALIPHATIC_CATEGORIES)
    observed_total = sum(
        float(integration)
        for peak in peaks
        if peak.get("category") not in {"solvent", "impurity"}
        for integration in [_inventory_integration(peak)]
        if integration is not None
    )
    observed_non_labile = max(observed_total - observed_labile, 0.0)

    def _round(value: float) -> float:
        return round(value, 1)

    observed_block: dict[str, float] = {
        "aromatic": _round(observed_aromatic),
        # 4.4–6 ppm bucket: anomeric (sugar) + olefinic (vinyl) + ambiguous.
        # Old name was ``olefinic_vinylic`` — renamed because aminoglycosides
        # (e.g. tobramycin) have anomeric protons here but no olefinic ones,
        # and the original name was misleading.
        "anomeric_or_olefinic": _round(observed_anomeric_olefinic),
        "carbohydrate_sugar": _round(observed_carbohydrate_sugar),
        "aldehyde": _round(observed_aldehyde),
        "carboxylic_acid": _round(observed_carboxyl),
        "labile": _round(observed_labile),
        "aliphatic": _round(observed_aliphatic),
        "non_labile": _round(observed_non_labile),
        "total": _round(observed_total),
    }

    expected_block: dict[str, Any] = {}
    deltas: dict[str, float] = {}
    warnings: list[str] = []
    if structure is not None:
        expected_block = {
            "aromatic": int(structure.aromatic_protons),
            "anomeric_or_olefinic": _expected_anomeric_signal_count(structure),
            "aliphatic": int(structure.aliphatic_protons),
            "labile": int(structure.labile_hydrogens),
            "non_labile": int(structure.non_labile_hydrogens),
            "total": int(structure.total_hydrogens),
            "oh": int(structure.oh_hydrogen_count),
            "nh": int(structure.nh_hydrogen_count),
            "sh": int(structure.sh_hydrogen_count),
            "labile_subset": _labile_subset_label(
                oh=int(structure.oh_hydrogen_count),
                nh=int(structure.nh_hydrogen_count),
                sh=int(structure.sh_hydrogen_count),
            ),
        }
        deltas = {
            "aromatic": _round(observed_aromatic - expected_block["aromatic"]),
            "anomeric_or_olefinic": _round(
                observed_anomeric_olefinic - expected_block["anomeric_or_olefinic"]
            ),
            "aliphatic": _round(observed_aliphatic - expected_block["aliphatic"]),
            "labile": _round(observed_labile - expected_block["labile"]),
            "non_labile": _round(observed_non_labile - expected_block["non_labile"]),
            "total": _round(observed_total - expected_block["total"]),
        }
        # Threshold for "meaningfully different from expectation".
        # 0.5 H accommodates legitimate integration rounding; > 1 H is flagged.
        for key, delta in deltas.items():
            if abs(delta) >= 1.0:
                if delta > 0:
                    warnings.append(
                        f"Observed {key} integration is {delta:+.1f} H above the structural "
                        f"expectation ({expected_block[key]} H) — likely overlap, impurity, "
                        "or unresolved multiplet."
                    )
                else:
                    warnings.append(
                        f"Observed {key} integration is {delta:+.1f} H below the structural "
                        f"expectation ({expected_block[key]} H) — possible exchange, suppression, "
                        "or truncation."
                    )

    integration_basis = (
        "nmr_text_guided"
        if any(str(peak.get("inventory_basis") or "") == "nmr_text" for peak in peaks)
        else "spectrum"
    )

    return {
        "nucleus": "1H",
        "integration_basis": integration_basis,
        "observed": observed_block,
        "expected": expected_block,
        "deltas": deltas,
        "warnings": warnings,
    }


def build_impurity_candidates(
    *,
    peaks: Iterable[dict[str, Any]],
    metadata_candidates: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Flatten impurity matches from enriched peaks. If the spectrum parser
    already attached richer ``impurity_candidates`` to metadata, those win and
    are simply normalised.
    """
    if metadata_candidates:
        normalized: list[dict[str, Any]] = []
        for record in metadata_candidates:
            if not isinstance(record, dict):
                continue
            normalized.append({
                "shift_ppm": record.get("shift_ppm"),
                "integration_h": record.get("integration_h"),
                "reason": record.get("reason"),
                "score": record.get("score"),
                "library_match": record.get("library_match"),
            })
        return normalized

    results: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for peak in peaks:
        match = peak.get("impurity_match")
        if not isinstance(match, dict):
            continue
        key = (peak.get("shift_ppm"), match.get("label"))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "shift_ppm": peak.get("shift_ppm"),
                "integration_h": peak.get("integration_h"),
                "reason": (
                    f"matches embedded impurity shift for {match.get('label')} "
                    f"({match.get('expected_ppm')} ppm)"
                ),
                "score": None,
                "library_match": match,
            }
        )
    return results


def _labile_subset_label(*, oh: int, nh: int, sh: int) -> str:
    """Return the exact labile-element subset string, e.g. ``"OH"``,
    ``"OH/NH"``, ``"OH/NH/SH"``. Returns an empty string when none are present.

    Ordering is fixed (OH > NH > SH) so the label is stable across calls and
    matches the convention used in NMR teaching tables
    (Silverstein, Spectrometric Identification of Organic Compounds, 8e, Table 4.10;
    Pretsch, Structure Determination of Organic Compounds, 5e, §H.5).
    """
    parts: list[str] = []
    if oh > 0:
        parts.append("OH")
    if nh > 0:
        parts.append("NH")
    if sh > 0:
        parts.append("SH")
    return "/".join(parts)


def build_labile_hydrogen_summary(
    *,
    peaks: Iterable[dict[str, Any]],
    structure: StructureSummary | None,
    solvent: str | None,
) -> dict[str, Any]:
    """Summarise exchangeable-proton evidence for the UI.

    The summary now declares the EXACT labile subset present in the SMILES
    (OH only / OH+NH / OH+NH+SH / …) rather than the generic "OH/NH/SH". The
    per-element expected counts also ride along on the returned dict so the
    UI / downstream confidence-scoring layers can reason about them.

    Chemical-shift windows informing the labile-hint detection are sourced
    from Silverstein 8e (Table 4.10) and Friebolin 5e (Ch. 2), summarised in
    ``literature_data.py::SHIFT_WINDOW_REFERENCES``.
    """
    observed: list[dict[str, Any]] = []
    for peak in peaks:
        if peak.get("labile_hint"):
            observed.append(
                {
                    "shift_ppm": peak.get("shift_ppm"),
                    "multiplicity": peak.get("multiplicity"),
                    "integration_h": peak.get("integration_h"),
                    "reason": peak.get("category_reason"),
                }
            )

    expected_labile = int(structure.labile_hydrogens) if structure else 0
    expected_oh = int(structure.oh_hydrogen_count) if structure else 0
    expected_nh = int(structure.nh_hydrogen_count) if structure else 0
    expected_sh = int(structure.sh_hydrogen_count) if structure else 0
    subset_label = _labile_subset_label(oh=expected_oh, nh=expected_nh, sh=expected_sh)

    notes: list[str] = []
    if expected_labile and subset_label:
        breakdown_bits: list[str] = []
        if expected_oh:
            breakdown_bits.append(f"{expected_oh} OH")
        if expected_nh:
            breakdown_bits.append(f"{expected_nh} NH")
        if expected_sh:
            breakdown_bits.append(f"{expected_sh} SH")
        breakdown = ", ".join(breakdown_bits)
        notes.append(
            f"Structure declares {expected_labile} labile H atom(s) ({subset_label}): {breakdown}."
        )
    elif expected_labile:
        # Edge case: labile total > 0 but no per-element data (e.g. legacy
        # StructureSummary deserialised without the new fields).
        notes.append(
            f"Structure declares {expected_labile} labile H atom(s); per-element subset unavailable."
        )

    if observed:
        notes.append(
            f"Detected {len(observed)} peak(s) consistent with exchangeable protons."
        )
    if solvent and solvent.strip().upper() == "D2O" and expected_labile:
        # Match the actual subset rather than the generic "OH/NH/SH" message.
        exchange_subject = subset_label if subset_label else "OH/NH/SH"
        notes.append(
            f"D2O solvent will exchange {exchange_subject} signals; missing labile peaks are expected."
        )
    if not observed and expected_labile and not (solvent and solvent.upper() == "D2O"):
        missing_subject = subset_label if subset_label else "OH/NH/SH"
        notes.append(
            f"No broad labile-region peaks detected; consider whether {missing_subject} integrations were truncated."
        )

    matched = min(len(observed), expected_labile) if expected_labile else 0
    confidence: float | None = None
    if expected_labile:
        confidence = round(min(1.0, matched / max(1, expected_labile)), 4)

    return {
        "expected_labile_h": expected_labile,
        # Per-element breakdown and the human-readable subset label used in
        # notes. Empty string when no labile protons are present (or no SMILES).
        "expected_oh_h": expected_oh,
        "expected_nh_h": expected_nh,
        "expected_sh_h": expected_sh,
        "labile_subset": subset_label,
        "observed_labile_candidates": observed,
        "notes": notes,
        "confidence": confidence,
    }


def build_predicted_vs_observed(
    *,
    predicted_peaks: Sequence[PredictedNMRPeak],
    observed_peaks: Sequence[dict[str, Any]],
    nucleus: Nucleus,
    tolerance_ppm: float | None = None,
) -> list[dict[str, Any]]:
    """Greedy nearest-shift matching between predicted and observed peaks.

    Each result row carries ``predicted_ppm``, ``observed_ppm``, ``delta_ppm``,
    ``status`` (``matched`` / ``unmatched_predicted`` / ``unmatched_observed``),
    plus three literature-grounded confidence fields:

    - ``z_dp4`` — signed (predicted − observed) / σ_DP4 [Smith & Goodman 2010].
    - ``tail_probability`` — 1 − T_ν(|z_dp4|) (higher = better fit).
    - ``confidence`` — categorical bucket grounded in the
      Computational-NMR-survey "acceptable" deviation thresholds
      (≤0.3 ppm 1H, ≤6 ppm 13C) and the strict DP4 σ.

    The default tolerance is set from
    :mod:`nmrcheck.literature_data` (``TOL_1H_ACCEPTABLE_PPM`` for 1H and
    ``TOL_13C_ACCEPTABLE_PPM`` for 13C). Pass ``tolerance_ppm`` to override.
    """
    if tolerance_ppm is None:
        tolerance_ppm = (
            TOL_1H_ACCEPTABLE_PPM if nucleus == "1H" else TOL_13C_ACCEPTABLE_PPM
        )
    strict_tolerance = TOL_1H_STRICT_PPM if nucleus == "1H" else TOL_13C_STRICT_PPM
    rmse_ref = predictor_rmse(nucleus)

    def _confidence_bucket(delta: float) -> str:
        abs_delta = abs(delta)
        if abs_delta <= strict_tolerance:
            return "high"
        if abs_delta <= tolerance_ppm:
            return "medium"
        return "low"

    predicted_for_nucleus = [p for p in predicted_peaks if p.nucleus == nucleus]
    observed_with_index: list[tuple[int, float, dict[str, Any]]] = []
    for idx, peak in enumerate(observed_peaks):
        shift = peak.get("shift_ppm")
        if isinstance(shift, (int, float)):
            observed_with_index.append((idx, float(shift), peak))

    used_observed: set[int] = set()
    rows: list[dict[str, Any]] = []

    for predicted in predicted_for_nucleus:
        best_idx: int | None = None
        best_delta: float | None = None
        for idx, observed_shift, _ in observed_with_index:
            if idx in used_observed:
                continue
            delta = abs(observed_shift - float(predicted.shift_ppm))
            if delta > tolerance_ppm:
                continue
            if best_delta is None or delta < best_delta:
                best_idx = idx
                best_delta = delta
        if best_idx is not None and best_delta is not None:
            used_observed.add(best_idx)
            observed_peak = next(
                peak for idx, _, peak in observed_with_index if idx == best_idx
            )
            observed_value = float(observed_peak.get("shift_ppm"))
            dp4 = pair_residual_dp4_score(
                observed_ppm=observed_value,
                predicted_ppm=float(predicted.shift_ppm),
                nucleus=nucleus,
            )
            rows.append(
                {
                    "status": "matched",
                    "predicted_ppm": float(predicted.shift_ppm),
                    "observed_ppm": observed_value,
                    "delta_ppm": round(best_delta, 4),
                    "predicted_atom_index": predicted.atom_index,
                    "predicted_attached_h": predicted.attached_h,
                    "predicted_environment": predicted.environment,
                    "predicted_uncertainty_ppm": float(predicted.uncertainty_ppm),
                    "observed_multiplicity": observed_peak.get("multiplicity"),
                    "observed_integration_h": observed_peak.get("integration_h"),
                    "category": observed_peak.get("category"),
                    # Literature-grounded confidence fields:
                    "z_dp4": dp4["z_dp4"],
                    "tail_probability": dp4["tail_probability"],
                    "confidence": _confidence_bucket(best_delta),
                    "predictor_rmse_ref_ppm": rmse_ref,
                }
            )
        else:
            rows.append(
                {
                    "status": "unmatched_predicted",
                    "predicted_ppm": float(predicted.shift_ppm),
                    "observed_ppm": None,
                    "delta_ppm": None,
                    "predicted_atom_index": predicted.atom_index,
                    "predicted_attached_h": predicted.attached_h,
                    "predicted_environment": predicted.environment,
                    "predicted_uncertainty_ppm": float(predicted.uncertainty_ppm),
                    "observed_multiplicity": None,
                    "observed_integration_h": None,
                    "category": None,
                }
            )

    for idx, _, peak in observed_with_index:
        if idx in used_observed:
            continue
        rows.append(
            {
                "status": "unmatched_observed",
                "predicted_ppm": None,
                "observed_ppm": float(peak.get("shift_ppm")),
                "delta_ppm": None,
                "predicted_atom_index": None,
                "predicted_attached_h": None,
                "predicted_environment": None,
                "predicted_uncertainty_ppm": None,
                "observed_multiplicity": peak.get("multiplicity"),
                "observed_integration_h": peak.get("integration_h"),
                "category": peak.get("category"),
            }
        )

    # Sort by observed_ppm desc when present, else by predicted_ppm desc.
    def _sort_key(row: dict[str, Any]) -> float:
        for key in ("observed_ppm", "predicted_ppm"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                return -float(value)
        return 0.0

    rows.sort(key=_sort_key)
    return rows


def build_dp4_candidate_ranking(
    *,
    observed_peaks: Sequence[dict[str, Any]],
    candidate_predicted: Sequence[Sequence[PredictedNMRPeak]],
    candidate_labels: Sequence[str],
    nucleus: Nucleus,
) -> list[dict[str, Any]]:
    """Run DP4 across a list of candidates and return a ranked, JSON-ready list.

    Uses the published Smith & Goodman 2010 σ / ν (1H σ=0.185 ν=14.18;
    13C σ=2.306 ν=11.38). Each row carries the candidate label, the DP4
    posterior probability, the candidate's MAE and RMSE vs the observed shifts,
    and the linear-scaling slope/intercept the fit produced.

    Returned list is sorted by descending probability.
    """
    from .dp4_scoring import dp4_probabilities  # local import to avoid cycle in tests

    observed_shifts = [
        float(peak.get("shift_ppm"))
        for peak in observed_peaks
        if isinstance(peak.get("shift_ppm"), (int, float))
    ]
    candidate_shifts = [
        [float(p.shift_ppm) for p in peaks if p.nucleus == nucleus]
        for peaks in candidate_predicted
    ]
    if not observed_shifts or not any(candidate_shifts):
        return []
    scores = dp4_probabilities(
        observed_shifts_ppm=observed_shifts,
        candidate_predicted_shifts_ppm=candidate_shifts,
        nucleus=nucleus,
    )
    rows = []
    for score in scores:
        label = (
            candidate_labels[score.candidate_index]
            if 0 <= score.candidate_index < len(candidate_labels)
            else f"candidate_{score.candidate_index}"
        )
        rows.append(
            {
                "candidate_index": score.candidate_index,
                "candidate_label": label,
                "dp4_probability": score.probability,
                "matched_peaks": score.matched_peaks,
                "mean_abs_error_ppm": score.mean_abs_error_ppm,
                "rms_error_ppm": score.rms_error_ppm,
                "scaling_slope": score.slope,
                "scaling_intercept": score.intercept,
                "notes": list(score.notes),
            }
        )
    rows.sort(key=lambda r: r["dp4_probability"], reverse=True)
    return rows


__all__ = [
    "PEAK_CATEGORIES",
    "build_dp4_candidate_ranking",
    "build_impurity_candidates",
    "build_labile_hydrogen_summary",
    "build_peak_category_summary",
    "build_predicted_vs_observed",
    "categorize_peak",
    "enrich_peaks",
]
