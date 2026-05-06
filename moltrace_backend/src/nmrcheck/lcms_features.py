from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable

from .lcms_import import (
    LCMSImportError,
    _detect_format,
    _scan_tic,
    _sha256_bytes,
    parse_mzml,
    parse_mzxml,
    parse_processed_peak_table,
)
from .models import (
    LCMSChromatogramPoint,
    LCMSCoelutingIon,
    LCMSFeatureDetectionRequest,
    LCMSFeatureDetectionResult,
    LCMSFeaturePeak,
    LCMSFeaturePurityReport,
    LCMSLinkedMSMSSpectrum,
    LCMSXICPoint,
)


class LCMSFeatureDetectionError(ValueError):
    pass


@dataclass(frozen=True)
class _ScanPoint:
    scan_id: str
    rt: float
    intensity: float
    observed_mz: float | None = None


@dataclass(frozen=True)
class _DetectedSegment:
    start_idx: int
    end_idx: int


@dataclass
class _IonTrace:
    mz: float
    values: list[float]
    area: float
    max_intensity: float


def _effective_tolerance(target_mz: float, mz_tolerance_da: float, ppm_tolerance: float) -> float:
    return max(float(mz_tolerance_da), abs(float(target_mz)) * float(ppm_tolerance) / 1_000_000.0)


def _safe_float(value: object | None, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _rt_for_scan(index: int, retention_time_min: float | None) -> float:
    if retention_time_min is not None:
        return float(retention_time_min)
    # Use a deterministic scan-index pseudo-time when the source lacks RT metadata.
    return float(index)


def _load_scans(request: LCMSFeatureDetectionRequest, *, raw_bytes: bytes | None = None):
    source_text = request.source_text or ""
    warnings: list[str] = []
    detected_format, detection_warnings = _detect_format(request.filename, source_text, request.source_format)
    warnings.extend(detection_warnings)
    file_sha = _sha256_bytes(raw_bytes if raw_bytes is not None else source_text.encode("utf-8", errors="replace"))
    if detected_format == "unsupported_vendor":
        raise LCMSFeatureDetectionError(
            "Feature detection needs mzML/mzXML or processed LC-MS peak tables. Convert the vendor raw file first and preserve the original raw file hash."
        )
    try:
        if detected_format == "mzML":
            scans, parser_warnings = parse_mzml(source_text)
            warnings.extend(parser_warnings)
        elif detected_format == "mzXML":
            scans, parser_warnings = parse_mzxml(source_text)
            warnings.extend(parser_warnings)
        else:
            scans = parse_processed_peak_table(source_text)
            detected_format = "processed_peak_table"
    except LCMSImportError as exc:
        raise LCMSFeatureDetectionError(str(exc)) from exc
    if not scans:
        raise LCMSFeatureDetectionError("No LC-MS scans were available for feature detection.")
    return scans, detected_format, file_sha, warnings


def _chromatogram_points(scans) -> list[LCMSChromatogramPoint]:
    points: list[LCMSChromatogramPoint] = []
    for idx, scan in enumerate(scans):
        tic = _scan_tic(scan)
        base_mz = None
        base_intensity = None
        if scan.peaks:
            base_mz, base_intensity = max(scan.peaks, key=lambda pair: pair[1])
        points.append(
            LCMSChromatogramPoint(
                scan_id=scan.scan_id,
                ms_level=scan.ms_level,
                retention_time_min=scan.retention_time_min if scan.retention_time_min is not None else float(idx),
                total_ion_current=round(tic, 6),
                base_peak_mz=round(base_mz, 6) if base_mz is not None else None,
                base_peak_intensity=round(base_intensity, 6) if base_intensity is not None else None,
            )
        )
    return points


def _cluster_peak_masses(peaks: Iterable[tuple[float, float]], *, mz_tolerance_da: float, ppm_tolerance: float, max_targets: int) -> list[float]:
    clusters: list[dict[str, float]] = []
    for mz, intensity in sorted(peaks, key=lambda item: item[0]):
        if mz <= 0 or intensity <= 0:
            continue
        matched = False
        for cluster in clusters:
            centroid = cluster["mz_sum"] / max(cluster["intensity_sum"], 1e-12)
            if abs(mz - centroid) <= _effective_tolerance(centroid, mz_tolerance_da, ppm_tolerance):
                cluster["mz_sum"] += mz * intensity
                cluster["intensity_sum"] += intensity
                cluster["max_intensity"] = max(cluster["max_intensity"], intensity)
                matched = True
                break
        if not matched:
            clusters.append({"mz_sum": mz * intensity, "intensity_sum": intensity, "max_intensity": intensity})
    clusters.sort(key=lambda c: (c["intensity_sum"], c["max_intensity"]), reverse=True)
    targets: list[float] = []
    for cluster in clusters[:max_targets]:
        if cluster["intensity_sum"] > 0:
            targets.append(round(cluster["mz_sum"] / cluster["intensity_sum"], 6))
    return targets


def _parse_target_text(text: str | None) -> list[float]:
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
            raise LCMSFeatureDetectionError(f"Target m/z value {token!r} could not be parsed.") from exc
        if value <= 0:
            raise LCMSFeatureDetectionError("Target m/z values must be positive.")
        values.append(value)
    return values


def _moving_average(values: list[float], window: int) -> list[float]:
    if window <= 1 or len(values) <= 2:
        return list(values)
    window = max(1, min(int(window), len(values)))
    if window % 2 == 0:
        window += 1
    half = window // 2
    smoothed: list[float] = []
    for i in range(len(values)):
        left = max(0, i - half)
        right = min(len(values), i + half + 1)
        smoothed.append(sum(values[left:right]) / max(right - left, 1))
    return smoothed


def _noise_estimate(values: list[float]) -> float:
    positives = [v for v in values if v > 0]
    if not positives:
        return 1.0
    sorted_vals = sorted(positives)
    low_count = max(1, len(sorted_vals) // 4)
    low = sorted_vals[:low_count]
    if len(low) == 1:
        return max(low[0] * 0.1, 1.0)
    median = statistics.median(low)
    mad = statistics.median(abs(v - median) for v in low)
    return max(median + 3.0 * mad, 1.0)


def _integrate(points: list[_ScanPoint], start_idx: int, end_idx: int) -> float:
    if end_idx < start_idx:
        return 0.0
    segment = points[start_idx : end_idx + 1]
    if len(segment) == 1:
        return segment[0].intensity
    area = 0.0
    for a, b in zip(segment, segment[1:]):
        dt = max(b.rt - a.rt, 0.0)
        area += ((a.intensity + b.intensity) / 2.0) * (dt if dt > 0 else 1.0)
    return area


def _extract_xic(ms1_scans, target_mz: float, *, mz_tolerance_da: float, ppm_tolerance: float) -> list[_ScanPoint]:
    tolerance = _effective_tolerance(target_mz, mz_tolerance_da, ppm_tolerance)
    points: list[_ScanPoint] = []
    for idx, scan in enumerate(ms1_scans):
        intensity = 0.0
        mz_weight = 0.0
        for mz, peak_intensity in scan.peaks:
            if abs(mz - target_mz) <= tolerance:
                intensity += peak_intensity
                mz_weight += mz * peak_intensity
        observed = mz_weight / intensity if intensity > 0 else None
        points.append(_ScanPoint(scan_id=scan.scan_id, rt=_rt_for_scan(idx, scan.retention_time_min), intensity=float(intensity), observed_mz=observed))
    points.sort(key=lambda p: p.rt)
    return points


def _find_segments(points: list[_ScanPoint], *, smoothing_window: int, min_relative_height: float, min_peak_height: float, min_scans_per_feature: int) -> list[_DetectedSegment]:
    if not points:
        return []
    values = [p.intensity for p in points]
    smoothed = _moving_average(values, smoothing_window)
    max_intensity = max(smoothed) if smoothed else 0.0
    if max_intensity <= 0:
        return []
    threshold = max(float(min_peak_height), max_intensity * float(min_relative_height) / 100.0, _noise_estimate(values))
    segments: list[_DetectedSegment] = []
    start: int | None = None
    for i, intensity in enumerate(smoothed):
        if intensity >= threshold:
            if start is None:
                start = i
        elif start is not None:
            end = i - 1
            if end - start + 1 >= min_scans_per_feature:
                segments.append(_DetectedSegment(start, end))
            start = None
    if start is not None:
        end = len(points) - 1
        if end - start + 1 >= min_scans_per_feature:
            segments.append(_DetectedSegment(start, end))
    return segments


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    da = [x - mean_a for x in a]
    db = [x - mean_b for x in b]
    denom_a = sum(x * x for x in da) ** 0.5
    denom_b = sum(x * x for x in db) ** 0.5
    denom = denom_a * denom_b
    if denom <= 1e-12:
        return None
    return sum(x * y for x, y in zip(da, db)) / denom


def _cluster_window_ions(ms1_scans, target_mz: float, start_rt: float, end_rt: float, *, mz_tolerance_da: float, ppm_tolerance: float) -> dict[float, list[tuple[str, float, float]]]:
    clusters: dict[float, list[tuple[str, float, float]]] = {}
    for idx, scan in enumerate(ms1_scans):
        rt = _rt_for_scan(idx, scan.retention_time_min)
        if rt < start_rt or rt > end_rt:
            continue
        for mz, intensity in scan.peaks:
            if intensity <= 0:
                continue
            matched_key = None
            for key in list(clusters.keys()):
                if abs(mz - key) <= _effective_tolerance(key, mz_tolerance_da, ppm_tolerance):
                    matched_key = key
                    break
            if matched_key is None:
                clusters[round(mz, 6)] = [(scan.scan_id, rt, intensity)]
            else:
                clusters[matched_key].append((scan.scan_id, rt, intensity))
    return clusters


def _area_from_trace(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    values = sorted(values, key=lambda item: item[0])
    if len(values) == 1:
        return values[0][1]
    area = 0.0
    for (rt_a, y_a), (rt_b, y_b) in zip(values, values[1:]):
        dt = max(rt_b - rt_a, 0.0)
        area += ((y_a + y_b) / 2.0) * (dt if dt > 0 else 1.0)
    return area


def _purity_report(ms1_scans, feature_id: str, target_mz: float, target_points: list[_ScanPoint], start_rt: float, end_rt: float, *, apex_rt: float, target_area: float, top_ions: int, mz_tolerance_da: float, ppm_tolerance: float) -> LCMSFeaturePurityReport:
    clusters = _cluster_window_ions(ms1_scans, target_mz, start_rt, end_rt, mz_tolerance_da=mz_tolerance_da, ppm_tolerance=ppm_tolerance)
    # Build target vector and coeluting vectors over the same scans.
    target_by_scan = {p.scan_id: p.intensity for p in target_points if start_rt <= p.rt <= end_rt}
    scan_ids = [p.scan_id for p in target_points if start_rt <= p.rt <= end_rt]
    target_vector = [target_by_scan.get(scan_id, 0.0) for scan_id in scan_ids]
    ion_traces: list[_IonTrace] = []
    target_tol = _effective_tolerance(target_mz, mz_tolerance_da, ppm_tolerance)
    for mz_key, entries in clusters.items():
        # Exclude the target ion cluster from the coeluting list.
        if abs(mz_key - target_mz) <= target_tol:
            continue
        by_scan = {scan_id: 0.0 for scan_id in scan_ids}
        for scan_id, _rt, intensity in entries:
            if scan_id in by_scan:
                by_scan[scan_id] += intensity
        vector = [by_scan.get(scan_id, 0.0) for scan_id in scan_ids]
        values_for_area = []
        for scan_id, rt, intensity in entries:
            if scan_id in by_scan:
                values_for_area.append((rt, intensity))
        area = _area_from_trace(values_for_area)
        if area <= 0:
            continue
        ion_traces.append(_IonTrace(mz=mz_key, values=vector, area=area, max_intensity=max(vector) if vector else 0.0))
    ion_traces.sort(key=lambda trace: trace.area, reverse=True)
    coeluting: list[LCMSCoelutingIon] = []
    total_area = max(target_area, 0.0) + sum(trace.area for trace in ion_traces)
    for trace in ion_traces[:top_ions]:
        coeluting.append(
            LCMSCoelutingIon(
                mz=round(trace.mz, 6),
                area=round(trace.area, 6),
                relative_area_percent=round((trace.area / total_area * 100.0) if total_area > 0 else 0.0, 4),
                max_intensity=round(trace.max_intensity, 6),
                correlation_to_target=_pearson(target_vector, trace.values),
            )
        )
    purity_percent = (target_area / total_area * 100.0) if total_area > 0 else 0.0
    if not target_points or target_area <= 0:
        label = "not_assessed"
    elif purity_percent >= 90.0:
        label = "high_purity"
    elif purity_percent >= 60.0:
        label = "possible_coelution"
    else:
        label = "poor_peak_purity"
    warnings: list[str] = []
    if coeluting and coeluting[0].relative_area_percent >= 25.0:
        warnings.append(f"Large coeluting ion at m/z {coeluting[0].mz:.4f} contributes about {coeluting[0].relative_area_percent:.1f}% of the local ion area.")
    return LCMSFeaturePurityReport(
        feature_id=feature_id,
        target_mz=round(target_mz, 6),
        apex_rt_min=round(apex_rt, 6),
        rt_window_start_min=round(start_rt, 6),
        rt_window_end_min=round(end_rt, 6),
        purity_percent=round(purity_percent, 4),
        label=label,  # type: ignore[arg-type]
        top_coeluting_ions=coeluting,
        warnings=warnings,
    )


def _link_msms(ms2_scans, target_mz: float, apex_rt: float, start_rt: float, end_rt: float, *, mz_tolerance_da: float, ppm_tolerance: float, max_links: int = 5) -> list[LCMSLinkedMSMSSpectrum]:
    links: list[LCMSLinkedMSMSSpectrum] = []
    tolerance = _effective_tolerance(target_mz, mz_tolerance_da, ppm_tolerance)
    for scan in ms2_scans:
        if scan.precursor_mz is None:
            continue
        rt = scan.retention_time_min
        precursor_error = scan.precursor_mz - target_mz
        if abs(precursor_error) > tolerance:
            continue
        rt_distance = abs((rt if rt is not None else apex_rt) - apex_rt)
        within_window = rt is None or (start_rt <= rt <= end_rt)
        if not within_window and rt_distance > max((end_rt - start_rt), 0.1):
            continue
        links.append(
            LCMSLinkedMSMSSpectrum(
                scan_id=scan.scan_id,
                precursor_mz=round(scan.precursor_mz, 6),
                retention_time_min=rt,
                precursor_error_da=round(precursor_error, 6),
                precursor_error_ppm=round((precursor_error / target_mz) * 1_000_000.0, 4),
                peak_count=len(scan.peaks),
                total_ion_current=round(_scan_tic(scan), 6),
            )
        )
    links.sort(key=lambda link: (abs(link.precursor_error_da), abs(_safe_float(link.retention_time_min, apex_rt) - apex_rt)))
    return links[:max_links]


def _feature_label(snr: float, purity_label: str, apex_intensity: float) -> str:
    if apex_intensity <= 0 or snr < 3.0:
        return "weak_or_no_feature"
    if purity_label in {"poor_peak_purity", "possible_coelution"}:
        return "possible_coelution"
    return "clean_feature"


def detect_lcms_features(request: LCMSFeatureDetectionRequest, *, raw_bytes: bytes | None = None) -> LCMSFeatureDetectionResult:
    scans, detected_format, file_sha, warnings = _load_scans(request, raw_bytes=raw_bytes)
    scans = scans[: request.max_scans_to_report] if len(scans) > request.max_scans_to_report else scans
    ms1_scans = [scan for scan in scans if scan.ms_level == 1]
    ms2_scans = [scan for scan in scans if scan.ms_level == 2]
    if not ms1_scans:
        raise LCMSFeatureDetectionError("LC-MS feature detection requires at least one MS1 scan.")
    targets = list(request.target_mz_values or [])
    targets.extend(_parse_target_text(request.target_mz_text))
    # Preserve input order while removing near-duplicates.
    deduped: list[float] = []
    for target in targets:
        if target <= 0:
            raise LCMSFeatureDetectionError("Target m/z values must be positive.")
        if not any(abs(target - existing) <= _effective_tolerance(existing, request.mz_tolerance_da, request.ppm_tolerance) for existing in deduped):
            deduped.append(float(target))
    targets = deduped
    if not targets:
        aggregate = []
        for scan in ms1_scans:
            aggregate.extend(scan.peaks)
        targets = _cluster_peak_masses(aggregate, mz_tolerance_da=request.mz_tolerance_da, ppm_tolerance=request.ppm_tolerance, max_targets=request.max_features)
        if targets:
            warnings.append("No target m/z values were supplied; feature targets were auto-selected from the most intense MS1 ion clusters.")
    if not targets:
        raise LCMSFeatureDetectionError("No target m/z values were available and auto-target selection found no MS1 peaks.")

    chromatogram = _chromatogram_points(scans)
    all_features: list[LCMSFeaturePeak] = []
    all_xics: list[LCMSXICPoint] = []
    feature_index = 1
    for target_mz in targets[: request.max_features]:
        xic_points = _extract_xic(ms1_scans, target_mz, mz_tolerance_da=request.mz_tolerance_da, ppm_tolerance=request.ppm_tolerance)
        max_xic = max((p.intensity for p in xic_points), default=0.0)
        for point in xic_points:
            all_xics.append(
                LCMSXICPoint(
                    target_mz=round(target_mz, 6),
                    scan_id=point.scan_id,
                    retention_time_min=round(point.rt, 6),
                    intensity=round(point.intensity, 6),
                    relative_intensity=round((point.intensity / max_xic * 100.0) if max_xic > 0 else 0.0, 4),
                )
            )
        segments = _find_segments(
            xic_points,
            smoothing_window=request.smoothing_window,
            min_relative_height=request.min_relative_feature_height,
            min_peak_height=request.min_peak_height,
            min_scans_per_feature=request.min_scans_per_feature,
        )
        if not segments:
            apex_point = max(xic_points, key=lambda p: p.intensity) if xic_points else _ScanPoint(scan_id="none", rt=0.0, intensity=0.0)
            feature_id = f"F{feature_index:03d}"
            purity = LCMSFeaturePurityReport(
                feature_id=feature_id,
                target_mz=round(target_mz, 6),
                apex_rt_min=round(apex_point.rt, 6),
                rt_window_start_min=round(apex_point.rt, 6),
                rt_window_end_min=round(apex_point.rt, 6),
                purity_percent=0.0,
                label="not_assessed",
                top_coeluting_ions=[],
                warnings=["No chromatographic feature passed the configured height and scan-count thresholds."],
            )
            all_features.append(
                LCMSFeaturePeak(
                    feature_id=feature_id,
                    target_mz=round(target_mz, 6),
                    observed_mz=None,
                    apex_rt_min=round(apex_point.rt, 6),
                    start_rt_min=round(apex_point.rt, 6),
                    end_rt_min=round(apex_point.rt, 6),
                    apex_intensity=round(apex_point.intensity, 6),
                    area=0.0,
                    width_min=0.0,
                    scan_count=0,
                    signal_to_noise=0.0,
                    purity=purity,
                    linked_msms_spectra=[],
                    label="weak_or_no_feature",
                    evidence_summary=[f"No reliable XIC feature was detected for target m/z {target_mz:.6f}."],
                    warnings=purity.warnings,
                )
            )
            feature_index += 1
            continue
        for seg in segments:
            segment_points = xic_points[seg.start_idx : seg.end_idx + 1]
            apex_point = max(segment_points, key=lambda p: p.intensity)
            area = _integrate(xic_points, seg.start_idx, seg.end_idx)
            start_rt = segment_points[0].rt
            end_rt = segment_points[-1].rt
            if request.purity_rt_window_min > 0:
                half = request.purity_rt_window_min / 2.0
                start_rt = max(0.0, min(start_rt, apex_point.rt - half))
                end_rt = max(end_rt, apex_point.rt + half)
            observed_values = [p.observed_mz for p in segment_points if p.observed_mz is not None and p.intensity > 0]
            observed_mz = sum(observed_values) / len(observed_values) if observed_values else None
            snr = apex_point.intensity / _noise_estimate([p.intensity for p in xic_points])
            feature_id = f"F{feature_index:03d}"
            purity = _purity_report(
                ms1_scans,
                feature_id,
                target_mz,
                xic_points,
                start_rt,
                end_rt,
                apex_rt=apex_point.rt,
                target_area=area,
                top_ions=request.top_coeluting_ions,
                mz_tolerance_da=request.mz_tolerance_da,
                ppm_tolerance=request.ppm_tolerance,
            )
            links = _link_msms(
                ms2_scans,
                target_mz,
                apex_point.rt,
                start_rt,
                end_rt,
                mz_tolerance_da=request.mz_tolerance_da,
                ppm_tolerance=request.ppm_tolerance,
            )
            label = _feature_label(snr, purity.label, apex_point.intensity)
            summary = [
                f"XIC target m/z {target_mz:.6f} produced a feature at RT {apex_point.rt:.3f} min.",
                f"Apex intensity {apex_point.intensity:.3g}; integrated area {area:.3g}; local purity {purity.purity_percent:.1f}%.",
            ]
            if links:
                summary.append(f"Linked {len(links)} MS/MS scan(s) by precursor m/z and retention time.")
            if purity.label != "high_purity":
                summary.append("Human review should inspect coeluting ions before using this feature as isolated evidence.")
            all_features.append(
                LCMSFeaturePeak(
                    feature_id=feature_id,
                    target_mz=round(target_mz, 6),
                    observed_mz=round(observed_mz, 6) if observed_mz is not None else None,
                    apex_rt_min=round(apex_point.rt, 6),
                    start_rt_min=round(start_rt, 6),
                    end_rt_min=round(end_rt, 6),
                    apex_intensity=round(apex_point.intensity, 6),
                    area=round(area, 6),
                    width_min=round(max(end_rt - start_rt, 0.0), 6),
                    scan_count=len(segment_points),
                    signal_to_noise=round(snr, 4),
                    purity=purity,
                    linked_msms_spectra=links,
                    label=label,  # type: ignore[arg-type]
                    evidence_summary=summary,
                    warnings=purity.warnings,
                )
            )
            feature_index += 1
    all_features.sort(key=lambda f: (f.label != "clean_feature", -f.area, f.target_mz))
    # Re-rank IDs are stable enough; keep feature_id assigned in detection order.
    clean = sum(1 for f in all_features if f.label == "clean_feature")
    coeluting = sum(1 for f in all_features if f.label == "possible_coelution")
    weak = sum(1 for f in all_features if f.label == "weak_or_no_feature")
    best = all_features[0] if all_features else None
    label = "ready_for_downstream_ms" if clean or coeluting else "metadata_only"
    actions = [
        "Review clean-feature and possible-coelution labels before assigning peaks to candidate structures.",
        "Copy the best feature m/z into HRMS and the selected MS/MS peak list into MS/MS annotation only after checking peak purity.",
        "Store the file SHA-256 and feature-detection settings in the regulatory report processing history.",
    ]
    if coeluting:
        warnings.append("One or more detected LC-MS features show possible coelution; use peak purity evidence before candidate scoring.")
    if weak:
        warnings.append("One or more requested target m/z values did not produce a robust chromatographic feature.")
    notes = [
        "Feature detection uses processed/open-format LC-MS views and does not mutate the raw source data.",
        "Peak purity is a local chromatographic estimate, not proof of chemical identity or structural correctness.",
    ]
    return LCMSFeatureDetectionResult(
        sample_id=request.sample_id,
        filename=request.filename,
        source_format=detected_format,  # type: ignore[arg-type]
        file_sha256=file_sha,
        immutable_raw_data=True,
        label=label,  # type: ignore[arg-type]
        scan_count=len(scans),
        ms1_scan_count=len(ms1_scans),
        ms2_scan_count=len(ms2_scans),
        target_count=len(targets),
        feature_count=len(all_features),
        clean_feature_count=clean,
        coeluting_feature_count=coeluting,
        weak_feature_count=weak,
        best_feature=best,
        features=all_features,
        xic_points=all_xics[: request.max_xic_points],
        chromatogram=chromatogram,
        recommended_next_actions=actions,
        warnings=warnings,
        notes=notes,
        metadata={
            "parser_version": "week36_lcms_feature_detection_v1",
            "mz_tolerance_da": request.mz_tolerance_da,
            "ppm_tolerance": request.ppm_tolerance,
            "min_relative_feature_height": request.min_relative_feature_height,
            "min_peak_height": request.min_peak_height,
            "min_scans_per_feature": request.min_scans_per_feature,
            "purity_rt_window_min": request.purity_rt_window_min,
            "target_mz_values": targets,
        },
    )
