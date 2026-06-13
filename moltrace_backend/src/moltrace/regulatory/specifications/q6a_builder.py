"""ICH Q6A Specification Builder (Prompt 6).

Implements the ICH Q6A decision trees as decision nodes; each tree returns a specification parameter
with a proposed limit + justification + method reference. The quantitative impurity limits are NOT
invented here — they come from the deterministic, validated P1-5 engines: Q3A/B reporting /
identification / qualification thresholds (:func:`calculate_q3ab_thresholds`) and ICH M7 safety
limits for genotoxic / Cohort-of-Concern impurities (:func:`classify_m7`). Decision-support only;
every draft specification requires review + sign-off by a qualified regulatory professional.

Decision trees (ICH Q6A Appendix 1-7) implemented: #1 appearance/description, #2 identification,
assay (manufacturing variation + stability), impurities (Q3A/B + M7 + process capability when
Cpk > 1.33), #3 dissolution (immediate-release), disintegration (in lieu of dissolution for
rapidly-dissolving high-solubility products), and #7 water content.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from moltrace.regulatory.impurities import calculate_q3ab_thresholds, classify_cpca, classify_m7

__all__ = [
    "BatchResult",
    "ImpurityObservation",
    "MethodValidation",
    "Specification",
    "SpecificationParameter",
    "SubstanceProfile",
    "build_specification",
    "process_capability_cpk",
]

_CPK_CAPABLE = 1.33  # ICH/Six-Sigma process-capability threshold for a tightened limit
_GENOTOXIC_CLASSES = frozenset({1, 2, 3})  # ICH M7 classes warranting a safety-based limit


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ImpurityObservation:
    """One impurity to specify: its name, optional structure (for M7), and observed batch levels."""

    name: str
    structural_assignment: str | None = None  # SMILES — enables the ICH M7 genotoxicity check
    batch_levels_percent: tuple[float, ...] = ()
    is_specified: bool = True


@dataclass(frozen=True)
class SubstanceProfile:
    """The substance/product under specification."""

    name: str
    substance_type: str = "drug_substance"  # "drug_substance" | "drug_product"
    dosage_form: str = "active pharmaceutical ingredient"
    route: str = "oral"
    max_daily_dose_g: float = 1.0
    physical_form: str = "crystalline solid"
    colour: str = "white to off-white"
    is_solid_oral: bool = False
    high_solubility: bool = False  # BCS high solubility
    rapidly_dissolving: bool = False  # drives disintegration-in-lieu-of-dissolution
    is_hygroscopic: bool = False
    is_hydrate: bool = False
    impurities: tuple[ImpurityObservation, ...] = ()
    identification_methods: tuple[str, ...] = ("IR spectroscopy", "HPLC retention time")


@dataclass(frozen=True)
class BatchResult:
    """One batch's analytical results (the manufacturing-variation + stability evidence)."""

    batch_id: str
    assay_percent: float | None = None
    dissolution_percent_30min: float | None = None
    water_content_percent: float | None = None
    total_impurities_percent: float | None = None


@dataclass(frozen=True)
class MethodValidation:
    """Which analytical methods are validated (ICH Q2(R2)); gates method selection."""

    validated_methods: frozenset[str] = frozenset()

    def is_validated(self, method: str) -> bool:
        return method in self.validated_methods


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SpecificationParameter:
    """One row of the draft specification table."""

    parameter: str
    proposed_limit: str
    justification: str
    method_reference: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "proposed_limit": self.proposed_limit,
            "justification": self.justification,
            "method_reference": self.method_reference,
        }


@dataclass(frozen=True)
class Specification:
    """The draft specification table for one substance/product."""

    substance_name: str
    dosage_form: str
    parameters: tuple[SpecificationParameter, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def parameter(self, name: str) -> SpecificationParameter | None:
        return next((p for p in self.parameters if p.parameter == name), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "substance_name": self.substance_name,
            "dosage_form": self.dosage_form,
            "parameters": [p.as_dict() for p in self.parameters],
            "metadata": self.metadata,
        }


# --------------------------------------------------------------------------- #
# Process capability
# --------------------------------------------------------------------------- #
def process_capability_cpk(
    values: Sequence[float], *, usl: float, lsl: float = 0.0
) -> float | None:
    """One-/two-sided Cpk for a measured parameter. ``None`` when < 2 batches.

    Cpk = min((USL - mean) / 3σ, (mean - LSL) / 3σ). A capable process (Cpk > 1.33) justifies a
    tighter, data-driven limit than the guideline ceiling.
    """

    vals = [float(v) for v in values]
    if len(vals) < 2:
        return None
    mean = statistics.fmean(vals)
    sd = statistics.stdev(vals)
    if sd == 0.0:
        return float("inf")
    return min((usl - mean) / (3.0 * sd), (mean - lsl) / (3.0 * sd))


def _fmt_pct(value: float) -> str:
    return f"{value:g}"


# --------------------------------------------------------------------------- #
# Decision trees
# --------------------------------------------------------------------------- #
def _appearance(profile: SubstanceProfile) -> SpecificationParameter:
    """ICH Q6A Decision Tree #1 — physical form + colour."""

    return SpecificationParameter(
        parameter="Appearance / Description",
        proposed_limit=f"{profile.physical_form}, {profile.colour}",
        justification=(
            "ICH Q6A Decision Tree #1: a qualitative description of physical form and colour is a "
            "universal test for every new drug substance and product."
        ),
        method_reference="Visual examination",
    )


def _identification(profile: SubstanceProfile, mv: MethodValidation) -> SpecificationParameter:
    """ICH Q6A Decision Tree #2 — select identification method(s)."""

    methods = list(profile.identification_methods)
    validated = [m for m in methods if mv.is_validated(m)] or methods
    note = (
        ""
        if len(validated) >= 2
        else " A second orthogonal identity test is recommended (ICH Q6A 3.3.1)."
    )
    return SpecificationParameter(
        parameter="Identification",
        proposed_limit="Conforms to reference standard",
        justification=(
            "ICH Q6A Decision Tree #2: highly specific identification is required. "
            f"Orthogonal tests selected: {', '.join(validated)}.{note}"
        ),
        method_reference="; ".join(validated),
    )


def _assay(
    profile: SubstanceProfile, batches: Sequence[BatchResult], mv: MethodValidation
) -> SpecificationParameter:
    """Assay limits from manufacturing variation + stability."""

    assays = [b.assay_percent for b in batches if b.assay_percent is not None]
    # Default acceptance bands (account for analytical + manufacturing + stability variability).
    low, high = (98.0, 102.0) if profile.substance_type == "drug_substance" else (95.0, 105.0)
    if assays:
        summary = (
            f" Batch assays n={len(assays)}, mean {statistics.fmean(assays):.1f}%, "
            f"range {min(assays):.1f}-{max(assays):.1f}%."
        )
    else:
        summary = " No batch assay data supplied; default band applied."
    method = (
        "HPLC (ICH Q2(R2)-validated)"
        if mv.is_validated("assay_hplc")
        else "HPLC (validation pending)"
    )
    return SpecificationParameter(
        parameter="Assay",
        proposed_limit=f"{low:.1f}% to {high:.1f}%",
        justification=(
            f"Limits set for manufacturing variation + stability over shelf life "
            f"({profile.substance_type.replace('_', ' ')})."
            + summary
        ),
        method_reference=method,
    )


def _genotoxic_parameter(
    imp: ImpurityObservation, m7: Any, profile: SubstanceProfile
) -> SpecificationParameter:
    """Safety-based limit for a genotoxic impurity (ICH M7).

    Cohort of Concern (e.g. N-nitroso) has no applicable TTC, so its limit comes from the FDA CPCA
    acceptable intake (P5); a non-CoC alerting impurity uses the staged TTC; otherwise a
    compound-specific acceptable intake is flagged as required.
    """

    if m7.coc_flag:
        cpca = classify_cpca(imp.structural_assignment)
        ppm = cpca.ai_limit_ng_per_day / profile.max_daily_dose_g / 1000.0
        return SpecificationParameter(
            parameter=f"Impurity: {imp.name} (Cohort of Concern)",
            proposed_limit=f"NMT {ppm:.3g} ppm",
            justification=(
                f"ICH M7(R2) Class {m7.m7_class}, Cohort of Concern (TTC not applicable); FDA CPCA "
                f"Category {cpca.category} AI {cpca.ai_limit_ng_per_day:g} ng/day at "
                f"{profile.max_daily_dose_g:g} g/day."
            ),
            method_reference="Specific LC-MS/MS (nitrosamine)",
        )
    if m7.ttc_ug_per_day is not None:
        ppm = m7.ttc_ug_per_day / profile.max_daily_dose_g
        return SpecificationParameter(
            parameter=f"Impurity: {imp.name} (mutagenic)",
            proposed_limit=f"NMT {ppm:.3g} ppm",
            justification=(
                f"ICH M7(R2) Class {m7.m7_class}: safety-based acceptable intake "
                f"{m7.ttc_ug_per_day:g} microg/day (TTC) at {profile.max_daily_dose_g:g} g/day."
            ),
            method_reference="Specific (sensitive) HPLC / LC-MS",
        )
    return SpecificationParameter(
        parameter=f"Impurity: {imp.name} (mutagenic)",
        proposed_limit="Compound-specific acceptable intake required",
        justification=f"ICH M7(R2) Class {m7.m7_class}: {m7.regulatory_action_required}",
        method_reference="Specific (sensitive) HPLC / LC-MS",
    )


def _impurity_parameters(
    profile: SubstanceProfile, batches: Sequence[BatchResult]
) -> list[SpecificationParameter]:
    """Per-impurity limits: M7 safety limit if genotoxic, else Q3A/B threshold, Cpk-tightened."""

    thresholds = calculate_q3ab_thresholds(
        profile.max_daily_dose_g, profile.substance_type, profile.route
    )
    qual_pct = thresholds.qualification_threshold.effective_percent
    ident_pct = thresholds.identification_threshold.effective_percent
    params: list[SpecificationParameter] = []

    for imp in profile.impurities:
        m7 = classify_m7(imp.structural_assignment) if imp.structural_assignment else None
        if m7 is not None and m7.m7_class in _GENOTOXIC_CLASSES:
            params.append(_genotoxic_parameter(imp, m7, profile))
            continue

        # Ordinary impurity: Q3A/B qualification threshold, tightened by process capability.
        limit_pct = qual_pct
        basis = (
            f"ICH {thresholds.regulatory_basis} qualification threshold "
            f"{_fmt_pct(qual_pct)}% at {profile.max_daily_dose_g:g} g/day."
        )
        cpk = (
            process_capability_cpk(imp.batch_levels_percent, usl=qual_pct)
            if imp.batch_levels_percent
            else None
        )
        if cpk is not None and cpk > _CPK_CAPABLE:
            observed_max = max(imp.batch_levels_percent)
            tightened = min(qual_pct, round(observed_max * 1.5, 3))
            if tightened < limit_pct:
                limit_pct = tightened
                basis += (
                    f" Process capable (Cpk={cpk:.2f} > {_CPK_CAPABLE}); limit tightened to "
                    f"observed max {observed_max:.3g}% x 1.5 = {_fmt_pct(limit_pct)}%."
                )
        params.append(
            SpecificationParameter(
                parameter=f"Impurity: {imp.name}",
                proposed_limit=f"NMT {_fmt_pct(limit_pct)}%",
                justification=basis,
                method_reference="HPLC (related substances)",
            )
        )

    # Any unspecified impurity + total impurities.
    params.append(
        SpecificationParameter(
            parameter="Any unspecified impurity",
            proposed_limit=f"NMT {_fmt_pct(ident_pct)}%",
            justification=(
                f"ICH {thresholds.regulatory_basis} identification threshold "
                f"{_fmt_pct(ident_pct)}% — any single unspecified impurity."
            ),
            method_reference="HPLC (related substances)",
        )
    )
    totals = [b.total_impurities_percent for b in batches if b.total_impurities_percent is not None]
    total_limit = max(2.0, round(max(totals) * 1.5, 1)) if totals else 2.0
    total_summary = (
        f" Batch totals max {max(totals):.2g}%." if totals else " Default total-impurities ceiling."
    )
    params.append(
        SpecificationParameter(
            parameter="Total impurities",
            proposed_limit=f"NMT {_fmt_pct(total_limit)}%",
            justification="ICH Q3A/B: sum of all impurities controlled." + total_summary,
            method_reference="HPLC (related substances)",
        )
    )
    return params


def _dissolution(profile: SubstanceProfile, mv: MethodValidation) -> SpecificationParameter | None:
    """ICH Q6A Decision Tree #3 — dissolution for an immediate-release solid oral product."""

    if not profile.is_solid_oral or (profile.high_solubility and profile.rapidly_dissolving):
        return None
    method = "USP <711> Apparatus 2 (paddle)"
    return SpecificationParameter(
        parameter="Dissolution",
        proposed_limit="Q = 80% in 30 minutes",
        justification=(
            "ICH Q6A Decision Tree #3 (immediate-release solid oral): a single-point dissolution "
            "acceptance criterion (Q at a defined time) ensures consistent in-vitro release."
            + ("" if mv.is_validated("dissolution") else " (dissolution method validation pending)")
        ),
        method_reference=method,
    )


def _disintegration(profile: SubstanceProfile) -> SpecificationParameter | None:
    """Disintegration in lieu of dissolution for rapidly-dissolving, high-solubility products."""

    if not (profile.is_solid_oral and profile.high_solubility and profile.rapidly_dissolving):
        return None
    return SpecificationParameter(
        parameter="Disintegration",
        proposed_limit="NMT 15 minutes",
        justification=(
            "ICH Q6A: for a rapidly-dissolving (>=80% in 15 min), high-solubility product, "
            "disintegration may replace dissolution."
        ),
        method_reference="USP <701> Disintegration",
    )


def _water_content(
    profile: SubstanceProfile, batches: Sequence[BatchResult], mv: MethodValidation
) -> SpecificationParameter | None:
    """ICH Q6A Decision Tree #7 — water content when hygroscopic or a hydrate."""

    if not (profile.is_hygroscopic or profile.is_hydrate):
        return None
    waters = [b.water_content_percent for b in batches if b.water_content_percent is not None]
    if waters:
        limit = round(max(waters) * 1.5 + 0.5, 1)
        summary = f" Batch water max {max(waters):.2g}%."
    else:
        limit = 5.0
        summary = " No batch water data; conservative default applied."
    return SpecificationParameter(
        parameter="Water content",
        proposed_limit=f"NMT {_fmt_pct(limit)}%",
        justification=(
            "ICH Q6A Decision Tree #7: water content controlled "
            + (
                "(hydrate stoichiometry / stability)."
                if profile.is_hydrate
                else "(hygroscopic / stability)."
            )
            + summary
        ),
        method_reference="Karl Fischer titration (USP <921>)"
        if mv.is_validated("water_kf")
        else "Karl Fischer titration (validation pending)",
    )


# --------------------------------------------------------------------------- #
# The builder
# --------------------------------------------------------------------------- #
def build_specification(
    substance_profile: SubstanceProfile,
    batch_analysis_data: Sequence[BatchResult],
    method_validation: MethodValidation,
) -> Specification:
    """Run all applicable ICH Q6A decision trees; return the complete draft specification table."""

    params: list[SpecificationParameter] = [
        _appearance(substance_profile),
        _identification(substance_profile, method_validation),
        _assay(substance_profile, batch_analysis_data, method_validation),
        *_impurity_parameters(substance_profile, batch_analysis_data),
    ]
    for optional in (
        _dissolution(substance_profile, method_validation),
        _disintegration(substance_profile),
        _water_content(substance_profile, batch_analysis_data, method_validation),
    ):
        if optional is not None:
            params.append(optional)

    return Specification(
        substance_name=substance_profile.name,
        dosage_form=substance_profile.dosage_form,
        parameters=tuple(params),
        metadata={
            "substance_type": substance_profile.substance_type,
            "route": substance_profile.route,
            "max_daily_dose_g": substance_profile.max_daily_dose_g,
            "guideline": "ICH Q6A",
            "n_batches": len(batch_analysis_data),
        },
    )
