from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _archive_member_name(filename: str | None) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return "raw/original_archive.tar.gz"
    if lower.endswith(".zip"):
        return "raw/original_archive.zip"
    return "raw/original_archive.bin"


def _peak_list_csv(peaks: Iterable[Any]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["shift_ppm", "multiplicity", "integration_h", "j_values_hz", "intensity", "assignment"])
    for peak in peaks:
        if isinstance(peak, Mapping):
            row = peak
        elif hasattr(peak, "model_dump"):
            row = peak.model_dump(mode="json")
        else:
            row = dict(getattr(peak, "__dict__", {}))
        writer.writerow(
            [
                row.get("shift_ppm"),
                row.get("multiplicity"),
                row.get("integration_h"),
                ";".join(str(value) for value in row.get("j_values_hz", []) or []),
                row.get("intensity"),
                row.get("assignment"),
            ]
        )
    return output.getvalue().encode("utf-8")


def _safe_payload(payload: Any) -> Any:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return payload


def export_raw_fid_analysis_package(
    *,
    raw_archive: Any,
    original_archive_bytes: bytes | None,
    original_filename: str | None = None,
    analysis: Any | None = None,
    processing_recipe: Mapping[str, Any] | None = None,
    acquisition_metadata: Mapping[str, Any] | None = None,
    peak_list: Iterable[Any] | None = None,
    spectrum_preview: Any | None = None,
    evidence_report: Any | None = None,
    audit_trail: Iterable[Any] | None = None,
    warnings: Iterable[str] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Package raw FID provenance and derivative analysis without modifying vendor data."""

    raw_archive_payload = _safe_payload(raw_archive)
    filename = original_filename or raw_archive_payload.get("filename") or "raw_fid_archive"
    files: list[dict[str, Any]] = []
    required_hashes: dict[str, str] = {}

    def add_bytes(package: zipfile.ZipFile, path: str, payload: bytes, *, role: str | None = None) -> None:
        package.writestr(path, payload)
        digest = _sha256_bytes(payload)
        item = {"path": path, "byte_size": len(payload), "sha256": digest}
        if role:
            item["role"] = role
        files.append(item)
        if path in {
            "analysis/analysis.json",
            "analysis/processing_recipe.json",
            "analysis/peak_list.csv",
            "analysis/evidence_report.json",
        } or role == "original_raw_archive":
            required_hashes[path] = digest

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
        if original_archive_bytes is not None:
            add_bytes(
                package,
                _archive_member_name(filename),
                original_archive_bytes,
                role="original_raw_archive",
            )
        else:
            add_bytes(
                package,
                "raw/ORIGINAL_ARCHIVE_NOT_INCLUDED.txt",
                (
                    "The immutable raw archive was not embedded in this package. "
                    "Use manifest.json and raw archive provenance to locate and verify it."
                ).encode("utf-8"),
            )
        add_bytes(package, "analysis/analysis.json", _json_bytes(_safe_payload(analysis)))
        add_bytes(package, "analysis/processing_recipe.json", _json_bytes(dict(processing_recipe or {})))
        add_bytes(package, "analysis/acquisition_metadata.json", _json_bytes(dict(acquisition_metadata or {})))
        add_bytes(package, "analysis/peak_list.csv", _peak_list_csv(peak_list or []))
        add_bytes(package, "analysis/spectrum_preview.json", _json_bytes(_safe_payload(spectrum_preview)))
        evidence_payload = _safe_payload(evidence_report)
        add_bytes(package, "analysis/evidence_report.json", _json_bytes(evidence_payload))
        audit_payload = [_safe_payload(event) for event in (audit_trail or [])]
        add_bytes(package, "analysis/audit_trail.json", _json_bytes(audit_payload))

        manifest = {
            "package_schema": "nmrcheck.raw_fid_analysis_package.v1",
            "created_at": datetime.now(UTC).isoformat(),
            "raw_archive": raw_archive_payload,
            "raw_archive_id": raw_archive_payload.get("raw_archive_id") or raw_archive_payload.get("sha256"),
            "raw_archive_db_id": raw_archive_payload.get("id"),
            "original_filename": filename,
            "original_archive_included": original_archive_bytes is not None,
            "hashes": required_hashes,
            "files": files,
            "warnings": list(warnings or []),
            "non_destructive_guarantees": {
                "original_fid_replaced": False,
                "processed_files_written_into_raw_vendor_folder": False,
                "processing_outputs_are_derivative": True,
            },
        }
        manifest_bytes = _json_bytes(manifest)
        package.writestr("manifest.json", manifest_bytes)
        files.append(
            {
                "path": "manifest.json",
                "byte_size": len(manifest_bytes),
                "sha256": _sha256_bytes(manifest_bytes),
            }
        )
    archive_buffer.seek(0)
    return archive_buffer.getvalue(), manifest
