from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable

from .lcms_features import LCMSFeatureDetectionError, detect_lcms_features
from .models import (
    LCMSFeatureDetectionRequest,
    LCMSFeatureGroup,
    LCMSFeatureGroupingRequest,
    LCMSFeatureGroupingResult,
    LCMSFeatureGroupingRunInput,
    LCMSFeatureGroupMember,
    LCMSFeatureRelationship,
    LCMSRunAlignmentSummary,
)


class LCMSFeatureGroupingError(ValueError):
    pass


@dataclass
class _FeatureMember:
    run_id: str
    role: str
    source_format: str
    file_sha256: str
    feature_id: str
    target_mz: float
    observed_mz: float
    raw_rt: float
    aligned_rt: float
    area: float
    apex_intensity: float
    purity_percent: float
    purity_label: str
    feature_label: str
    linked_msms_count: int
    warnings: list[str]


@dataclass
class _FeatureGroup:
    group_id: str
    representative_mz: float
    representative_rt: float
    members: list[_FeatureMember]


RELATION_DELTAS: tuple[tuple[str, str, float], ...] = (
    ("isotope_m_plus_1_z1", "M+1 isotope spacing, z=1", 1.003355),
    ("isotope_m_plus_1_z2", "M+1 isotope spacing, z=2", 0.501678),
    ("adduct_pair_na_h", "[M+Na]+ / [M+H]+ pair", 21.981943),
    ("adduct_pair_k_h", "[M+K]+ / [M+H]+ pair", 37.955882),
    ("adduct_pair_nh4_h", "[M+NH4]+ / [M+H]+ pair", 17.026549),
    ("in_source_loss_h2o", "in-source H2O loss", 18.010565),
    ("in_source_loss_nh3", "in-source NH3 loss", 17.026549),
    ("in_source_loss_co2", "in-source CO2 loss", 43.989829),
    ("in_source_loss_co", "in-source CO loss", 27.994915),
)


def _effective_tolerance(target_mz: float, mz_tolerance_da: float, ppm_tolerance: float) -> float:
    return max(float(mz_tolerance_da), abs(float(target_mz)) * float(ppm_tolerance) / 1_000_000.0)


def _parse_float_text(text: str | None) -> list[float]:
    if not text:
        return []
    values: list[float] = []
    for token in text.replace(";", ",").replace("\n", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError as exc:
            raise LCMSFeatureGroupingError(f"Could not parse m/z value {token!r}.") from exc
        if value <= 0:
            raise LCMSFeatureGroupingError("m/z values must be positive.")
        values.append(value)
    return values


def _median(values: Iterable[float], default: float = 0.0) -> float:
    values = [v for v in values if abs(v) < 1_000_000]
    if not values:
        return default
    return float(statistics.median(values))


def _build_detection_request(run: LCMSFeatureGroupingRunInput, request: LCMSFeatureGroupingRequest) -> LCMSFeatureDetectionRequest:
    return LCMSFeatureDetectionRequest(
        sample_id=request.sample_id,
        filename=run.filename,
        source_format=run.source_format,
        source_text=run.source_text,
        target_mz_values=request.target_mz_values,
        target_mz_text=request.target_mz_text,
        mz_tolerance_da=request.mz_tolerance_da,
        ppm_tolerance=request.ppm_tolerance,
        min_relative_feature_height=request.min_relative_feature_height,
        min_peak_height=request.min_peak_height,
        min_scans_per_feature=request.min_scans_per_feature,
        smoothing_window=request.smoothing_window,
        purity_rt_window_min=request.purity_rt_window_min,
        top_coeluting_ions=request.top_coeluting_ions,
        max_features=request.max_features_per_run,
        max_scans_to_report=request.max_scans_to_report,
        max_xic_points=request.max_xic_points,
    )


def _feature_mz(feature) -> float:
    return float(feature.observed_mz or feature.target_mz)


def _match_shift_to_reference(run_features, ref_features, request: LCMSFeatureGroupingRequest, anchors: list[float]) -> tuple[float, int, list[str]]:
    warnings: list[str] = []
    shifts: list[float] = []
    for feature in run_features:
        if feature.area <= 0:
            continue
        mz = _feature_mz(feature)
        if anchors and not any(abs(mz - anchor) <= _effective_tolerance(anchor, request.mz_tolerance_da, request.ppm_tolerance) for anchor in anchors):
            continue
        candidates = []
        for ref in ref_features:
            ref_mz = _feature_mz(ref)
            if abs(mz - ref_mz) <= _effective_tolerance(ref_mz, request.mz_tolerance_da, request.ppm_tolerance):
                rt_delta = abs(float(feature.apex_rt_min) - float(ref.apex_rt_min))
                if rt_delta <= request.rt_alignment_search_window_min:
                    candidates.append((rt_delta, ref))
        if candidates:
            _rt_delta, ref = sorted(candidates, key=lambda item: item[0])[0]
            shifts.append(float(ref.apex_rt_min) - float(feature.apex_rt_min))
    if not shifts:
        warnings.append("No reliable shared m/z anchors were found for retention-time alignment; using zero RT shift for this run.")
        return 0.0, 0, warnings
    # Avoid extreme single-feature shifts from dominating if a run is malformed.
    shift = max(min(_median(shifts), request.max_rt_shift_min), -request.max_rt_shift_min)
    return shift, len(shifts), warnings


def _extract_members(run_results: dict[str, object], rt_shifts: dict[str, float], request: LCMSFeatureGroupingRequest) -> list[_FeatureMember]:
    members: list[_FeatureMember] = []
    for run_id, result in run_results.items():
        role = getattr(result, "metadata", {}).get("run_role", "sample")
        for feature in getattr(result, "features", []):
            if feature.area <= 0 and feature.label == "weak_or_no_feature":
                continue
            if request.exclude_weak_features and feature.label == "weak_or_no_feature":
                continue
            mz = _feature_mz(feature)
            raw_rt = float(feature.apex_rt_min)
            shift = rt_shifts.get(run_id, 0.0)
            purity = feature.purity
            members.append(
                _FeatureMember(
                    run_id=run_id,
                    role=str(role),
                    source_format=str(getattr(result, "source_format", "unknown")),
                    file_sha256=str(getattr(result, "file_sha256", "")),
                    feature_id=str(feature.feature_id),
                    target_mz=float(feature.target_mz),
                    observed_mz=mz,
                    raw_rt=raw_rt,
                    aligned_rt=max(raw_rt + shift, 0.0),
                    area=float(feature.area),
                    apex_intensity=float(feature.apex_intensity),
                    purity_percent=float(purity.purity_percent if purity else 0.0),
                    purity_label=str(purity.label if purity else "not_assessed"),
                    feature_label=str(feature.label),
                    linked_msms_count=len(feature.linked_msms_spectra or []),
                    warnings=list(feature.warnings or []),
                )
            )
    return members


def _weighted_mean(pairs: Iterable[tuple[float, float]]) -> float:
    total_weight = 0.0
    total_value = 0.0
    for value, weight in pairs:
        w = max(float(weight), 1e-9)
        total_weight += w
        total_value += float(value) * w
    return total_value / total_weight if total_weight else 0.0


def _group_members(members: list[_FeatureMember], request: LCMSFeatureGroupingRequest) -> list[_FeatureGroup]:
    groups: list[_FeatureGroup] = []
    for member in sorted(members, key=lambda m: (m.aligned_rt, m.observed_mz)):
        matched_group: _FeatureGroup | None = None
        for group in groups:
            mz_tol = _effective_tolerance(group.representative_mz, request.mz_tolerance_da, request.ppm_tolerance)
            if abs(member.observed_mz - group.representative_mz) <= mz_tol and abs(member.aligned_rt - group.representative_rt) <= request.group_rt_tolerance_min:
                matched_group = group
                break
        if matched_group is None:
            groups.append(_FeatureGroup(group_id=f"G{len(groups) + 1:03d}", representative_mz=member.observed_mz, representative_rt=member.aligned_rt, members=[member]))
        else:
            matched_group.members.append(member)
            matched_group.representative_mz = _weighted_mean((m.observed_mz, m.area) for m in matched_group.members)
            matched_group.representative_rt = _weighted_mean((m.aligned_rt, m.area) for m in matched_group.members)
    return groups


def _relationship_candidates(groups: list[_FeatureGroup], request: LCMSFeatureGroupingRequest) -> dict[str, list[LCMSFeatureRelationship]]:
    relationships: dict[str, list[LCMSFeatureRelationship]] = {group.group_id: [] for group in groups}
    if not request.annotate_feature_families:
        return relationships
    mz_tol = max(request.mz_tolerance_da, 0.01)
    for i, a in enumerate(groups):
        for b in groups[i + 1 :]:
            if abs(a.representative_rt - b.representative_rt) > request.family_rt_tolerance_min:
                continue
            delta = abs(b.representative_mz - a.representative_mz)
            for kind, label, expected in RELATION_DELTAS:
                if abs(delta - expected) <= mz_tol:
                    rel = LCMSFeatureRelationship(
                        relationship_type=kind,
                        label=label,
                        partner_group_id=b.group_id,
                        observed_delta_mz=round(delta, 6),
                        expected_delta_mz=round(expected, 6),
                        rt_delta_min=round(abs(a.representative_rt - b.representative_rt), 6),
                        evidence_summary=f"{a.group_id} and {b.group_id} are within {abs(delta - expected):.4f} Da of the {label} mass difference at similar aligned RT.",
                    )
                    relationships[a.group_id].append(rel)
                    relationships[b.group_id].append(
                        LCMSFeatureRelationship(
                            relationship_type=kind,
                            label=label,
                            partner_group_id=a.group_id,
                            observed_delta_mz=round(delta, 6),
                            expected_delta_mz=round(expected, 6),
                            rt_delta_min=round(abs(a.representative_rt - b.representative_rt), 6),
                            evidence_summary=f"{b.group_id} and {a.group_id} are within {abs(delta - expected):.4f} Da of the {label} mass difference at similar aligned RT.",
                        )
                    )
                    break
    return relationships


def _label_group(sample_area: float, blank_area: float, request: LCMSFeatureGroupingRequest, roles_present: list[str]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if sample_area <= 0 and blank_area > 0:
        return "blank_only_background", ["Feature was observed only in blank/background runs."]
    if sample_area <= 0:
        return "reference_or_qc_only", ["Feature was observed only in reference/QC runs and not in sample runs."]
    blank_ratio = blank_area / sample_area if sample_area > 0 else 0.0
    if blank_area > 0 and blank_ratio >= request.blank_area_ratio_threshold:
        return "blank_like_feature", [f"Blank area is {blank_ratio:.2f}× the sample area, above the configured threshold."]
    if blank_area > 0 and blank_ratio >= request.possible_background_ratio_threshold:
        warnings.append(f"Blank area is {blank_ratio:.2f}× sample area; keep this feature under background review.")
        return "possible_background_feature", warnings
    if sample_area < request.min_blank_subtracted_area:
        warnings.append("Sample area is below the configured minimum blank-subtracted area threshold.")
        return "low_abundance_feature", warnings
    if "sample" in roles_present and ("blank" in roles_present or blank_area > 0):
        return "sample_enriched_feature", warnings
    return "sample_only_feature", warnings


def _to_public_group(group: _FeatureGroup, relationships: list[LCMSFeatureRelationship], request: LCMSFeatureGroupingRequest) -> LCMSFeatureGroup:
    sample_area = sum(m.area for m in group.members if m.role == "sample")
    blank_area = sum(m.area for m in group.members if m.role == "blank")
    qc_area = sum(m.area for m in group.members if m.role == "qc")
    reference_area = sum(m.area for m in group.members if m.role == "reference")
    blank_subtracted_area = max(sample_area - blank_area * request.blank_subtraction_factor, 0.0)
    roles_present = sorted({m.role for m in group.members})
    label, label_warnings = _label_group(sample_area, blank_area, request, roles_present)
    member_models = [
        LCMSFeatureGroupMember(
            run_id=m.run_id,
            role=m.role,  # type: ignore[arg-type]
            source_format=m.source_format,
            file_sha256=m.file_sha256,
            feature_id=m.feature_id,
            target_mz=round(m.target_mz, 6),
            observed_mz=round(m.observed_mz, 6),
            raw_apex_rt_min=round(m.raw_rt, 6),
            aligned_apex_rt_min=round(m.aligned_rt, 6),
            rt_shift_applied_min=round(m.aligned_rt - m.raw_rt, 6),
            area=round(m.area, 6),
            apex_intensity=round(m.apex_intensity, 6),
            purity_percent=round(m.purity_percent, 4),
            purity_label=m.purity_label,
            feature_label=m.feature_label,
            linked_msms_count=m.linked_msms_count,
            warnings=m.warnings,
        )
        for m in sorted(group.members, key=lambda x: (x.role, x.run_id, x.feature_id))
    ]
    summary = [
        f"Grouped {len(group.members)} feature(s) around m/z {group.representative_mz:.6f} at aligned RT {group.representative_rt:.3f} min.",
        f"Sample area {sample_area:.3g}; blank area {blank_area:.3g}; blank-subtracted area {blank_subtracted_area:.3g}.",
    ]
    if relationships:
        summary.append(f"Detected {len(relationships)} isotope/adduct/in-source family relationship(s) at similar retention time.")
    if label in {"blank_like_feature", "possible_background_feature", "blank_only_background"}:
        summary.append("Do not use this feature as structure evidence unless a reviewer confirms it is not background or carryover.")
    return LCMSFeatureGroup(
        group_id=group.group_id,
        representative_mz=round(group.representative_mz, 6),
        representative_rt_min=round(group.representative_rt, 6),
        label=label,  # type: ignore[arg-type]
        member_count=len(group.members),
        roles_present=roles_present,
        sample_area=round(sample_area, 6),
        blank_area=round(blank_area, 6),
        qc_area=round(qc_area, 6),
        reference_area=round(reference_area, 6),
        blank_ratio=round((blank_area / sample_area) if sample_area > 0 else 0.0, 6),
        blank_subtracted_area=round(blank_subtracted_area, 6),
        members=member_models,
        relationships=relationships,
        evidence_summary=summary,
        warnings=label_warnings,
    )


def _feature_table(groups: list[LCMSFeatureGroup]) -> str:
    header = "group_id,representative_mz,aligned_rt_min,label,sample_area,blank_area,blank_ratio,blank_subtracted_area,member_count,roles_present"
    lines = [header]
    for g in groups:
        roles = ";".join(g.roles_present)
        lines.append(
            f"{g.group_id},{g.representative_mz:.6f},{g.representative_rt_min:.6f},{g.label},{g.sample_area:.6f},{g.blank_area:.6f},{g.blank_ratio:.6f},{g.blank_subtracted_area:.6f},{g.member_count},{roles}"
        )
    return "\n".join(lines)


def group_lcms_features(request: LCMSFeatureGroupingRequest) -> LCMSFeatureGroupingResult:
    if not request.runs:
        raise LCMSFeatureGroupingError("At least one LC-MS run is required for feature grouping.")
    run_ids = [run.run_id for run in request.runs]
    if len(run_ids) != len(set(run_ids)):
        raise LCMSFeatureGroupingError("LC-MS run IDs must be unique.")
    if not any(run.role == "sample" for run in request.runs):
        raise LCMSFeatureGroupingError("At least one run must have role='sample'.")
    if len(request.runs) > request.max_runs:
        raise LCMSFeatureGroupingError(f"The request contains {len(request.runs)} runs, above max_runs={request.max_runs}.")

    run_results: dict[str, object] = {}
    warnings: list[str] = []
    for run in request.runs:
        try:
            result = detect_lcms_features(_build_detection_request(run, request))
        except LCMSFeatureDetectionError as exc:
            raise LCMSFeatureGroupingError(f"Run {run.run_id}: {exc}") from exc
        result.metadata["run_id"] = run.run_id
        result.metadata["run_role"] = run.role
        run_results[run.run_id] = result
        warnings.extend([f"{run.run_id}: {warning}" for warning in result.warnings])

    sample_runs = [run for run in request.runs if run.role == "sample"]
    reference_run_id = request.reference_run_id or sample_runs[0].run_id
    if reference_run_id not in run_results:
        raise LCMSFeatureGroupingError("reference_run_id must match one of the supplied runs.")
    reference_result = run_results[reference_run_id]
    reference_features = [f for f in getattr(reference_result, "features", []) if f.area > 0]
    anchor_mz = list(request.alignment_anchor_mz_values or [])
    anchor_mz.extend(_parse_float_text(request.alignment_anchor_mz_text))

    rt_shifts: dict[str, float] = {reference_run_id: 0.0}
    alignment_summaries: list[LCMSRunAlignmentSummary] = []
    for run in request.runs:
        result = run_results[run.run_id]
        features = [f for f in getattr(result, "features", []) if f.area > 0]
        if run.run_id == reference_run_id or not request.align_retention_times:
            shift = 0.0
            anchors_used = 0 if run.run_id != reference_run_id else len(features)
            align_warnings: list[str] = []
        else:
            shift, anchors_used, align_warnings = _match_shift_to_reference(features, reference_features, request, anchor_mz)
            warnings.extend([f"{run.run_id}: {warning}" for warning in align_warnings])
        rt_shifts[run.run_id] = shift
        alignment_summaries.append(
            LCMSRunAlignmentSummary(
                run_id=run.run_id,
                role=run.role,
                filename=run.filename,
                source_format=str(getattr(result, "source_format", "unknown")),
                file_sha256=str(getattr(result, "file_sha256", "")),
                raw_feature_count=int(getattr(result, "feature_count", 0)),
                aligned_feature_count=len(features),
                rt_shift_min=round(shift, 6),
                anchor_match_count=anchors_used,
                warnings=align_warnings,
            )
        )

    members = _extract_members(run_results, rt_shifts, request)
    if not members:
        raise LCMSFeatureGroupingError("No LC-MS features survived filtering for grouping.")
    raw_groups = _group_members(members, request)
    relationship_map = _relationship_candidates(raw_groups, request)
    public_groups = [_to_public_group(group, relationship_map.get(group.group_id, []), request) for group in raw_groups]
    public_groups.sort(key=lambda g: (g.label not in {"sample_enriched_feature", "sample_only_feature"}, -g.blank_subtracted_area, g.representative_rt_min, g.representative_mz))

    sample_enriched = sum(1 for g in public_groups if g.label in {"sample_enriched_feature", "sample_only_feature"})
    background = sum(1 for g in public_groups if g.label in {"blank_like_feature", "blank_only_background", "possible_background_feature"})
    blank_subtracted = sum(1 for g in public_groups if g.blank_subtracted_area > 0)
    relationship_count = sum(len(g.relationships) for g in public_groups)
    label = "ready_for_candidate_scoring" if sample_enriched else "review_background_before_scoring" if background else "metadata_only"
    if background:
        warnings.append("One or more feature groups look blank-like or background-like; inspect blank subtraction before candidate scoring.")
    actions = [
        "Use sample-enriched groups as the LC-MS feature table for downstream HRMS/MS/MS confidence only after human review.",
        "Treat blank-like and possible-background groups as exclusions unless a reviewer overrides the background call.",
        "Store run hashes, RT shifts, grouping tolerances, and blank subtraction settings in the structure elucidation report.",
    ]
    notes = [
        "Retention-time alignment is a local shift correction based on shared feature anchors, not a full chromatographic warping model.",
        "Blank subtraction is evidence triage, not proof of identity; carryover, matrix effects, and ion suppression still require review.",
        "Feature-family relationships are simple mass-difference annotations for isotope/adduct/in-source-loss review.",
    ]
    return LCMSFeatureGroupingResult(
        sample_id=request.sample_id,
        run_count=len(request.runs),
        reference_run_id=reference_run_id,
        label=label,  # type: ignore[arg-type]
        group_count=len(public_groups),
        sample_enriched_group_count=sample_enriched,
        background_group_count=background,
        blank_subtracted_group_count=blank_subtracted,
        relationship_count=relationship_count,
        alignment_summaries=alignment_summaries,
        groups=public_groups[: request.max_groups_to_report],
        feature_table_text=_feature_table(public_groups[: request.max_groups_to_report]),
        recommended_next_actions=actions,
        warnings=warnings,
        notes=notes,
        metadata={
            "parser_version": "week37_lcms_feature_grouping_v1",
            "mz_tolerance_da": request.mz_tolerance_da,
            "ppm_tolerance": request.ppm_tolerance,
            "group_rt_tolerance_min": request.group_rt_tolerance_min,
            "family_rt_tolerance_min": request.family_rt_tolerance_min,
            "blank_subtraction_factor": request.blank_subtraction_factor,
            "blank_area_ratio_threshold": request.blank_area_ratio_threshold,
            "possible_background_ratio_threshold": request.possible_background_ratio_threshold,
            "align_retention_times": request.align_retention_times,
            "alignment_anchor_mz_values": anchor_mz,
            "run_ids": run_ids,
        },
    )
