from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any

from .models import ArtifactRecord, VisualizationArtifact, VisualizationNormalizeRequest

_NORMALIZATION_NOTE = (
    "Visualization normalization reshapes existing artifact data for plot viewers; "
    "it does not add or confirm scientific interpretation."
)


def normalize_artifact_record(record: ArtifactRecord) -> VisualizationArtifact:
    metadata = dict(record.metadata_json or {})
    metadata.update(
        {
            "content_type": record.content_type,
            "download_url": record.download_url,
            "sha256": record.sha256,
            "source_artifact_created_at": record.created_at.isoformat(),
        }
    )
    provenance = _dict_or_empty((record.metadata_json or {}).get("provenance_metadata"))
    return normalize_visualization_artifact(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        title=record.title,
        artifact_json=record.artifact_json or {},
        provenance=provenance,
        metadata=metadata,
    )


def normalize_visualization_request(
    payload: VisualizationNormalizeRequest,
) -> VisualizationArtifact:
    return normalize_visualization_artifact(
        artifact_id=payload.artifact_id,
        artifact_type=payload.artifact_type,
        title=payload.title or _title_from_type(payload.artifact_type),
        artifact_json=payload.artifact_json,
        provenance=payload.provenance,
        metadata=payload.metadata,
    )


def normalize_visualization_artifact(
    *,
    artifact_id: int | str | None,
    artifact_type: str,
    title: str | None,
    artifact_json: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> VisualizationArtifact:
    payload = deepcopy(artifact_json or {})
    warnings = _string_list(payload.get("warnings"))
    notes = _string_list(payload.get("notes"))
    if _NORMALIZATION_NOTE not in notes:
        notes.append(_NORMALIZATION_NOTE)

    provenance_out = _merged_provenance(payload, provenance=provenance, metadata=metadata)
    metadata_out = _merged_metadata(payload, metadata=metadata)
    normalized_title = title or _title_from_type(artifact_type)

    for normalizer in (
        _normalize_spectrum_1d,
        _normalize_nmr_2d,
        _normalize_fragmentation_tree,
        _normalize_msms_mirror,
        _normalize_chromatogram,
        _normalize_table,
        _normalize_metadata,
    ):
        normalized = normalizer(artifact_type, payload)
        if normalized is None:
            continue
        viewer_type, data, extra_warnings = normalized
        return VisualizationArtifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            title=normalized_title,
            viewer_type=viewer_type,
            data=data,
            warnings=_dedupe_strings([*warnings, *extra_warnings]),
            notes=_dedupe_strings(notes),
            provenance=provenance_out,
            metadata=metadata_out,
        )

    warnings.append(
        "Artifact data could not be normalized into a specialized plot-ready viewer; "
        "returning raw JSON."
    )
    return VisualizationArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        title=normalized_title,
        viewer_type="json",
        data=payload,
        warnings=_dedupe_strings(warnings),
        notes=_dedupe_strings(notes),
        provenance=provenance_out,
        metadata=metadata_out,
    )


def _normalize_spectrum_1d(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    spectrumish = _type_contains(artifact_type, "spectrum", "nmr", "peak_table")
    for root in _candidate_roots(payload):
        x_vals = _number_list(root.get("x"))
        y_vals = _number_list(root.get("y"))
        if not x_vals or not y_vals:
            point_source = _first_list(root, "preview_points", "points", "trace", "data_points")
            x_vals, y_vals = _xy_from_points(
                point_source,
                x_keys=("shift_ppm", "ppm", "x", "mz", "retention_time_min"),
                y_keys=("intensity", "signal", "y", "amplitude", "response", "integration_h"),
            )
        if (not x_vals or not y_vals) and spectrumish:
            peak_source = _first_list(root, "inferred_peaks", "peaks", "peak_table")
            x_vals, y_vals = _xy_from_points(
                peak_source,
                x_keys=("shift_ppm", "ppm", "x"),
                y_keys=("intensity", "integration_h", "area", "relative_intensity", "y"),
            )
        if not x_vals or not y_vals:
            continue
        if len(x_vals) != len(y_vals):
            return None
        x_label = str(root.get("x_label") or "ppm")
        y_label = str(root.get("y_label") or "intensity")
        reversed_x_axis = _bool_or_default(
            root.get("reversed_x_axis"),
            default=("ppm" in x_label.lower() or "shift" in x_label.lower()),
        )
        peaks = _records_from_list(_first_list(root, "inferred_peaks", "peaks", "peak_table"))
        overlays = _records_from_list(root.get("overlays"))
        reference_peaks = _records_from_list(root.get("reference_peaks"))
        if reference_peaks:
            overlays.append({"name": "reference_peaks", "peaks": reference_peaks})
        return (
            "spectrum_1d",
            {
                "x": x_vals,
                "y": y_vals,
                "x_label": x_label,
                "y_label": y_label,
                "reversed_x_axis": reversed_x_axis,
                "peaks": peaks or None,
                "overlays": overlays or None,
            },
            [],
        )
    return None


def _normalize_nmr_2d(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    for root in _candidate_roots(payload):
        peaks: list[dict[str, Any]] = []
        for peak in _records_from_list(root.get("peaks")):
            f2 = _first_number(
                peak, "f2_ppm", "observed_f2_ppm", "proton1_ppm", "linked_proton_ppm"
            )
            f1 = _first_number(
                peak,
                "f1_ppm",
                "observed_f1_ppm",
                "proton2_ppm",
                "carbon_ppm",
                "linked_carbon_ppm",
            )
            if f2 is None or f1 is None:
                continue
            normalized_peak: dict[str, Any] = {"f2_ppm": f2, "f1_ppm": f1}
            intensity = _first_number(peak, "intensity", "volume")
            if intensity is not None:
                normalized_peak["intensity"] = intensity
            label = _first_string(peak, "label", "assignment", "annotation")
            if label:
                normalized_peak["label"] = label
            status = _first_string(peak, "status", "evidence_label", "plausibility_label")
            if status:
                normalized_peak["status"] = status
            peaks.append(normalized_peak)
        if not peaks:
            continue
        experiment = (
            _first_string(root, "experiment", "experiment_detected", "experiment_type")
            or _first_string(peaks[0], "experiment")
            or "UNKNOWN"
        )
        return ("nmr_2d", {"peaks": peaks, "experiment": experiment}, [])
    if _type_contains(artifact_type, "nmr_2d", "nmr2d", "2d"):
        return None
    return None


def _normalize_fragmentation_tree(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    if not _type_contains(artifact_type, "fragmentation"):
        roots = _candidate_roots(payload)
    else:
        roots = _candidate_roots(payload)
    for root in roots:
        tree_root = _tree_root(root)
        nodes = _records_from_list(tree_root.get("nodes"))
        edges = _records_from_list(tree_root.get("edges"))
        if not nodes:
            continue
        diagnostic_hits = _list_or_none(
            tree_root.get("diagnostic_hits")
            or root.get("diagnostic_hits")
            or root.get("global_neutral_loss_hits")
        )
        contradictions = _list_or_none(
            tree_root.get("contradictions")
            or tree_root.get("contradiction_flags")
            or root.get("contradictions")
        )
        return (
            "fragmentation_tree",
            {
                "nodes": nodes,
                "edges": edges,
                "diagnostic_hits": diagnostic_hits,
                "contradictions": contradictions,
            },
            [],
        )
    return None


def _normalize_msms_mirror(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    if not _type_contains(artifact_type, "msms", "ms_ms"):
        return None
    for root in _candidate_roots(payload):
        observed = _mirror_peaks_from_list(
            _first_list(root, "observed_peaks", "peaks", "msms_peaks", "peak_list")
        )
        reference = _mirror_peaks_from_list(_first_list(root, "reference_peaks", "library_peaks"))
        fragment_matches = _collect_fragment_matches(root)
        if not observed and fragment_matches:
            observed = _mirror_peaks_from_list(fragment_matches)
        if not observed:
            continue
        adduct = root.get("adduct")
        if isinstance(adduct, dict):
            adduct_label = _first_string(adduct, "name", "label", "adduct", "formula")
        elif adduct is not None:
            adduct_label = str(adduct)
        else:
            adduct_label = None
        return (
            "msms_mirror",
            {
                "observed_peaks": observed,
                "reference_peaks": reference or None,
                "fragment_matches": fragment_matches or None,
                "precursor_mz": _first_number(root, "precursor_mz", "selected_msms_precursor_mz"),
                "adduct": adduct_label,
            },
            [],
        )
    return None


def _normalize_chromatogram(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    if not _type_contains(artifact_type, "lcms", "chromatogram"):
        return None
    for root in _candidate_roots(payload):
        traces = _normalize_existing_traces(root.get("traces"))
        chromatogram = _records_from_list(root.get("chromatogram"))
        tic_rt: list[float] = []
        tic_intensity: list[float] = []
        bpc_rt: list[float] = []
        bpc_intensity: list[float] = []
        for point in chromatogram:
            rt = _first_number(point, "retention_time_min", "rt", "time")
            tic = _first_number(point, "total_ion_current", "tic", "intensity")
            bpc = _first_number(point, "base_peak_intensity")
            if rt is not None and tic is not None:
                tic_rt.append(rt)
                tic_intensity.append(tic)
            if rt is not None and bpc is not None:
                bpc_rt.append(rt)
                bpc_intensity.append(bpc)
        if tic_rt:
            traces.append({"name": "TIC", "rt": tic_rt, "intensity": tic_intensity, "type": "tic"})
        if bpc_rt:
            traces.append(
                {
                    "name": "Base peak",
                    "rt": bpc_rt,
                    "intensity": bpc_intensity,
                    "type": "base_peak",
                }
            )
        traces.extend(_xic_traces(root.get("xic_points")))
        if not traces:
            continue
        features = _records_from_list(root.get("features"))
        best_feature = _dict_or_empty(root.get("best_feature"))
        if best_feature:
            features.insert(0, best_feature)
        return (
            "chromatogram",
            {
                "traces": traces,
                "features": features or None,
            },
            [],
        )
    return None


def _normalize_table(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    for root in _candidate_roots(payload):
        columns = root.get("columns")
        rows = root.get("rows")
        if isinstance(columns, list) and isinstance(rows, list):
            return (
                "table",
                {"columns": deepcopy(columns), "rows": [_record_or_list(row) for row in rows]},
                [],
            )
        if _type_contains(artifact_type, "lcms", "table"):
            for key in ("features", "groups", "families", "scans", "imported_spectra", "peaks"):
                records = _records_from_list(root.get(key))
                if not records:
                    continue
                return ("table", {"columns": _columns_from_records(records), "rows": records}, [])
    return None


def _normalize_metadata(
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[str]] | None:
    if _type_contains(artifact_type, "metadata"):
        return ("metadata", payload, [])
    return None


def _candidate_roots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    roots = [payload]
    for key in ("data", "preview", "result", "spectrum_preview", "artifact_json"):
        value = payload.get(key)
        if isinstance(value, dict):
            roots.append(value)
    return roots


def _tree_root(root: dict[str, Any]) -> dict[str, Any]:
    if _records_from_list(root.get("nodes")):
        return root
    best = _dict_or_empty(root.get("best_candidate"))
    if best:
        return best
    ranked = root.get("ranked_candidates")
    if isinstance(ranked, list):
        for item in ranked:
            if isinstance(item, dict) and _records_from_list(item.get("nodes")):
                return item
    return root


def _collect_fragment_matches(root: dict[str, Any]) -> list[dict[str, Any]]:
    matches = _records_from_list(root.get("fragment_matches"))
    best = _dict_or_empty(root.get("best_candidate"))
    matches.extend(_records_from_list(best.get("fragment_matches")))
    for candidate in _records_from_list(root.get("ranked_candidates")):
        matches.extend(_records_from_list(candidate.get("fragment_matches")))
    return matches


def _mirror_peaks_from_list(value: Any) -> list[dict[str, Any]]:
    peaks: list[dict[str, Any]] = []
    for item in _records_from_list(value):
        mz = _first_number(item, "mz", "peak_mz", "fragment_mz", "theoretical_mz")
        intensity = _first_number(item, "intensity", "relative_intensity")
        if mz is None or intensity is None:
            continue
        peak: dict[str, Any] = {"mz": mz, "intensity": intensity}
        label = _first_string(item, "label", "annotation", "loss_name", "fragment_type", "formula")
        if label:
            peak["label"] = label
        peaks.append(peak)
    return peaks


def _normalize_existing_traces(value: Any) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for item in _records_from_list(value):
        rt = _number_list(item.get("rt") or item.get("retention_time_min"))
        intensity = _number_list(item.get("intensity") or item.get("y"))
        if not rt or not intensity or len(rt) != len(intensity):
            continue
        trace: dict[str, Any] = {
            "name": str(item.get("name") or item.get("label") or "Trace"),
            "rt": rt,
            "intensity": intensity,
            "type": str(item.get("type") or "trace"),
        }
        mz = _first_number(item, "mz", "target_mz")
        if mz is not None:
            trace["mz"] = mz
        traces.append(trace)
    return traces


def _xic_traces(value: Any) -> list[dict[str, Any]]:
    grouped: dict[float, dict[str, list[float]]] = {}
    for point in _records_from_list(value):
        mz = _first_number(point, "target_mz", "mz", "observed_mz")
        rt = _first_number(point, "retention_time_min", "rt", "time")
        intensity = _first_number(point, "intensity", "total_ion_current", "signal")
        if mz is None or rt is None or intensity is None:
            continue
        bucket = grouped.setdefault(mz, {"rt": [], "intensity": []})
        bucket["rt"].append(rt)
        bucket["intensity"].append(intensity)
    return [
        {
            "name": f"XIC {mz:g}",
            "rt": values["rt"],
            "intensity": values["intensity"],
            "type": "xic",
            "mz": mz,
        }
        for mz, values in sorted(grouped.items())
    ]


def _xy_from_points(
    value: Any,
    *,
    x_keys: tuple[str, ...],
    y_keys: tuple[str, ...],
) -> tuple[list[float], list[float]]:
    x_vals: list[float] = []
    y_vals: list[float] = []
    for item in _records_from_list(value):
        x = _first_number(item, *x_keys)
        y = _first_number(item, *y_keys)
        if x is None or y is None:
            continue
        x_vals.append(x)
        y_vals.append(y)
    return x_vals, y_vals


def _columns_from_records(records: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)
    return columns


def _first_list(root: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = root.get(key)
        if isinstance(value, list):
            return deepcopy(value)
    return []


def _records_from_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            records.append(deepcopy(item))
        else:
            records.append({"value": deepcopy(item)})
    return records


def _record_or_list(value: Any) -> dict[str, Any] | list[Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if isinstance(value, list):
        return deepcopy(value)
    return {"value": deepcopy(value)}


def _list_or_none(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return deepcopy(value)
    return None


def _number_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    values: list[float] = []
    for item in value:
        number = _to_float(item)
        if number is None:
            return []
        values.append(number)
    return values


def _first_number(root: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in root:
            number = _to_float(root.get(key))
            if number is not None:
                return number
    return None


def _first_string(root: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = root.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return number


def _bool_or_default(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return default


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if str(item).strip()))


def _merged_provenance(
    payload: dict[str, Any],
    *,
    provenance: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    artifact_metadata = _dict_or_empty(payload.get("metadata"))
    for source in (
        payload.get("provenance"),
        payload.get("provenance_json"),
        artifact_metadata.get("provenance"),
        (metadata or {}).get("provenance_metadata") if isinstance(metadata, dict) else None,
        provenance,
    ):
        if isinstance(source, dict):
            merged.update(deepcopy(source))
    return merged


def _merged_metadata(payload: dict[str, Any], *, metadata: dict[str, Any] | None) -> dict[str, Any]:
    merged = _dict_or_empty(payload.get("metadata"))
    if isinstance(metadata, dict):
        merged.update(deepcopy(metadata))
    return merged


def _type_contains(artifact_type: str, *needles: str) -> bool:
    normalized = artifact_type.lower().replace("-", "_")
    return any(needle in normalized for needle in needles)


def _title_from_type(artifact_type: str) -> str:
    return artifact_type.replace("_", " ").strip().title() or "Visualization Artifact"
