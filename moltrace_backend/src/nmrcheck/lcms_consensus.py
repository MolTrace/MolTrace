from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable

from .hrms import HRMSError, formula_info
from .models import (
    LCMSFeatureFamilyConsensus,
    LCMSFeatureFamilyConsensusRequest,
    LCMSFeatureFamilyConsensusResult,
    LCMSFeatureFamilyLayerScore,
    LCMSFeatureFamilyMember,
    LCMSFeatureFamilyRelationship,
    LCMSFeatureGroup,
)


class LCMSFeatureFamilyConsensusError(ValueError):
    pass


@dataclass(frozen=True)
class _DeltaRule:
    relationship_type: str
    label: str
    expected_delta_mz: float
    role: str
    direction: int = 1
    evidence_weight: float = 1.0


ISOTOPE_RULES: tuple[_DeltaRule, ...] = (
    _DeltaRule("isotope_m_plus_1_z1", "M+1 isotope spacing, z=1", 1.003355, "isotope_m_plus_1", 1, 1.0),
    _DeltaRule("isotope_m_plus_2_z1", "M+2 isotope spacing, z=1", 2.006710, "isotope_m_plus_2", 1, 0.8),
    _DeltaRule("isotope_m_plus_1_z2", "M+1 isotope spacing, z=2", 0.501678, "isotope_m_plus_1_z2", 1, 0.7),
)

ADDUCT_RULES: tuple[_DeltaRule, ...] = (
    _DeltaRule("adduct_pair_na_h", "[M+Na]+ / [M+H]+ pair", 21.981943, "adduct_sodium", 1, 0.9),
    _DeltaRule("adduct_pair_k_h", "[M+K]+ / [M+H]+ pair", 37.955882, "adduct_potassium", 1, 0.8),
    _DeltaRule("adduct_pair_nh4_h", "[M+NH4]+ / [M+H]+ pair", 17.026549, "adduct_ammonium", 1, 0.8),
)

LOSS_RULES: tuple[_DeltaRule, ...] = (
    _DeltaRule("in_source_loss_h2o", "in-source H2O loss", 18.010565, "in_source_loss", -1, 0.75),
    _DeltaRule("in_source_loss_nh3", "in-source NH3 loss", 17.026549, "in_source_loss", -1, 0.65),
    _DeltaRule("in_source_loss_co2", "in-source CO2 loss", 43.989829, "in_source_loss", -1, 0.70),
    _DeltaRule("in_source_loss_co", "in-source CO loss", 27.994915, "in_source_loss", -1, 0.55),
)

LAYER_WEIGHTS = {
    "blank_subtraction": 0.22,
    "peak_purity": 0.18,
    "isotope_envelope": 0.24,
    "adduct_consensus": 0.14,
    "in_source_loss": 0.08,
    "msms_linkage": 0.14,
}

BACKGROUND_LABELS = {"blank_like_feature", "blank_only_background", "possible_background_feature"}
SAMPLE_LABELS = {"sample_enriched_feature", "sample_only_feature", "low_abundance_feature"}


def _clamp(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _effective_mz_tolerance(target_mz: float, mz_tolerance_da: float, ppm_tolerance: float) -> float:
    return max(float(mz_tolerance_da), abs(float(target_mz)) * float(ppm_tolerance) / 1_000_000.0)


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator <= 0:
        return default
    return numerator / denominator


def _intensity(group: LCMSFeatureGroup) -> float:
    return float(group.blank_subtracted_area or group.sample_area or 0.0)


def _status(score: float | None, used: bool, contradiction: bool = False) -> str:
    if not used:
        return "not_used"
    if contradiction:
        return "contradiction"
    if score is None:
        return "not_scored"
    if score >= 0.78:
        return "strong_agreement"
    if score >= 0.58:
        return "partial_agreement"
    if score >= 0.35:
        return "weak_or_ambiguous"
    return "poor_agreement"


def _layer(
    layer: str,
    label: str,
    *,
    used: bool,
    score: float | None,
    evidence_summary: list[str] | None = None,
    warnings: list[str] | None = None,
    contradiction: bool = False,
    metadata: dict[str, object] | None = None,
) -> LCMSFeatureFamilyLayerScore:
    return LCMSFeatureFamilyLayerScore(
        layer=layer,
        label=label,
        used=used,
        score=round(_clamp(score), 4) if score is not None else None,
        status=_status(score, used, contradiction),
        contradiction=bool(contradiction),
        evidence_count=len(evidence_summary or []),
        evidence_summary=evidence_summary or [],
        warnings=warnings or [],
        metadata=metadata or {},
    )


def _weighted_score(layers: list[LCMSFeatureFamilyLayerScore]) -> tuple[float, int, int]:
    total = 0.0
    weights = 0.0
    used_count = 0
    contradiction_count = 0
    for item in layers:
        if item.used and item.score is not None:
            weight = LAYER_WEIGHTS.get(item.layer, 0.0)
            total += item.score * weight
            weights += weight
            used_count += 1
        if item.contradiction:
            contradiction_count += 1
    if weights <= 0:
        return 0.0, used_count, contradiction_count
    return round(_clamp(total / weights), 4), used_count, contradiction_count


def _family_label(score: float, used_count: int, contradiction_count: int, promoted: bool) -> str:
    if contradiction_count:
        return "conflicting_or_background_family"
    if promoted and score >= 0.80 and used_count >= 4:
        return "high_confidence_feature_family"
    if score >= 0.62 and used_count >= 3:
        return "moderate_confidence_feature_family"
    if score >= 0.42:
        return "low_confidence_feature_family"
    return "insufficient_family_evidence"


def _member_role_for_group(anchor: LCMSFeatureGroup, group: LCMSFeatureGroup, rels: list[LCMSFeatureFamilyRelationship]) -> str:
    if group.group_id == anchor.group_id:
        return "anchor_feature"
    for rel in rels:
        if rel.partner_group_id == group.group_id:
            return rel.partner_role
    return "coeluting_unassigned"


def _feature_table_groups(text: str | None) -> list[LCMSFeatureGroup]:
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text.strip()))
    groups: list[LCMSFeatureGroup] = []
    required = {"group_id", "representative_mz", "aligned_rt_min", "label", "sample_area", "blank_area", "blank_ratio", "blank_subtracted_area"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise LCMSFeatureFamilyConsensusError("Feature table must use the Week 37 grouped feature table columns.")
    for row in reader:
        roles = [x for x in (row.get("roles_present") or "").split(";") if x]
        try:
            groups.append(
                LCMSFeatureGroup(
                    group_id=row["group_id"],
                    representative_mz=float(row["representative_mz"]),
                    representative_rt_min=float(row["aligned_rt_min"]),
                    label=row["label"],  # type: ignore[arg-type]
                    member_count=int(float(row.get("member_count") or 0)),
                    roles_present=roles,
                    sample_area=float(row["sample_area"]),
                    blank_area=float(row["blank_area"]),
                    blank_ratio=float(row["blank_ratio"]),
                    blank_subtracted_area=float(row["blank_subtracted_area"]),
                    members=[],
                    relationships=[],
                    evidence_summary=["Imported from grouped feature table text."],
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LCMSFeatureFamilyConsensusError("Could not parse one or more rows in the grouped feature table.") from exc
    return groups


def _collect_groups(request: LCMSFeatureFamilyConsensusRequest) -> list[LCMSFeatureGroup]:
    groups: list[LCMSFeatureGroup] = []
    if request.grouping_result is not None:
        groups.extend(request.grouping_result.groups)
    groups.extend(request.groups or [])
    groups.extend(_feature_table_groups(request.feature_table_text))
    seen: set[str] = set()
    deduped: list[LCMSFeatureGroup] = []
    for group in groups:
        if group.group_id in seen:
            continue
        seen.add(group.group_id)
        deduped.append(group)
    if not deduped:
        raise LCMSFeatureFamilyConsensusError("Provide a Week 37 grouping_result, groups, or feature_table_text before consensus scoring.")
    return deduped


def _candidate_anchors(groups: list[LCMSFeatureGroup], request: LCMSFeatureFamilyConsensusRequest) -> list[LCMSFeatureGroup]:
    if request.anchor_group_id:
        matches = [group for group in groups if group.group_id == request.anchor_group_id]
        if not matches:
            raise LCMSFeatureFamilyConsensusError("anchor_group_id does not match any supplied feature group.")
        return matches
    anchors: list[LCMSFeatureGroup] = []
    for group in groups:
        if group.label in BACKGROUND_LABELS and not request.include_background_groups:
            continue
        if request.require_sample_enrichment and group.label not in SAMPLE_LABELS:
            continue
        if group.blank_subtracted_area < request.min_blank_subtracted_area:
            continue
        if _intensity(group) <= 0:
            continue
        anchors.append(group)
    anchors.sort(key=lambda g: (-g.blank_subtracted_area, g.representative_rt_min, g.representative_mz))
    return anchors[: request.max_families_to_report]


def _find_rule_match(anchor: LCMSFeatureGroup, groups: list[LCMSFeatureGroup], rule: _DeltaRule, request: LCMSFeatureFamilyConsensusRequest) -> LCMSFeatureFamilyRelationship | None:
    expected_partner_mz = anchor.representative_mz + rule.direction * rule.expected_delta_mz
    candidates: list[tuple[float, float, LCMSFeatureGroup]] = []
    mz_tol = _effective_mz_tolerance(expected_partner_mz, request.mz_tolerance_da, request.ppm_tolerance)
    for group in groups:
        if group.group_id == anchor.group_id:
            continue
        rt_delta = abs(group.representative_rt_min - anchor.representative_rt_min)
        if rt_delta > request.family_rt_tolerance_min:
            continue
        mz_error = abs(group.representative_mz - expected_partner_mz)
        if mz_error <= mz_tol:
            candidates.append((mz_error, rt_delta, group))
    if not candidates:
        return None
    mz_error, rt_delta, partner = sorted(candidates, key=lambda item: (item[0], item[1], -_intensity(item[2])))[0]
    ratio = _safe_ratio(_intensity(partner), _intensity(anchor)) * 100.0
    return LCMSFeatureFamilyRelationship(
        relationship_type=rule.relationship_type,
        label=rule.label,
        anchor_group_id=anchor.group_id,
        partner_group_id=partner.group_id,
        partner_role=rule.role,
        observed_delta_mz=round(abs(partner.representative_mz - anchor.representative_mz), 6),
        expected_delta_mz=round(rule.expected_delta_mz, 6),
        mz_error_da=round(float(mz_error), 6),
        rt_delta_min=round(float(rt_delta), 6),
        intensity_ratio_percent=round(float(ratio), 4),
        evidence_weight=rule.evidence_weight,
        evidence_summary=f"{anchor.group_id} -> {partner.group_id}: {rule.label}; error {mz_error:.5f} Da; RT Δ {rt_delta:.3f} min; blank-subtracted ratio {ratio:.2f}%.",
    )


def _relationships(anchor: LCMSFeatureGroup, groups: list[LCMSFeatureGroup], request: LCMSFeatureFamilyConsensusRequest) -> list[LCMSFeatureFamilyRelationship]:
    rels: list[LCMSFeatureFamilyRelationship] = []
    rules: list[_DeltaRule] = []
    if request.score_isotope_relationships:
        rules.extend(ISOTOPE_RULES)
    if request.score_adduct_relationships:
        rules.extend(ADDUCT_RULES)
    if request.score_in_source_losses:
        rules.extend(LOSS_RULES)
    for rule in rules:
        match = _find_rule_match(anchor, groups, rule, request)
        if match is not None:
            rels.append(match)
    return rels


def _blank_layer(anchor: LCMSFeatureGroup, request: LCMSFeatureFamilyConsensusRequest) -> LCMSFeatureFamilyLayerScore:
    blank_ratio = float(anchor.blank_ratio or 0.0)
    contradiction = anchor.label in BACKGROUND_LABELS or blank_ratio >= request.blank_area_ratio_threshold
    if contradiction:
        score = 0.05
    elif blank_ratio >= request.possible_background_ratio_threshold:
        score = max(0.2, 1.0 - blank_ratio / max(request.blank_area_ratio_threshold, 1e-9))
    else:
        score = 1.0 - 0.25 * _safe_ratio(blank_ratio, max(request.possible_background_ratio_threshold, 1e-9))
    summary = [
        f"Anchor {anchor.group_id} blank ratio is {blank_ratio:.3f}; blank-subtracted area is {anchor.blank_subtracted_area:.3g}.",
        f"Anchor label from grouping is {anchor.label}.",
    ]
    warnings = []
    if contradiction:
        warnings.append("Anchor is blank-like/background-like and should not be promoted without reviewer override.")
    return _layer("blank_subtraction", "Blank subtraction / background gate", used=True, score=score, evidence_summary=summary, warnings=warnings, contradiction=contradiction, metadata={"blank_ratio": blank_ratio})


def _purity_layer(anchor: LCMSFeatureGroup, members: list[LCMSFeatureGroup]) -> LCMSFeatureFamilyLayerScore:
    purity_values: list[float] = []
    coeluting = 0
    for group in members:
        if not group.members:
            continue
        for member in group.members:
            purity_values.append(float(member.purity_percent) / 100.0)
            if str(member.purity_label) in {"possible_coelution", "poor_peak_purity"} or str(member.feature_label) == "possible_coelution":
                coeluting += 1
    if not purity_values:
        # A table-only request still deserves a conservative score rather than a false high-purity claim.
        return _layer(
            "peak_purity",
            "Peak-purity support",
            used=False,
            score=None,
            evidence_summary=[],
            warnings=["No run-level purity members were available; pass a full grouping_result for purity scoring."],
        )
    score = _clamp(sum(purity_values) / len(purity_values))
    if coeluting:
        score *= max(0.45, 1.0 - 0.15 * coeluting)
    return _layer(
        "peak_purity",
        "Peak-purity support",
        used=True,
        score=score,
        evidence_summary=[f"{len(purity_values)} member purity value(s) averaged {sum(purity_values) / len(purity_values) * 100:.1f}%.", f"Anchor feature group is {anchor.group_id}."],
        warnings=[f"{coeluting} member feature(s) had coelution warnings."] if coeluting else [],
        contradiction=False,
    )


def _isotope_layer(rels: list[LCMSFeatureFamilyRelationship], request: LCMSFeatureFamilyConsensusRequest) -> LCMSFeatureFamilyLayerScore:
    isotope_rels = [rel for rel in rels if rel.relationship_type.startswith("isotope")]
    if not isotope_rels and not request.formula:
        return _layer("isotope_envelope", "Isotope-envelope agreement", used=False, score=None, warnings=["No isotope partner was detected and no formula was supplied."], evidence_summary=[])
    warnings: list[str] = []
    summary = [rel.evidence_summary for rel in isotope_rels]
    score: float | None = None
    metadata: dict[str, object] = {"detected_isotope_relationships": len(isotope_rels)}
    contradiction = False
    if request.formula:
        try:
            info = formula_info(request.formula)
        except HRMSError as exc:
            raise LCMSFeatureFamilyConsensusError(f"Could not parse formula for isotope consensus: {exc}") from exc
        expected_m1 = info.isotope_m_plus_1_percent or 0.0
        expected_m2 = info.isotope_m_plus_2_percent or 0.0
        metadata.update({"formula": info.formula, "expected_m_plus_1_percent": expected_m1, "expected_m_plus_2_percent": expected_m2})
        rel_map = {rel.partner_role: rel for rel in isotope_rels}
        scores: list[float] = []
        if expected_m1 >= request.minimum_expected_isotope_percent:
            rel = rel_map.get("isotope_m_plus_1") or rel_map.get("isotope_m_plus_1_z2")
            if rel is None:
                scores.append(0.15)
                warnings.append(f"Formula predicts M+1 around {expected_m1:.1f}% but no M+1 feature was detected within the RT/m/z window.")
                contradiction = expected_m1 >= 8.0
            else:
                tol = max(request.isotope_ratio_absolute_tolerance_percent, expected_m1 * request.isotope_ratio_relative_tolerance)
                scores.append(max(0.0, min(1.0, 1.0 - abs(rel.intensity_ratio_percent - expected_m1) / tol)))
                summary.append(f"Observed M+1 ratio {rel.intensity_ratio_percent:.2f}% versus formula estimate {expected_m1:.2f}%.")
        if expected_m2 >= request.minimum_expected_isotope_percent:
            rel = rel_map.get("isotope_m_plus_2")
            if rel is None:
                scores.append(0.20)
                warnings.append(f"Formula predicts M+2 around {expected_m2:.1f}% but no M+2 feature was detected within the RT/m/z window.")
                contradiction = contradiction or expected_m2 >= 12.0
            else:
                tol = max(request.isotope_ratio_absolute_tolerance_percent, expected_m2 * request.isotope_ratio_relative_tolerance)
                scores.append(max(0.0, min(1.0, 1.0 - abs(rel.intensity_ratio_percent - expected_m2) / tol)))
                summary.append(f"Observed M+2 ratio {rel.intensity_ratio_percent:.2f}% versus formula estimate {expected_m2:.2f}%.")
        if not scores:
            score = 0.55 if isotope_rels else None
            if not isotope_rels:
                warnings.append("Formula has very low expected isotope satellites under current settings; isotope layer was not decisive.")
        else:
            score = sum(scores) / len(scores)
    else:
        plausible = [rel for rel in isotope_rels if 0.1 <= rel.intensity_ratio_percent <= request.isotope_ratio_plausible_max_percent]
        score = min(0.82, 0.45 + 0.18 * len(plausible) + 0.08 * sum(rel.evidence_weight for rel in plausible))
        if isotope_rels and not plausible:
            warnings.append("Isotope mass spacings were detected, but their area ratios are outside the configured plausibility range.")
            score = 0.25
            contradiction = True
    return _layer("isotope_envelope", "Isotope-envelope agreement", used=score is not None, score=score, evidence_summary=summary, warnings=warnings, contradiction=contradiction, metadata=metadata)


def _adduct_layer(rels: list[LCMSFeatureFamilyRelationship], request: LCMSFeatureFamilyConsensusRequest) -> LCMSFeatureFamilyLayerScore:
    adduct_rels = [rel for rel in rels if rel.relationship_type.startswith("adduct_pair")]
    if not adduct_rels:
        return _layer("adduct_consensus", "Adduct-family support", used=False, score=None, warnings=["No same-RT adduct-pair relationship was detected."], evidence_summary=[])
    plausible = []
    warnings: list[str] = []
    for rel in adduct_rels:
        if request.adduct_ratio_min_percent <= rel.intensity_ratio_percent <= request.adduct_ratio_max_percent:
            plausible.append(rel)
        else:
            warnings.append(f"{rel.label} ratio {rel.intensity_ratio_percent:.2f}% is outside the configured adduct ratio range.")
    score = min(0.88, 0.48 + 0.18 * len(plausible) + 0.06 * sum(rel.evidence_weight for rel in plausible)) if plausible else 0.25
    return _layer(
        "adduct_consensus",
        "Adduct-family support",
        used=True,
        score=score,
        evidence_summary=[rel.evidence_summary for rel in adduct_rels],
        warnings=warnings,
        contradiction=bool(adduct_rels and not plausible),
        metadata={"detected_adduct_relationships": len(adduct_rels), "expected_anchor_adduct": request.expected_anchor_adduct},
    )


def _loss_layer(rels: list[LCMSFeatureFamilyRelationship], request: LCMSFeatureFamilyConsensusRequest) -> LCMSFeatureFamilyLayerScore:
    loss_rels = [rel for rel in rels if rel.relationship_type.startswith("in_source_loss")]
    if not loss_rels:
        return _layer("in_source_loss", "In-source loss consistency", used=False, score=None, warnings=["No same-RT in-source loss relationship was detected."], evidence_summary=[])
    plausible = [rel for rel in loss_rels if rel.intensity_ratio_percent <= request.in_source_loss_ratio_max_percent]
    warnings = [] if plausible else ["All detected in-source loss relationships are stronger than the configured ratio ceiling; inspect for separate coeluting compounds."]
    score = min(0.78, 0.40 + 0.12 * len(plausible) + 0.05 * sum(rel.evidence_weight for rel in plausible)) if plausible else 0.22
    return _layer(
        "in_source_loss",
        "In-source loss consistency",
        used=True,
        score=score,
        evidence_summary=[rel.evidence_summary for rel in loss_rels],
        warnings=warnings,
        contradiction=bool(loss_rels and not plausible),
        metadata={"detected_loss_relationships": len(loss_rels)},
    )


def _msms_layer(anchor: LCMSFeatureGroup, members: list[LCMSFeatureGroup]) -> LCMSFeatureFamilyLayerScore:
    anchor_links = sum(int(member.linked_msms_count or 0) for member in anchor.members)
    family_links = sum(int(member.linked_msms_count or 0) for group in members for member in group.members)
    if anchor_links:
        score = 1.0
        summary = [f"Anchor group {anchor.group_id} has {anchor_links} linked MS/MS scan(s)."]
    elif family_links:
        score = 0.72
        summary = [f"Family has {family_links} linked MS/MS scan(s), but not directly on the anchor group."]
    else:
        score = 0.0
        summary = ["No linked MS/MS scans were available for this feature family."]
    return _layer("msms_linkage", "MS/MS precursor linkage", used=True, score=score, evidence_summary=summary, warnings=[] if family_links else ["Acquire or link MS/MS near the anchor RT before using this feature family as strong structure evidence."])


def _members(anchor: LCMSFeatureGroup, groups: list[LCMSFeatureGroup], rels: list[LCMSFeatureFamilyRelationship], request: LCMSFeatureFamilyConsensusRequest) -> list[LCMSFeatureGroup]:
    member_ids = {anchor.group_id}
    member_ids.update(rel.partner_group_id for rel in rels)
    for group in groups:
        if group.group_id in member_ids:
            continue
        if abs(group.representative_rt_min - anchor.representative_rt_min) <= request.family_rt_tolerance_min and _intensity(group) > 0:
            if len(member_ids) < request.max_family_members:
                member_ids.add(group.group_id)
    ordered = [group for group in groups if group.group_id in member_ids]
    ordered.sort(key=lambda g: (g.group_id != anchor.group_id, g.representative_mz))
    return ordered[: request.max_family_members]


def _public_members(anchor: LCMSFeatureGroup, groups: list[LCMSFeatureGroup], rels: list[LCMSFeatureFamilyRelationship]) -> list[LCMSFeatureFamilyMember]:
    public: list[LCMSFeatureFamilyMember] = []
    for group in groups:
        public.append(
            LCMSFeatureFamilyMember(
                group_id=group.group_id,
                family_role=_member_role_for_group(anchor, group, rels),
                representative_mz=group.representative_mz,
                representative_rt_min=group.representative_rt_min,
                label=group.label,
                sample_area=group.sample_area,
                blank_area=group.blank_area,
                blank_ratio=group.blank_ratio,
                blank_subtracted_area=group.blank_subtracted_area,
                member_count=group.member_count,
                linked_msms_count=sum(int(member.linked_msms_count or 0) for member in group.members),
            )
        )
    return public


def _promote(score: float, label: str, layers: list[LCMSFeatureFamilyLayerScore], request: LCMSFeatureFamilyConsensusRequest) -> bool:
    if label == "conflicting_or_background_family":
        return False
    if score < request.min_consensus_score_to_promote:
        return False
    if any(layer.contradiction for layer in layers if layer.layer in {"blank_subtraction", "isotope_envelope", "adduct_consensus"}):
        return False
    return True


def _build_family(anchor: LCMSFeatureGroup, groups: list[LCMSFeatureGroup], request: LCMSFeatureFamilyConsensusRequest, family_index: int) -> LCMSFeatureFamilyConsensus:
    rels = _relationships(anchor, groups, request)
    member_groups = _members(anchor, groups, rels, request)
    layers = [
        _blank_layer(anchor, request),
        _purity_layer(anchor, member_groups),
        _isotope_layer(rels, request),
        _adduct_layer(rels, request),
        _loss_layer(rels, request),
        _msms_layer(anchor, member_groups),
    ]
    score, used_count, contradiction_count = _weighted_score(layers)
    preliminary_label = _family_label(score, used_count, contradiction_count, promoted=False)
    promoted = _promote(score, preliminary_label, layers, request)
    label = _family_label(score, used_count, contradiction_count, promoted=promoted)
    summary = [
        f"Family anchored on {anchor.group_id} at m/z {anchor.representative_mz:.6f}, RT {anchor.representative_rt_min:.3f} min.",
        f"Consensus score {score:.3f}; {len(rels)} same-RT mass-difference relationship(s); {len(member_groups)} family member group(s).",
    ]
    if promoted:
        summary.append("Feature family passed the consensus promotion gate for downstream candidate scoring after human review.")
    elif label == "conflicting_or_background_family":
        summary.append("Feature family failed a contradiction/background gate and should remain under review.")
    else:
        summary.append("Feature family is usable as weak/auxiliary evidence but should not dominate candidate ranking.")
    warnings = [warning for layer in layers for warning in layer.warnings]
    return LCMSFeatureFamilyConsensus(
        family_id=f"F{family_index:03d}",
        anchor_group_id=anchor.group_id,
        anchor_mz=anchor.representative_mz,
        anchor_rt_min=anchor.representative_rt_min,
        label=label,  # type: ignore[arg-type]
        promoted_for_candidate_scoring=promoted,
        consensus_score=score,
        evidence_layer_count=used_count,
        contradiction_count=contradiction_count,
        relationship_count=len(rels),
        member_count=len(member_groups),
        members=_public_members(anchor, member_groups, rels),
        relationships=rels,
        layer_scores=layers,
        evidence_summary=summary,
        warnings=warnings,
    )


def _family_table(families: list[LCMSFeatureFamilyConsensus]) -> str:
    lines = ["family_id,anchor_group_id,anchor_mz,anchor_rt_min,label,consensus_score,promoted,relationship_count,member_count"]
    for family in families:
        lines.append(
            f"{family.family_id},{family.anchor_group_id},{family.anchor_mz:.6f},{family.anchor_rt_min:.6f},{family.label},{family.consensus_score:.4f},{str(family.promoted_for_candidate_scoring).lower()},{family.relationship_count},{family.member_count}"
        )
    return "\n".join(lines)


def score_lcms_feature_family_consensus(request: LCMSFeatureFamilyConsensusRequest) -> LCMSFeatureFamilyConsensusResult:
    groups = _collect_groups(request)
    anchors = _candidate_anchors(groups, request)
    if not anchors:
        raise LCMSFeatureFamilyConsensusError("No eligible sample-enriched LC-MS feature groups were available for consensus scoring.")
    families = [_build_family(anchor, groups, request, idx + 1) for idx, anchor in enumerate(anchors)]
    families.sort(key=lambda family: (not family.promoted_for_candidate_scoring, -family.consensus_score, family.anchor_rt_min, family.anchor_mz))
    promoted = sum(1 for family in families if family.promoted_for_candidate_scoring)
    conflicting = sum(1 for family in families if family.label == "conflicting_or_background_family")
    relationship_count = sum(family.relationship_count for family in families)
    if promoted:
        label = "ready_for_candidate_scoring"
    elif conflicting:
        label = "review_conflicting_families"
    else:
        label = "insufficient_consensus"
    warnings: list[str] = []
    if conflicting:
        warnings.append("One or more LC-MS feature families failed a background, isotope, or adduct contradiction gate.")
    if not promoted:
        warnings.append("No family passed the promotion gate; use results for review rather than automated candidate scoring.")
    actions = [
        "Review promoted feature families before passing them into unified candidate scoring.",
        "Use isotope/adduct/in-source-loss relationships as orthogonal feature-family support, not as identity proof.",
        "Keep blank ratios, RT tolerance, m/z tolerance, and formula assumptions with any exported report.",
    ]
    notes = [
        "Week 38 scores LC-MS feature-family consensus from Week 37 grouped features; it does not perform database search or generative structure proposal.",
        "Isotope scoring uses transparent approximate isotope percentages when a formula is supplied.",
        "Adduct and in-source-loss evidence is treated as supportive review evidence and can be overridden by a human reviewer.",
    ]
    return LCMSFeatureFamilyConsensusResult(
        sample_id=request.sample_id or (request.grouping_result.sample_id if request.grouping_result else None),
        label=label,  # type: ignore[arg-type]
        input_group_count=len(groups),
        family_count=len(families),
        promoted_family_count=promoted,
        conflicting_family_count=conflicting,
        relationship_count=relationship_count,
        families=families[: request.max_families_to_report],
        best_family=families[0] if families else None,
        family_table_text=_family_table(families[: request.max_families_to_report]),
        recommended_next_actions=actions,
        warnings=warnings,
        notes=notes,
        metadata={
            "parser_version": "week38_lcms_feature_family_consensus_v1",
            "mz_tolerance_da": request.mz_tolerance_da,
            "ppm_tolerance": request.ppm_tolerance,
            "family_rt_tolerance_min": request.family_rt_tolerance_min,
            "formula": request.formula,
            "expected_anchor_adduct": request.expected_anchor_adduct,
            "layer_weights": LAYER_WEIGHTS,
        },
    )
