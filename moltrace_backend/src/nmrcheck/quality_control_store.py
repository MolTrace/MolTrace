from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    QualityAssessment,
    QualityAssessmentRequest,
    QualityFinding,
    QualityFindingReviewRequest,
    QualityOverride,
    QualityOverrideCreate,
)
from .orm import (
    ArtifactRecordORM,
    ManagedFileRecordORM,
    QualityAssessmentORM,
    QualityFindingORM,
    QualityOverrideORM,
    SpectraCheckAuditEventORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckProjectORM,
    SpectraCheckSessionFileLinkORM,
    SpectraCheckSessionORM,
    utcnow,
)
from .spectrum import SpectrumParseError, parse_processed_spectrum


class QualityControlError(ValueError):
    pass


def _json_dump(value: Any, *, default: Any) -> str:
    return json.dumps(default if value is None else value, sort_keys=True, separators=(",", ":"))


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _project_visible(row: SpectraCheckProjectORM | None, *, owner_scope_id: int | None) -> bool:
    return row is not None and (owner_scope_id is None or row.owner_id == owner_scope_id)


def _session_visible(row: SpectraCheckSessionORM | None, *, owner_scope_id: int | None) -> bool:
    return row is not None and _project_visible(row.project, owner_scope_id=owner_scope_id)


def _get_visible_session(session: Session, session_id: int, *, owner_scope_id: int | None) -> SpectraCheckSessionORM | None:
    row = session.get(SpectraCheckSessionORM, session_id)
    return row if _session_visible(row, owner_scope_id=owner_scope_id) else None


def _storage_path_from_key(storage_root: Path, storage_key: str) -> Path:
    if storage_key.startswith("storage/"):
        return storage_root.parent / storage_key
    return storage_root / storage_key


def _file_path(row: ManagedFileRecordORM, storage_root: Path) -> Path:
    metadata = _json_dict(row.metadata_json)
    local_path = metadata.get("local_path")
    if isinstance(local_path, str) and local_path.strip():
        return Path(local_path)
    return _storage_path_from_key(storage_root, row.storage_key)


def _finding(
    *,
    severity: str,
    code: str,
    title: str,
    message: str,
    recommendation: str | None = None,
    layer: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "title": title,
        "message": message,
        "recommendation": recommendation,
        "layer": layer,
        "metadata_json": metadata or {},
    }


def _score_from_findings(findings: list[dict[str, Any]], *, not_assessed: bool = False) -> float | None:
    if not_assessed:
        return None
    score = 1.0
    for finding in findings:
        severity = finding.get("severity")
        if severity == "critical":
            score -= 0.6
        elif severity == "error":
            score -= 0.4
        elif severity == "warning":
            score -= 0.15
        elif severity == "info":
            score -= 0.03
    return round(max(0.0, min(1.0, score)), 4)


def _statuses_from_findings(
    findings: list[dict[str, Any]],
    *,
    not_assessed: bool = False,
    force_review: bool = False,
) -> tuple[str, str, bool]:
    severities = {str(finding.get("severity")) for finding in findings}
    if not_assessed:
        return ("not_assessed", "not_ready", True)
    if "critical" in severities or "error" in severities:
        return ("qc_fail", "blocked_until_review", True)
    if force_review:
        return ("requires_human_review", "blocked_until_review", True)
    if "warning" in severities:
        return ("qc_warning", "usable_with_warnings", True)
    return ("qc_pass", "ready_for_unified_evidence", False)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _xy_from_points(points: Any) -> tuple[list[float], list[float]]:
    x_values: list[float] = []
    y_values: list[float] = []
    if not isinstance(points, list):
        return (x_values, y_values)
    for point in points:
        if isinstance(point, dict):
            x = point.get("x", point.get("shift_ppm", point.get("ppm")))
            y = point.get("y", point.get("intensity"))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x, y = point[0], point[1]
        else:
            continue
        x_num = _finite_float(x)
        y_num = _finite_float(y)
        if x_num is not None and y_num is not None:
            x_values.append(x_num)
            y_values.append(y_num)
    return (x_values, y_values)


def _xy_from_payload(payload: dict[str, Any]) -> tuple[list[float], list[float]]:
    x_direct = payload.get("x")
    y_direct = payload.get("y")
    if isinstance(x_direct, list) and isinstance(y_direct, list):
        x_values: list[float] = []
        y_values: list[float] = []
        for x, y in zip(x_direct, y_direct, strict=False):
            x_num = _finite_float(x)
            y_num = _finite_float(y)
            if x_num is not None and y_num is not None:
                x_values.append(x_num)
                y_values.append(y_num)
        if x_values and y_values:
            return (x_values, y_values)
    for key in ("preview_points", "points", "data"):
        x_values, y_values = _xy_from_points(payload.get(key))
        if x_values and y_values:
            return (x_values, y_values)
    return ([], [])


def _metrics_from_xy(x_values: list[float], y_values: list[float]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "xy_point_count": len(x_values),
        "ppm_axis_valid": len(x_values) >= 2 and len(x_values) == len(y_values),
    }
    if not x_values or not y_values:
        return metrics
    metrics["x_min"] = min(x_values)
    metrics["x_max"] = max(x_values)
    metrics["reversed_x_axis"] = x_values[0] > x_values[-1] if len(x_values) >= 2 else False
    metrics["baseline_estimate"] = round(statistics.median(y_values), 6)
    abs_y = sorted(abs(y) for y in y_values)
    noise_window = abs_y[: max(2, len(abs_y) // 5)] if len(abs_y) >= 2 else abs_y
    noise = statistics.pstdev(noise_window) if len(noise_window) >= 2 else 0.0
    if noise <= 0 and noise_window:
        noise = max(statistics.mean(noise_window), 1e-12)
    max_abs = max(abs_y) if abs_y else 0.0
    metrics["noise_estimate"] = round(noise, 6)
    metrics["signal_to_noise_estimate"] = round(max_abs / noise, 4) if noise > 0 else None
    if max_abs > 0:
        metrics["clipped_point_count"] = sum(1 for y in y_values if abs(y) >= max_abs * 0.999)
    else:
        metrics["clipped_point_count"] = 0
    return metrics


def _add_xy_findings(findings: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    point_count = int(metrics.get("xy_point_count") or metrics.get("point_count") or 0)
    if point_count <= 0:
        findings.append(
            _finding(
                severity="warning",
                code="no_xy_points",
                title="No x/y spectrum points found",
                message="QC could not find numeric x/y arrays in this target.",
                recommendation="Re-upload a processed spectrum or inspect the artifact payload.",
            )
        )
    elif point_count < 2 or not metrics.get("ppm_axis_valid", False):
        findings.append(
            _finding(
                severity="error",
                code="invalid_ppm_axis",
                title="Invalid ppm axis",
                message="The spectrum axis does not contain enough valid numeric points for evidence use.",
                recommendation="Review the processed spectrum export and regenerate the preview.",
            )
        )
    signal_to_noise = metrics.get("signal_to_noise_estimate")
    if isinstance(signal_to_noise, (int, float)) and signal_to_noise < 3:
        findings.append(
            _finding(
                severity="warning",
                code="low_signal_to_noise",
                title="Low signal-to-noise estimate",
                message="The estimated signal-to-noise ratio is below a conservative review threshold.",
                recommendation="Review acquisition/processing settings before using this as strong evidence.",
            )
        )
    clipped = int(metrics.get("clipped_point_count") or 0)
    if clipped > max(5, point_count // 20):
        findings.append(
            _finding(
                severity="warning",
                code="possible_clipping",
                title="Possible intensity clipping",
                message="Many points sit at the maximum absolute intensity.",
                recommendation="Check the processed export for clipping or display scaling artifacts.",
            )
        )


def _modality_from_file(row: ManagedFileRecordORM, *, override: str | None = None) -> str:
    if override:
        return override
    metadata = _json_dict(row.metadata_json)
    nucleus = str(metadata.get("nucleus") or metadata.get("detected_nucleus") or "").upper()
    searchable = f"{row.original_filename} {row.filename} {nucleus}".lower()
    if row.file_kind == "raw_fid":
        return "raw_fid_nmr"
    if row.file_kind == "processed_nmr":
        return "nmr_13c_processed" if "13c" in searchable or "13 c" in searchable else "nmr_1h_processed"
    if row.file_kind == "lcms_peak_table":
        return "lcms_feature_table"
    if row.file_kind in {"lcms_mzml", "lcms_mzxml"}:
        return "lcms_ms1"
    if row.file_kind == "report":
        return "report"
    return "unknown"


def _modality_from_artifact(row: ArtifactRecordORM, payload: dict[str, Any], *, override: str | None = None) -> str:
    if override:
        return override
    metadata = _json_dict(row.metadata_json)
    nucleus = str(payload.get("nucleus") or metadata.get("nucleus") or "").upper()
    if row.artifact_type in {"spectrum_preview", "processed_spectrum", "peak_table", "nmr_metadata"}:
        return "nmr_13c_processed" if "13C" in nucleus else "nmr_1h_processed"
    if row.artifact_type == "msms_annotation":
        return "msms"
    if row.artifact_type == "lcms_feature_table":
        return "lcms_feature_table"
    if row.artifact_type == "unified_evidence":
        return "unknown"
    if row.artifact_type in {"report_json", "report_html"}:
        return "report"
    return "unknown"


def _modality_from_evidence_layer(layer: str, *, override: str | None = None) -> str:
    if override:
        return override
    normalized = layer.strip().lower()
    if normalized in {"predicted_nmr", "processed_nmr", "nmr_1h_processed"}:
        return "nmr_1h_processed"
    if normalized in {"carbon13", "nmr_13c_processed"}:
        return "nmr_13c_processed"
    if "hrms" in normalized or "exact_mass" in normalized:
        return "hrms"
    if "fragmentation" in normalized or "msms" in normalized:
        return "msms"
    if "consensus" in normalized:
        return "lcms_consensus"
    if "feature" in normalized:
        return "lcms_feature_table"
    if "lcms" in normalized:
        return "lcms_ms1"
    if "report" in normalized:
        return "report"
    return "unknown"


def _assessment_to_record(row: QualityAssessmentORM) -> QualityAssessment:
    warnings = _text_list(_json_list(row.warnings_json))
    notes = _text_list(_json_list(row.notes_json))
    recommended_actions = _text_list(_json_list(row.recommended_actions_json))
    return QualityAssessment(
        id=row.id,
        target_type=row.target_type,  # type: ignore[arg-type]
        target_id=row.target_id,
        modality=row.modality,  # type: ignore[arg-type]
        quality_score=row.quality_score,
        qc_status=row.qc_status,  # type: ignore[arg-type]
        readiness_status=row.readiness_status,  # type: ignore[arg-type]
        metrics_json=_json_dict(row.metrics_json),
        findings_json=_json_list(row.findings_json),
        warnings_json=warnings,
        notes_json=notes,
        recommended_actions_json=recommended_actions,
        human_review_required=row.human_review_required,
        override_status=row.override_status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
        recommended_actions=recommended_actions,
    )


def _finding_to_record(row: QualityFindingORM) -> QualityFinding:
    recommendation = row.recommendation
    recommended_actions = [recommendation] if recommendation else []
    return QualityFinding(
        id=row.id,
        target_type=row.target_type,  # type: ignore[arg-type]
        target_id=row.target_id,
        severity=row.severity,  # type: ignore[arg-type]
        code=row.code,
        title=row.title,
        message=row.message,
        recommendation=recommendation,
        layer=row.layer,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Finding review records QC disposition only; it does not confirm identity."],
        recommended_actions=recommended_actions,
    )


def _override_to_record(row: QualityOverrideORM) -> QualityOverride:
    return QualityOverride(
        id=row.id,
        assessment_id=row.assessment_id,
        reviewer_name=row.reviewer_name,
        reason=row.reason,
        decision=row.decision,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Quality override preserves reviewer rationale and does not confirm structure identity."],
    )


def _session_ids_for_target(session: Session, *, target_type: str, target_id: int) -> list[int]:
    if target_type == "session":
        return [target_id]
    if target_type == "evidence":
        evidence = session.get(SpectraCheckEvidenceRecordORM, target_id)
        return [evidence.session_id] if evidence is not None else []
    if target_type == "artifact":
        artifact = session.get(ArtifactRecordORM, target_id)
        return [artifact.session_id] if artifact is not None and artifact.session_id is not None else []
    if target_type == "file":
        return list(
            session.scalars(
                select(SpectraCheckSessionFileLinkORM.session_id)
                .where(SpectraCheckSessionFileLinkORM.file_id == target_id)
                .order_by(SpectraCheckSessionFileLinkORM.created_at.desc())
            ).all()
        )
    return []


def _add_session_audit(
    session: Session,
    *,
    session_ids: list[int],
    actor_id: int | None,
    event_type: str,
    message: str,
    metadata: dict[str, Any],
) -> None:
    for session_id in dict.fromkeys(session_ids):
        session.add(
            SpectraCheckAuditEventORM(
                session_id=session_id,
                event_type=event_type,
                message=message,
                actor_id=actor_id,
                metadata_json=_json_dump(metadata, default={}),
            )
        )


def _persist_assessment(
    session: Session,
    *,
    target_type: str,
    target_id: int,
    modality: str,
    metrics: dict[str, Any],
    findings: list[dict[str, Any]],
    warnings: list[str],
    notes: list[str],
    recommended_actions: list[str],
    metadata: dict[str, Any] | None,
    actor_id: int | None,
    force_review: bool = False,
    not_assessed: bool = False,
) -> QualityAssessmentORM:
    qc_status, readiness_status, human_review_required = _statuses_from_findings(
        findings,
        not_assessed=not_assessed,
        force_review=force_review,
    )
    row = QualityAssessmentORM(
        target_type=target_type,
        target_id=target_id,
        modality=modality,
        quality_score=_score_from_findings(findings, not_assessed=not_assessed),
        qc_status=qc_status,
        readiness_status=readiness_status,
        metrics_json=_json_dump(metrics, default={}),
        warnings_json=_json_dump(warnings, default=[]),
        notes_json=_json_dump(notes, default=[]),
        recommended_actions_json=_json_dump(recommended_actions, default=[]),
        human_review_required=human_review_required,
        metadata_json=_json_dump(metadata or {}, default={}),
    )
    session.add(row)
    session.flush()
    finding_records: list[dict[str, Any]] = []
    for finding in findings:
        finding_metadata = dict(finding.get("metadata_json") or {})
        finding_metadata["assessment_id"] = row.id
        finding_row = QualityFindingORM(
            target_type=target_type,
            target_id=target_id,
            severity=str(finding.get("severity") or "info"),
            code=str(finding.get("code") or "quality_finding"),
            title=str(finding.get("title") or "Quality finding"),
            message=str(finding.get("message") or ""),
            recommendation=finding.get("recommendation"),
            layer=finding.get("layer"),
            metadata_json=_json_dump(finding_metadata, default={}),
        )
        session.add(finding_row)
        session.flush()
        finding_records.append(_finding_to_record(finding_row).model_dump(mode="json"))
    row.findings_json = _json_dump(finding_records, default=[])
    if target_type == "evidence" and readiness_status == "blocked_until_review":
        evidence = session.get(SpectraCheckEvidenceRecordORM, target_id)
        if evidence is not None:
            evidence.status = "blocked_until_review"
            evidence.updated_at = utcnow()
    _add_session_audit(
        session,
        session_ids=_session_ids_for_target(session, target_type=target_type, target_id=target_id),
        actor_id=actor_id,
        event_type="quality.assessment.create",
        message="Quality assessment recorded for evidence readiness review.",
        metadata={
            "assessment_id": row.id,
            "target_type": target_type,
            "target_id": target_id,
            "qc_status": qc_status,
            "readiness_status": readiness_status,
        },
    )
    session.flush()
    session.refresh(row)
    return row


def _build_processed_payload_assessment(
    payload: dict[str, Any],
    *,
    modality: str,
    target_label: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str], list[str]]:
    x_values, y_values = _xy_from_payload(payload)
    metrics = _metrics_from_xy(x_values, y_values)
    metrics["point_count"] = int(payload.get("point_count") or metrics.get("xy_point_count") or 0)
    metrics["peak_count"] = len(payload.get("peaks") or payload.get("inferred_peaks") or [])
    findings: list[dict[str, Any]] = []
    _add_xy_findings(findings, metrics)
    warnings = _text_list(payload.get("warnings"))
    if warnings:
        findings.append(
            _finding(
                severity="warning",
                code="source_warnings_present",
                title="Source warnings present",
                message=f"{target_label} contains parser or evidence warnings.",
                recommendation="Review source warnings before using this evidence in unified confidence.",
                metadata={"warning_count": len(warnings)},
            )
        )
    notes = ["QC assesses data usability only; a QC pass does not confirm molecular identity."]
    actions = ["Review parser warnings and peak picking before promoting this evidence."]
    return (metrics, findings, warnings, notes, actions)


def _build_file_assessment(
    row: ManagedFileRecordORM,
    *,
    storage_root: Path,
    modality_override: str | None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[str], list[str], list[str], dict[str, Any], bool]:
    modality = _modality_from_file(row, override=modality_override)
    metadata = _json_dict(row.metadata_json)
    notes = ["QC evaluates whether uploaded data is usable as evidence; it does not confirm identity."]
    warnings: list[str] = []
    actions: list[str] = []
    findings: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {
        "filename": row.original_filename,
        "file_kind": row.file_kind,
        "file_size_bytes": row.file_size_bytes,
        "sha256_present": bool(row.sha256),
        "storage_backend": row.storage_backend,
    }
    not_assessed = False
    if row.file_kind == "raw_fid":
        metrics.update(
            {
                "raw_sha256_present": bool(row.sha256),
                "vendor_detected": metadata.get("vendor_detected") or metadata.get("vendor"),
                "required_files_present": metadata.get("required_files_present"),
                "nucleus_detected": metadata.get("nucleus") or metadata.get("detected_nucleus"),
                "acquisition_metadata_present": bool(metadata.get("acquisition_metadata") or metadata.get("acquisition_parameters")),
                "processing_preset_recorded": bool(metadata.get("processing_preset")),
                "raw_file_immutable": bool(metadata.get("raw_file_immutable")),
            }
        )
        if not row.sha256:
            findings.append(_finding(severity="error", code="raw_hash_missing", title="Raw hash missing", message="Raw FID upload is missing SHA-256 provenance."))
        if not metrics["raw_file_immutable"]:
            findings.append(_finding(severity="critical", code="raw_immutability_unverified", title="Raw immutability not verified", message="Raw FID metadata does not mark the upload immutable.", recommendation="Re-upload through the managed immutable file endpoint."))
        if not metrics["vendor_detected"]:
            findings.append(_finding(severity="warning", code="vendor_not_detected", title="Vendor not detected", message="QC could not confirm Bruker or Agilent/Varian provenance.", recommendation="Inspect archive inventory before processing."))
        if metrics["required_files_present"] is False:
            findings.append(_finding(severity="error", code="raw_required_files_missing", title="Required raw files missing", message="Raw FID metadata reports missing required vendor files."))
        elif metrics["required_files_present"] is None:
            findings.append(_finding(severity="warning", code="raw_inventory_not_recorded", title="Raw inventory not recorded", message="Required vendor-file inventory was not present in metadata."))
        if not metrics["acquisition_metadata_present"]:
            findings.append(_finding(severity="warning", code="acquisition_metadata_missing", title="Acquisition metadata missing", message="QC could not find acquisition parameters in provenance metadata."))
        actions.append("Review raw archive inventory and acquisition metadata before using derived spectra.")
        return (modality, metrics, findings, warnings, notes, actions, {"source": "managed_file"}, not_assessed)
    if row.file_kind == "processed_nmr":
        path = _file_path(row, storage_root)
        if not path.exists():
            findings.append(_finding(severity="error", code="stored_file_missing", title="Stored file unavailable", message="Managed file record exists but local file bytes are unavailable."))
            actions.append("Restore managed local storage or re-upload the processed spectrum.")
        else:
            try:
                preview = parse_processed_spectrum(filename=row.original_filename, content=path.read_bytes())
            except SpectrumParseError as exc:
                findings.append(_finding(severity="warning", code="processed_parse_warning", title="Processed spectrum not parsed", message=str(exc), recommendation="Review the processed file export format."))
                not_assessed = True
            else:
                payload = preview.model_dump(mode="json")
                extra_metrics, extra_findings, parser_warnings, parser_notes, parser_actions = _build_processed_payload_assessment(payload, modality=modality, target_label="Processed spectrum file")
                metrics.update(extra_metrics)
                findings.extend(extra_findings)
                warnings.extend(parser_warnings)
                notes.extend(parser_notes)
                actions.extend(parser_actions)
        return (modality, metrics, findings, warnings, notes, actions, {"source": "managed_file"}, not_assessed)
    findings.append(
        _finding(
            severity="info",
            code="unsupported_file_kind",
            title="File kind not assessed by QC",
            message=f"File kind '{row.file_kind}' does not have a dedicated QC adapter yet.",
            recommendation="Use human review or add a dedicated QC adapter for this file kind.",
        )
    )
    not_assessed = True
    actions.append("Attach modality-specific metadata or convert this target into a supported evidence artifact.")
    return (modality, metrics, findings, warnings, notes, actions, {"source": "managed_file"}, not_assessed)


def _build_artifact_assessment(
    row: ArtifactRecordORM,
    *,
    modality_override: str | None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[str], list[str], list[str], dict[str, Any], bool]:
    payload = _json_dict(row.artifact_json) if row.artifact_json else {}
    modality = _modality_from_artifact(row, payload, override=modality_override)
    metrics: dict[str, Any] = {
        "artifact_type": row.artifact_type,
        "content_type": row.content_type,
        "sha256_present": bool(row.sha256),
    }
    notes = ["Artifact QC checks whether derived outputs are usable as evidence, not whether identity is confirmed."]
    warnings: list[str] = []
    actions = ["Review artifact provenance before promoting it to unified evidence."]
    findings: list[dict[str, Any]] = []
    not_assessed = False
    if row.artifact_type in {"spectrum_preview", "processed_spectrum", "peak_table", "nmr_metadata"}:
        extra_metrics, extra_findings, source_warnings, source_notes, source_actions = _build_processed_payload_assessment(
            payload,
            modality=modality,
            target_label="Processed spectrum artifact",
        )
        metrics.update(extra_metrics)
        findings.extend(extra_findings)
        warnings.extend(source_warnings)
        notes.extend(source_notes)
        actions.extend(source_actions)
    elif row.artifact_type == "msms_annotation":
        peaks = payload.get("peaks") or payload.get("fragments") or []
        explained = payload.get("explained_peak_count") or payload.get("matched_peak_count")
        metrics.update(
            {
                "precursor_present": bool(payload.get("precursor_mz") or payload.get("precursor")),
                "peak_count": len(peaks) if isinstance(peaks, list) else None,
                "explained_peak_count": explained,
                "explained_intensity_fraction": payload.get("explained_intensity_fraction"),
                "contradiction_count": len(_text_list(payload.get("contradictions"))),
            }
        )
        if not metrics["precursor_present"]:
            findings.append(_finding(severity="warning", code="msms_precursor_missing", title="MS/MS precursor missing", message="MS/MS artifact did not expose a precursor m/z."))
        if metrics["contradiction_count"]:
            findings.append(_finding(severity="warning", code="msms_contradictions", title="MS/MS contradictions present", message="MS/MS evidence contains contradictions requiring review."))
    elif row.artifact_type == "lcms_feature_table":
        features = payload.get("features") or payload.get("feature_table") or []
        metrics["feature_count"] = len(features) if isinstance(features, list) else payload.get("feature_count")
        if not metrics["feature_count"]:
            findings.append(_finding(severity="warning", code="lcms_features_empty", title="No LC-MS features found", message="Feature artifact did not contain detected feature rows."))
    elif row.artifact_type in {"report_json", "report_html"}:
        metrics["report_has_content"] = bool(row.artifact_json or row.storage_key)
        if not metrics["report_has_content"]:
            findings.append(_finding(severity="warning", code="report_content_missing", title="Report content missing", message="Report artifact has no JSON or downloadable storage payload."))
    else:
        not_assessed = True
        findings.append(_finding(severity="info", code="unsupported_artifact_type", title="Artifact type not assessed by QC", message=f"Artifact type '{row.artifact_type}' does not have a dedicated QC adapter yet."))
    return (modality, metrics, findings, warnings, notes, actions, {"source": "artifact_record"}, not_assessed)


def _build_evidence_assessment(
    row: SpectraCheckEvidenceRecordORM,
    *,
    modality_override: str | None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[str], list[str], list[str], dict[str, Any], bool, bool]:
    response = _json_dict(row.response_json)
    contradictions = _text_list(_json_list(row.contradictions_json)) + _text_list(response.get("contradictions"))
    warnings = _text_list(_json_list(row.warnings_json)) + _text_list(response.get("warnings"))
    modality = _modality_from_evidence_layer(row.layer, override=modality_override)
    metrics: dict[str, Any] = {
        "layer": row.layer,
        "selected_for_unified": row.selected_for_unified,
        "score": row.score,
        "contradiction_count": len(contradictions),
        "warning_count": len(warnings),
    }
    findings: list[dict[str, Any]] = []
    force_review = False
    if contradictions:
        force_review = True
        findings.append(
            _finding(
                severity="warning",
                code="evidence_contradictions_present",
                title="Evidence contradictions present",
                message="Evidence record contains contradictions and requires human review before unified evidence.",
                recommendation="Resolve or explicitly override contradictions before promoting this evidence.",
                layer=row.layer,
                metadata={"contradictions": contradictions},
            )
        )
    if warnings:
        findings.append(
            _finding(
                severity="warning",
                code="evidence_warnings_present",
                title="Evidence warnings present",
                message="Evidence record contains warnings from an upstream evidence layer.",
                recommendation="Review warnings before using this evidence in reports.",
                layer=row.layer,
                metadata={"warning_count": len(warnings)},
            )
        )
    status_text = str(response.get("status") or row.status).lower()
    if "failed" in status_text or "error" in status_text:
        findings.append(_finding(severity="error", code="evidence_layer_failed", title="Evidence layer failed", message="Evidence status indicates a failed upstream operation.", layer=row.layer))
    if modality == "hrms":
        metrics.update(
            {
                "observed_mz_present": bool(response.get("observed_mz") or response.get("mz")),
                "ppm_tolerance": response.get("ppm_tolerance") or response.get("tolerance_ppm"),
                "mass_error_ppm": response.get("mass_error_ppm") or response.get("ppm_error"),
                "isotope_hints_present": bool(response.get("isotope_hints") or response.get("isotope_summary")),
            }
        )
    elif modality == "msms":
        metrics.update(
            {
                "precursor_present": bool(response.get("precursor_mz") or response.get("precursor")),
                "peak_count": response.get("peak_count") or len(response.get("peaks") or []),
                "explained_peak_count": response.get("explained_peak_count"),
                "explained_intensity_fraction": response.get("explained_intensity_fraction"),
            }
        )
    elif modality.startswith("lcms"):
        metrics.update(
            {
                "scan_count": response.get("scan_count"),
                "ms1_count": response.get("ms1_count"),
                "ms2_count": response.get("ms2_count"),
                "rt_range": response.get("rt_range"),
                "feature_count": response.get("feature_count") or len(response.get("features") or []),
                "blank_like_feature_count": response.get("blank_like_feature_count"),
            }
        )
    notes = ["Evidence QC checks readiness for synthesis and reports; it does not confirm identity."]
    actions = ["Keep human-review language in any downstream unified evidence or report."]
    return (modality, metrics, findings, warnings, notes, actions, {"source": "evidence_record"}, False, force_review)


def assess_file(
    session_factory: sessionmaker[Session],
    file_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
    storage_root: Path,
    payload: QualityAssessmentRequest | None = None,
) -> QualityAssessment:
    with session_scope(session_factory) as session:
        row = session.get(ManagedFileRecordORM, file_id)
        if row is None:
            raise KeyError(f"File {file_id} not found.")
        modality, metrics, findings, warnings, notes, actions, metadata, not_assessed = _build_file_assessment(
            row,
            storage_root=storage_root,
            modality_override=payload.modality if payload else None,
        )
        if payload:
            metadata.update(payload.metadata_json)
        assessment = _persist_assessment(
            session,
            target_type="file",
            target_id=file_id,
            modality=modality,
            metrics=metrics,
            findings=findings,
            warnings=warnings,
            notes=notes,
            recommended_actions=actions,
            metadata=metadata,
            actor_id=actor_id,
            not_assessed=not_assessed,
        )
        return _assessment_to_record(assessment)


def assess_artifact(
    session_factory: sessionmaker[Session],
    artifact_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
    payload: QualityAssessmentRequest | None = None,
) -> QualityAssessment:
    with session_scope(session_factory) as session:
        row = session.get(ArtifactRecordORM, artifact_id)
        if row is None:
            raise KeyError(f"Artifact {artifact_id} not found.")
        parent_session = session.get(SpectraCheckSessionORM, row.session_id) if row.session_id is not None else None
        if row.session_id is not None and not _session_visible(parent_session, owner_scope_id=owner_scope_id):
            raise KeyError(f"Artifact {artifact_id} not found.")
        modality, metrics, findings, warnings, notes, actions, metadata, not_assessed = _build_artifact_assessment(
            row,
            modality_override=payload.modality if payload else None,
        )
        if payload:
            metadata.update(payload.metadata_json)
        assessment = _persist_assessment(
            session,
            target_type="artifact",
            target_id=artifact_id,
            modality=modality,
            metrics=metrics,
            findings=findings,
            warnings=warnings,
            notes=notes,
            recommended_actions=actions,
            metadata=metadata,
            actor_id=actor_id,
            not_assessed=not_assessed,
        )
        return _assessment_to_record(assessment)


def assess_evidence(
    session_factory: sessionmaker[Session],
    evidence_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
    payload: QualityAssessmentRequest | None = None,
) -> QualityAssessment:
    with session_scope(session_factory) as session:
        row = session.get(SpectraCheckEvidenceRecordORM, evidence_id)
        if row is None or not _session_visible(row.session, owner_scope_id=owner_scope_id):
            raise KeyError(f"Evidence {evidence_id} not found.")
        modality, metrics, findings, warnings, notes, actions, metadata, not_assessed, force_review = _build_evidence_assessment(
            row,
            modality_override=payload.modality if payload else None,
        )
        if payload:
            metadata.update(payload.metadata_json)
        assessment = _persist_assessment(
            session,
            target_type="evidence",
            target_id=evidence_id,
            modality=modality,
            metrics=metrics,
            findings=findings,
            warnings=warnings,
            notes=notes,
            recommended_actions=actions,
            metadata=metadata,
            actor_id=actor_id,
            force_review=force_review,
            not_assessed=not_assessed,
        )
        return _assessment_to_record(assessment)


def assess_session(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
    storage_root: Path,
    payload: QualityAssessmentRequest | None = None,
) -> QualityAssessment:
    with session_scope(session_factory) as session:
        parent = _get_visible_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        child_rows: list[QualityAssessmentORM] = []
        file_ids = list(
            session.scalars(
                select(SpectraCheckSessionFileLinkORM.file_id)
                .where(SpectraCheckSessionFileLinkORM.session_id == session_id)
                .order_by(SpectraCheckSessionFileLinkORM.id.asc())
            ).all()
        )
        for file_id in file_ids:
            file_row = session.get(ManagedFileRecordORM, file_id)
            if file_row is None:
                continue
            modality, metrics, findings, warnings, notes, actions, metadata, not_assessed = _build_file_assessment(
                file_row,
                storage_root=storage_root,
                modality_override=None,
            )
            child_rows.append(
                _persist_assessment(
                    session,
                    target_type="file",
                    target_id=file_id,
                    modality=modality,
                    metrics=metrics,
                    findings=findings,
                    warnings=warnings,
                    notes=notes,
                    recommended_actions=actions,
                    metadata=metadata,
                    actor_id=actor_id,
                    not_assessed=not_assessed,
                )
            )
        artifact_rows = list(
            session.scalars(
                select(ArtifactRecordORM)
                .where(ArtifactRecordORM.session_id == session_id)
                .order_by(ArtifactRecordORM.id.asc())
            ).all()
        )
        for artifact_row in artifact_rows:
            modality, metrics, findings, warnings, notes, actions, metadata, not_assessed = _build_artifact_assessment(
                artifact_row,
                modality_override=None,
            )
            child_rows.append(
                _persist_assessment(
                    session,
                    target_type="artifact",
                    target_id=artifact_row.id,
                    modality=modality,
                    metrics=metrics,
                    findings=findings,
                    warnings=warnings,
                    notes=notes,
                    recommended_actions=actions,
                    metadata=metadata,
                    actor_id=actor_id,
                    not_assessed=not_assessed,
                )
            )
        evidence_rows = list(
            session.scalars(
                select(SpectraCheckEvidenceRecordORM)
                .where(SpectraCheckEvidenceRecordORM.session_id == session_id)
                .order_by(SpectraCheckEvidenceRecordORM.id.asc())
            ).all()
        )
        for evidence_row in evidence_rows:
            modality, metrics, findings, warnings, notes, actions, metadata, not_assessed, force_review = _build_evidence_assessment(
                evidence_row,
                modality_override=None,
            )
            child_rows.append(
                _persist_assessment(
                    session,
                    target_type="evidence",
                    target_id=evidence_row.id,
                    modality=modality,
                    metrics=metrics,
                    findings=findings,
                    warnings=warnings,
                    notes=notes,
                    recommended_actions=actions,
                    metadata=metadata,
                    actor_id=actor_id,
                    force_review=force_review,
                    not_assessed=not_assessed,
                )
            )
        passed = sum(1 for row in child_rows if row.qc_status == "qc_pass")
        warnings_count = sum(1 for row in child_rows if row.qc_status == "qc_warning")
        failed = sum(1 for row in child_rows if row.qc_status == "qc_fail")
        requires_review = sum(1 for row in child_rows if row.human_review_required)
        findings: list[dict[str, Any]] = []
        if failed:
            findings.append(_finding(severity="error", code="session_qc_failures", title="Session has QC failures", message=f"{failed} session item(s) failed QC.", recommendation="Resolve failed items before unified evidence or reports."))
        elif requires_review:
            findings.append(_finding(severity="warning", code="session_review_required", title="Session requires human review", message=f"{requires_review} session item(s) require human review.", recommendation="Review warnings and contradictions before unified evidence."))
        elif warnings_count:
            findings.append(_finding(severity="warning", code="session_warnings_present", title="Session has QC warnings", message=f"{warnings_count} session item(s) are usable with warnings."))
        metrics = {
            "total_items": len(child_rows),
            "passed": passed,
            "warnings": warnings_count,
            "failed": failed,
            "requires_review": requires_review,
            "file_count": len(file_ids),
            "artifact_count": len(artifact_rows),
            "evidence_count": len(evidence_rows),
        }
        notes = ["Session QC aggregates files, artifacts, and evidence readiness; it does not confirm identity."]
        actions = ["Only promote evidence after reviewing blocked items, warnings, and any override rationale."]
        metadata = {"source": "session_quality_aggregate", "child_assessment_ids": [row.id for row in child_rows]}
        if payload:
            metadata.update(payload.metadata_json)
        assessment = _persist_assessment(
            session,
            target_type="session",
            target_id=session_id,
            modality=payload.modality if payload and payload.modality else "unknown",
            metrics=metrics,
            findings=findings,
            warnings=[],
            notes=notes,
            recommended_actions=actions,
            metadata=metadata,
            actor_id=actor_id,
            force_review=requires_review > 0 and failed == 0,
            not_assessed=len(child_rows) == 0,
        )
        return _assessment_to_record(assessment)


def get_latest_assessment(
    session_factory: sessionmaker[Session],
    *,
    target_type: str,
    target_id: int,
    owner_scope_id: int | None,
) -> QualityAssessment | None:
    with session_scope(session_factory) as session:
        if target_type == "session" and _get_visible_session(session, target_id, owner_scope_id=owner_scope_id) is None:
            return None
        if target_type == "evidence":
            evidence = session.get(SpectraCheckEvidenceRecordORM, target_id)
            if evidence is None or not _session_visible(evidence.session, owner_scope_id=owner_scope_id):
                return None
        row = session.scalar(
            select(QualityAssessmentORM)
            .where(QualityAssessmentORM.target_type == target_type)
            .where(QualityAssessmentORM.target_id == target_id)
            .order_by(QualityAssessmentORM.created_at.desc(), QualityAssessmentORM.id.desc())
            .limit(1)
        )
        return _assessment_to_record(row) if row is not None else None


def review_finding(
    session_factory: sessionmaker[Session],
    finding_id: int,
    payload: QualityFindingReviewRequest,
    *,
    actor_id: int | None,
) -> QualityFinding | None:
    with session_scope(session_factory) as session:
        row = session.get(QualityFindingORM, finding_id)
        if row is None:
            return None
        metadata = _json_dict(row.metadata_json)
        metadata["review"] = {
            "reviewer_name": payload.reviewer_name,
            "reason": payload.reason,
            "decision": payload.decision,
            "metadata_json": payload.metadata_json,
            "reviewed_at": utcnow().isoformat(),
        }
        row.metadata_json = _json_dump(metadata, default={})
        _add_session_audit(
            session,
            session_ids=_session_ids_for_target(session, target_type=row.target_type, target_id=row.target_id),
            actor_id=actor_id,
            event_type="quality.finding.review",
            message="Quality finding reviewed.",
            metadata={"finding_id": row.id, "target_type": row.target_type, "target_id": row.target_id, "decision": payload.decision},
        )
        session.flush()
        session.refresh(row)
        return _finding_to_record(row)


def override_evidence(
    session_factory: sessionmaker[Session],
    evidence_id: int,
    payload: QualityOverrideCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> QualityAssessment:
    with session_scope(session_factory) as session:
        evidence = session.get(SpectraCheckEvidenceRecordORM, evidence_id)
        if evidence is None or not _session_visible(evidence.session, owner_scope_id=owner_scope_id):
            raise KeyError(f"Evidence {evidence_id} not found.")
        assessment = session.scalar(
            select(QualityAssessmentORM)
            .where(QualityAssessmentORM.target_type == "evidence")
            .where(QualityAssessmentORM.target_id == evidence_id)
            .order_by(QualityAssessmentORM.created_at.desc(), QualityAssessmentORM.id.desc())
            .limit(1)
        )
        if assessment is None:
            modality, metrics, findings, warnings, notes, actions, metadata, not_assessed, force_review = _build_evidence_assessment(
                evidence,
                modality_override=None,
            )
            assessment = _persist_assessment(
                session,
                target_type="evidence",
                target_id=evidence_id,
                modality=modality,
                metrics=metrics,
                findings=findings,
                warnings=warnings,
                notes=notes,
                recommended_actions=actions,
                metadata=metadata,
                actor_id=actor_id,
                force_review=force_review,
                not_assessed=not_assessed,
            )
        override = QualityOverrideORM(
            assessment_id=assessment.id,
            reviewer_name=payload.reviewer_name,
            reason=payload.reason,
            decision=payload.decision,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(override)
        session.flush()
        warnings = _text_list(_json_list(assessment.warnings_json))
        actions = _text_list(_json_list(assessment.recommended_actions_json))
        metadata = _json_dict(assessment.metadata_json)
        metadata["latest_override"] = _override_to_record(override).model_dump(mode="json")
        assessment.override_status = payload.decision
        assessment.metadata_json = _json_dump(metadata, default={})
        assessment.human_review_required = True
        if payload.decision == "allow_with_warning":
            assessment.qc_status = "qc_warning"
            assessment.readiness_status = "usable_with_warnings"
            evidence.status = "usable_with_warnings"
            warnings.append("Human override allows this evidence with warnings; preserve the override reason downstream.")
            actions.append("Carry override rationale into unified evidence and reports.")
        elif payload.decision == "block":
            assessment.qc_status = "qc_fail"
            assessment.readiness_status = "blocked_until_review"
            evidence.status = "blocked_until_review"
            actions.append("Keep evidence blocked until a reviewer resolves the QC issue.")
        else:
            assessment.qc_status = "qc_fail"
            assessment.readiness_status = "not_ready"
            evidence.status = "needs_reprocessing"
            actions.append("Reprocess or replace the evidence before unified evidence or reports.")
        evidence.updated_at = utcnow()
        assessment.warnings_json = _json_dump(warnings, default=[])
        assessment.recommended_actions_json = _json_dump(actions, default=[])
        _add_session_audit(
            session,
            session_ids=[evidence.session_id],
            actor_id=actor_id,
            event_type="quality.evidence.override",
            message="Quality override recorded for evidence readiness.",
            metadata={"evidence_id": evidence_id, "assessment_id": assessment.id, "override_id": override.id, "decision": payload.decision},
        )
        session.flush()
        session.refresh(assessment)
        return _assessment_to_record(assessment)
