"""Fixture validation runner for the Prompt 1/2 raw-FID sidecar.

The report produced here is deliberately observational.  It compares the
current, user-visible legacy raw-FID processor with the newer Prompt 1/2
reader/preprocess sidecar, but it does not activate or replace either path in
SpectraCheck.  This gives us hard fixture data before any future wiring work.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .fid import fid_settings_from_preset, process_bruker_1d_zip
from .fid_pipeline_adapter import (
    build_prompt_pipeline_sidecar,
    build_prompt_pipeline_validation_report,
)
from .models import FIDPreviewReport

REPORT_VERSION = "raw_fid_prompt_sidecar_fixture_report_v1"
SHADOW_COMPARISON_VERSION = "raw_fid_prompt_shadow_comparison_v1"
SHADOW_COMPARISON_ARTIFACT_VERSION = "raw_fid_prompt_shadow_comparison_artifact_v1"
RELEASE_READINESS_ARTIFACT_VERSION = "raw_fid_prompt_release_readiness_artifact_v1"
PROMOTION_GATE_VERSION = "raw_fid_prompt_manual_promotion_gate_v1"
PROVENANCE_VERSION = "raw_fid_prompt_report_provenance_v1"
PROVENANCE_ARTIFACT_VERSION = "raw_fid_prompt_provenance_artifact_v1"
DEFAULT_OUTPUT_DIRNAME = "raw_fid_prompt_validation"
CSV_COLUMNS = [
    "fixture_id",
    "source",
    "vendor",
    "nucleus",
    "archive",
    "archive_sha256",
    "archive_size_bytes",
    "row_status",
    "legacy_status",
    "prompt_status",
    "validation_status",
    "legacy_peak_count",
    "prompt_peak_count",
    "reference_peak_count",
    "reference_peak_ppm_count",
    "reference_ppm_tolerance",
    "legacy_reference_peak_count_delta",
    "prompt_reference_peak_count_delta",
    "peak_count_tolerance",
    "legacy_peak_count_within_reference_tolerance",
    "prompt_peak_count_within_reference_tolerance",
    "prompt_reference_ppm_checked_count",
    "prompt_reference_ppm_max_error",
    "prompt_reference_ppm_mean_error",
    "prompt_reference_ppm_within_tolerance",
    "peak_count_delta_legacy_prompt",
    "legacy_point_count",
    "prompt_point_count",
    "point_count_delta",
    "prompt_ppm_min",
    "prompt_ppm_max",
    "ppm_min_abs_delta",
    "ppm_max_abs_delta",
    "phase_delta_degrees",
    "baseline_legacy_method",
    "baseline_prompt_method",
    "baseline_prompt_rmse_fraction_full_scale",
    "prompt_hash_present",
    "prompt_runtime_ms",
    "prompt_runtime_within_target",
    "validation_visibility",
    "safe_to_activate",
    "activation_readiness_status",
    "activation_readiness_gate_failures",
    "activation_readiness_gate_reviews",
    "failure_reasons",
]


def backend_root() -> Path:
    """Return the moltrace_backend root from the installed source tree."""

    return Path(__file__).resolve().parents[2]


def build_fixture_validation_report(
    *,
    nmrshiftdb2_root: Path | None = None,
    varian_root: Path | None = None,
    include_varian: bool = True,
    limit: int | None = None,
    strict: bool = False,
    progress: bool = False,
) -> dict[str, Any]:
    """Build a compact comparison report over Bruker and Varian fixtures."""

    root = backend_root()
    bruker_root = nmrshiftdb2_root or root / "tests" / "fixtures" / "nmrshiftdb2"
    varian_fixture_root = (
        varian_root or root / "tests" / "fixtures" / "nmrglue" / "varian"
    )
    fixtures = list(_load_nmrshiftdb2_fixtures(bruker_root))
    if limit is not None:
        fixtures = fixtures[: max(0, int(limit))]
    if include_varian:
        fixtures.append(_load_varian_fixture(varian_fixture_root))

    generated_at = datetime.now(UTC).isoformat()
    rows = []
    for index, fixture in enumerate(fixtures, start=1):
        if progress:
            print(
                f"[{index}/{len(fixtures)}] validating {fixture['fixture_id']} "
                f"({fixture['vendor']} {fixture['nucleus']})",
                flush=True,
            )
        rows.append(_validate_fixture(fixture, strict=strict))
    summary = _summarize_rows(rows)
    activation_readiness = _activation_readiness_summary(rows, summary)
    shadow_comparison = shadow_comparison_summary(rows, summary)
    report = {
        "version": REPORT_VERSION,
        "generated_at": generated_at,
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "activation_policy": "reporting_only_no_runtime_wiring",
        "activation_readiness": activation_readiness,
        "shadow_comparison_summary": shadow_comparison,
        "fixture_count": len(rows),
        "summary": summary,
        "rows": rows,
    }
    report["reporting_only_smoke"] = reporting_only_smoke_summary(report)
    report["promotion_gate"] = promotion_gate_summary(report)
    attach_report_provenance(
        report,
        include_varian=include_varian,
        limit=limit,
        strict=strict,
        nmrshiftdb2_root=bruker_root,
        varian_root=varian_fixture_root if include_varian else None,
    )
    return report


def attach_report_provenance(
    report: dict[str, Any],
    *,
    include_varian: bool | None,
    limit: int | None,
    strict: bool = False,
    nmrshiftdb2_root: Path | None = None,
    varian_root: Path | None = None,
    route_policy: str | None = None,
) -> dict[str, Any]:
    """Attach deterministic traceability metadata to a fixture report."""

    report.pop("provenance", None)
    rows = [row for row in report.get("rows") or [] if isinstance(row, Mapping)]
    fixture_identity = [
        {
            key: row.get(key)
            for key in (
                "fixture_id",
                "source",
                "vendor",
                "nucleus",
                "archive",
                "archive_sha256",
                "archive_size_bytes",
                "reference_peak_count",
                "reference_peak_ppm_count",
                "reference_ppm_tolerance",
                "peak_count_tolerance",
            )
        }
        for row in rows
    ]
    stable_rows = [_stable_row_for_hash(row) for row in rows]
    provenance = {
        "version": PROVENANCE_VERSION,
        "generated_at": report.get("generated_at"),
        "report_version": report.get("version"),
        "route_policy": route_policy or report.get("route_policy") or "offline_builder",
        "parameters": {
            "include_varian": include_varian,
            "limit": limit,
            "strict": strict,
        },
        "fixture_roots": {
            "nmrshiftdb2": str(nmrshiftdb2_root) if nmrshiftdb2_root else None,
            "varian": str(varian_root) if varian_root else None,
        },
        "fixture_count": report.get("fixture_count"),
        "fixture_identity_sha256": _sha256_json(fixture_identity),
        "row_fingerprint_sha256": _sha256_json(stable_rows),
        "row_payload_sha256": _sha256_json(rows),
        "summary_sha256": _sha256_json(report.get("summary") or {}),
        "activation_readiness_sha256": _sha256_json(
            report.get("activation_readiness") or {}
        ),
        "shadow_comparison_sha256": _sha256_json(
            report.get("shadow_comparison_summary") or {}
        ),
        "reporting_only_smoke_sha256": _sha256_json(
            report.get("reporting_only_smoke") or {}
        ),
        "promotion_gate_sha256": _sha256_json(report.get("promotion_gate") or {}),
        "requested_by_sha256": _sha256_json(report.get("requested_by") or {}),
        "runtime_effect_sha256": _sha256_json(report.get("runtime_effect") or {}),
    }
    provenance["report_payload_sha256"] = _sha256_json(report)
    report["provenance"] = provenance
    return report


def write_validation_outputs(
    report: Mapping[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write report JSON, CSV, and provenance checksum summaries."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "raw_fid_prompt_sidecar_fixture_report.json"
    csv_path = output_dir / "raw_fid_prompt_sidecar_fixture_report.csv"
    json_path.write_text(
        json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = list(report.get("rows") or [])
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_cell(row.get(column)) for column in CSV_COLUMNS})
    shadow_json_path, shadow_csv_path = write_validation_shadow_comparison_artifacts(
        report,
        output_dir,
    )
    readiness_path = write_validation_release_readiness_artifact(report, output_dir)
    write_validation_provenance_artifacts(
        report,
        output_dir,
        json_path=json_path,
        csv_path=csv_path,
        shadow_json_path=shadow_json_path,
        shadow_csv_path=shadow_csv_path,
        release_readiness_path=readiness_path,
    )
    return json_path, csv_path


def write_validation_shadow_comparison_artifacts(
    report: Mapping[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write compact CI/admin shadow comparison artifacts.

    These files are review aids only.  They summarize how the Prompt 1/2
    sidecar compared with fixture references without creating any runtime
    activation path.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    shadow = report.get("shadow_comparison_summary")
    if not isinstance(shadow, Mapping):
        rows = [row for row in report.get("rows") or [] if isinstance(row, Mapping)]
        summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else None
        shadow = shadow_comparison_summary(rows, summary)
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    payload = {
        "version": SHADOW_COMPARISON_ARTIFACT_VERSION,
        "report_version": report.get("version"),
        "generated_at": report.get("generated_at"),
        "active_visible_pipeline": report.get("active_visible_pipeline"),
        "prompt_pipeline_active": report.get("prompt_pipeline_active"),
        "runtime_activation_allowed": False,
        "policy": "ci_admin_shadow_comparison_no_runtime_activation",
        "shadow_comparison_summary": dict(shadow),
        "shadow_comparison_sha256": provenance.get("shadow_comparison_sha256")
        or _sha256_json(shadow),
        "runtime_effect": dict(shadow.get("runtime_effect") or {}),
    }
    json_path = output_dir / "raw_fid_prompt_shadow_comparison_summary.json"
    csv_path = output_dir / "raw_fid_prompt_shadow_comparison_summary.csv"
    json_path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    csv_columns = [
        "version",
        "status",
        "visibility",
        "reporting_policy",
        "decision_guidance",
        "active_visible_pipeline",
        "prompt_pipeline_active",
        "runtime_activation_allowed",
        "fixture_count",
        "prompt_sidecar_available",
        "prompt_sidecar_unavailable",
        "reference_rows",
        "ppm_reference_rows",
        "prompt_peak_count_review_required",
        "prompt_reference_ppm_review_required",
        "prompt_runtime_review_required",
        "max_prompt_reference_peak_count_delta",
        "max_prompt_reference_ppm_error",
        "max_prompt_runtime_ms",
        "review_fixture_ids",
        "shadow_comparison_sha256",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerow(
            {
                "version": _csv_cell(shadow.get("version")),
                "status": _csv_cell(shadow.get("status")),
                "visibility": _csv_cell(shadow.get("visibility")),
                "reporting_policy": _csv_cell(shadow.get("reporting_policy")),
                "decision_guidance": _csv_cell(shadow.get("decision_guidance")),
                "active_visible_pipeline": _csv_cell(
                    shadow.get("active_visible_pipeline")
                ),
                "prompt_pipeline_active": _csv_cell(
                    shadow.get("prompt_pipeline_active")
                ),
                "runtime_activation_allowed": _csv_cell(
                    shadow.get("runtime_activation_allowed")
                ),
                "fixture_count": _csv_cell(shadow.get("fixture_count")),
                "prompt_sidecar_available": _csv_cell(
                    shadow.get("prompt_sidecar_available")
                ),
                "prompt_sidecar_unavailable": _csv_cell(
                    shadow.get("prompt_sidecar_unavailable")
                ),
                "reference_rows": _csv_cell(shadow.get("reference_rows")),
                "ppm_reference_rows": _csv_cell(shadow.get("ppm_reference_rows")),
                "prompt_peak_count_review_required": _csv_cell(
                    shadow.get("prompt_peak_count_review_required")
                ),
                "prompt_reference_ppm_review_required": _csv_cell(
                    shadow.get("prompt_reference_ppm_review_required")
                ),
                "prompt_runtime_review_required": _csv_cell(
                    shadow.get("prompt_runtime_review_required")
                ),
                "max_prompt_reference_peak_count_delta": _csv_cell(
                    shadow.get("max_prompt_reference_peak_count_delta")
                ),
                "max_prompt_reference_ppm_error": _csv_cell(
                    shadow.get("max_prompt_reference_ppm_error")
                ),
                "max_prompt_runtime_ms": _csv_cell(
                    shadow.get("max_prompt_runtime_ms")
                ),
                "review_fixture_ids": _csv_cell(
                    ";".join(
                        str(item) for item in shadow.get("review_fixture_ids") or []
                    )
                ),
                "shadow_comparison_sha256": _csv_cell(
                    payload["shadow_comparison_sha256"]
                ),
            }
        )
    return json_path, csv_path


def write_validation_release_readiness_artifact(
    report: Mapping[str, Any],
    output_dir: Path,
) -> Path:
    """Write a compact reviewer-facing release readiness markdown artifact."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    promotion_gate = (
        report.get("promotion_gate")
        if isinstance(report.get("promotion_gate"), Mapping)
        else promotion_gate_summary(report)
    )
    shadow = report.get("shadow_comparison_summary")
    if not isinstance(shadow, Mapping):
        rows = [row for row in report.get("rows") or [] if isinstance(row, Mapping)]
        shadow = shadow_comparison_summary(rows, summary)
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    if isinstance(report.get("runtime_effect"), Mapping):
        runtime_effect = dict(report["runtime_effect"])
    elif isinstance(shadow.get("runtime_effect"), Mapping):
        runtime_effect = dict(shadow["runtime_effect"])
    else:
        runtime_effect = {
            "spectracheck_visible_pipeline": "unchanged_legacy",
            "processed_spectrum_pipeline": "unchanged",
            "raw_fid_plotting": "unchanged",
            "peak_markers": "unchanged",
        }
    rows = [row for row in report.get("rows") or [] if isinstance(row, Mapping)]
    review_fixture_ids = shadow.get("review_fixture_ids") or []
    if not isinstance(review_fixture_ids, Sequence) or isinstance(review_fixture_ids, str):
        review_fixture_ids = []
    fixture_table = [
        "| Fixture | Vendor | Nucleus | Row status | Activation readiness | Legacy peaks | Prompt peaks | Reference peaks |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in rows[:20]:
        fixture_table.append(
            "| "
            + " | ".join(
                _markdown_cell(row.get(key))
                for key in (
                    "fixture_id",
                    "vendor",
                    "nucleus",
                    "row_status",
                    "activation_readiness_status",
                    "legacy_peak_count",
                    "prompt_peak_count",
                    "reference_peak_count",
                )
            )
            + " |"
        )
    if len(fixture_table) == 2:
        fixture_table.append("| No fixtures | - | - | - | - | - | - | - |")

    lines = [
        "# Raw FID Prompt 1/2 Release Readiness",
        "",
        f"- Artifact version: `{RELEASE_READINESS_ARTIFACT_VERSION}`",
        f"- Report version: `{_markdown_inline(report.get('version'))}`",
        f"- Generated at: `{_markdown_inline(report.get('generated_at'))}`",
        f"- Active visible pipeline: `{_markdown_inline(report.get('active_visible_pipeline'))}`",
        f"- Prompt pipeline active: `{_markdown_inline(report.get('prompt_pipeline_active'))}`",
        "- Runtime activation: `blocked`",
        "- Runtime activation allowed: `false`",
        "",
        (
            "This is read-only release evidence. It does not activate Prompt 1/2, "
            "does not alter SpectraCheck raw-FID plotting, and does not alter "
            "processed-spectrum behavior."
        ),
        "",
        "## Manual Promotion Gate",
        "",
        f"- Version: `{_markdown_inline(promotion_gate.get('version'))}`",
        f"- Status: `{_markdown_inline(promotion_gate.get('status'))}`",
        f"- Eligible for manual promotion: `{_markdown_inline(promotion_gate.get('eligible_for_manual_promotion'))}`",
        f"- Runtime activation allowed: `{_markdown_inline(promotion_gate.get('runtime_activation_allowed'))}`",
        f"- Failure count: `{_markdown_inline(promotion_gate.get('failure_count'))}`",
        f"- Required command: `{_markdown_inline(promotion_gate.get('ci_command'))}`",
        "",
        "Promotion remains blocked until a separate manual runtime promotion is implemented, reviewed, and protected by guardrails.",
        "",
        "## Shadow Comparison",
        "",
        f"- Version: `{_markdown_inline(shadow.get('version'))}`",
        f"- Status: `{_markdown_inline(shadow.get('status'))}`",
        f"- Decision guidance: `{_markdown_inline(shadow.get('decision_guidance'))}`",
        f"- Fixture count: `{_markdown_inline(shadow.get('fixture_count'))}`",
        f"- Prompt sidecar available: `{_markdown_inline(shadow.get('prompt_sidecar_available'))}`",
        f"- Prompt sidecar unavailable: `{_markdown_inline(shadow.get('prompt_sidecar_unavailable'))}`",
        f"- Peak-count review required: `{_markdown_inline(shadow.get('prompt_peak_count_review_required'))}`",
        f"- PPM-reference review required: `{_markdown_inline(shadow.get('prompt_reference_ppm_review_required'))}`",
        f"- Runtime review required: `{_markdown_inline(shadow.get('prompt_runtime_review_required'))}`",
        f"- Review fixture IDs: `{_markdown_inline('; '.join(str(item) for item in review_fixture_ids))}`",
        "",
        "## Provenance Hashes",
        "",
        f"- Fixture identity SHA-256: `{_markdown_inline(provenance.get('fixture_identity_sha256'))}`",
        f"- Row fingerprint SHA-256: `{_markdown_inline(provenance.get('row_fingerprint_sha256'))}`",
        f"- Report payload SHA-256: `{_markdown_inline(provenance.get('report_payload_sha256'))}`",
        f"- Shadow comparison SHA-256: `{_markdown_inline(provenance.get('shadow_comparison_sha256'))}`",
        f"- Runtime effect SHA-256: `{_markdown_inline(provenance.get('runtime_effect_sha256'))}`",
        "",
        "## Summary Counts",
        "",
        f"- Passed rows: `{_markdown_inline(summary.get('passed'))}`",
        f"- Review-required rows: `{_markdown_inline(summary.get('review_required'))}`",
        f"- Failed rows: `{_markdown_inline(summary.get('failed'))}`",
        f"- Total rows: `{_markdown_inline(summary.get('total'))}`",
        "",
        "## Runtime Effect",
        "",
    ]
    for key, value in sorted(dict(runtime_effect).items()):
        lines.append(f"- `{_markdown_inline(key)}`: `{_markdown_inline(value)}`")
    lines.extend(["", "## Fixture Snapshot", "", *fixture_table, ""])

    path = output_dir / "raw_fid_prompt_release_readiness.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_validation_provenance_artifacts(
    report: Mapping[str, Any],
    output_dir: Path,
    *,
    json_path: Path,
    csv_path: Path,
    shadow_json_path: Path | None = None,
    shadow_csv_path: Path | None = None,
    release_readiness_path: Path | None = None,
) -> tuple[Path, Path]:
    """Write CI-friendly provenance and checksum manifests for report outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "raw_fid_prompt_sidecar_provenance_checksums.json"
    checksum_csv_path = output_dir / "raw_fid_prompt_sidecar_provenance_checksums.csv"
    exported_files = [
        _file_manifest("report_json", json_path),
        _file_manifest("report_csv", csv_path),
    ]
    if shadow_json_path is not None:
        exported_files.append(_file_manifest("shadow_comparison_json", shadow_json_path))
    if shadow_csv_path is not None:
        exported_files.append(_file_manifest("shadow_comparison_csv", shadow_csv_path))
    if release_readiness_path is not None:
        exported_files.append(
            _file_manifest("release_readiness_markdown", release_readiness_path)
        )
    rows = [row for row in report.get("rows") or [] if isinstance(row, Mapping)]
    fixture_archives = [
        {
            "artifact_type": "fixture_archive",
            "fixture_id": row.get("fixture_id"),
            "source": row.get("source"),
            "vendor": row.get("vendor"),
            "nucleus": row.get("nucleus"),
            "path": row.get("archive"),
            "sha256": row.get("archive_sha256"),
            "size_bytes": row.get("archive_size_bytes"),
        }
        for row in rows
    ]
    manifest = {
        "version": PROVENANCE_ARTIFACT_VERSION,
        "report_version": report.get("version"),
        "generated_at": report.get("generated_at"),
        "active_visible_pipeline": report.get("active_visible_pipeline"),
        "prompt_pipeline_active": report.get("prompt_pipeline_active"),
        "activation_policy": report.get("activation_policy"),
        "runtime_effect": report.get("runtime_effect")
        or {
            "spectracheck_visible_pipeline": "unchanged_legacy",
            "processed_spectrum_pipeline": "unchanged",
            "raw_fid_plotting": "unchanged",
            "peak_markers": "unchanged",
        },
        "provenance": report.get("provenance") or {},
        "exported_files": exported_files,
        "fixture_archives": fixture_archives,
        "checksum_summary_sha256": _sha256_json(
            {
                "exported_files": exported_files,
                "fixture_archives": fixture_archives,
            }
        ),
    }
    manifest_path.write_text(
        json.dumps(_jsonable(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksum_rows = exported_files + fixture_archives
    with checksum_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "artifact_type",
                "fixture_id",
                "source",
                "vendor",
                "nucleus",
                "path",
                "sha256",
                "size_bytes",
            ],
        )
        writer.writeheader()
        for row in checksum_rows:
            writer.writerow(
                {
                    "artifact_type": _csv_cell(row.get("artifact_type")),
                    "fixture_id": _csv_cell(row.get("fixture_id")),
                    "source": _csv_cell(row.get("source")),
                    "vendor": _csv_cell(row.get("vendor")),
                    "nucleus": _csv_cell(row.get("nucleus")),
                    "path": _csv_cell(row.get("path")),
                    "sha256": _csv_cell(row.get("sha256")),
                    "size_bytes": _csv_cell(row.get("size_bytes")),
                }
            )
    return manifest_path, checksum_csv_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the legacy raw-FID processor with the Prompt 1/2 sidecar "
            "on fixture archives. The report is observational only."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=backend_root() / "reports" / DEFAULT_OUTPUT_DIRNAME,
        help="Directory for JSON/CSV report outputs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for NMRShiftDB2 Bruker fixtures before Varian is added.",
    )
    parser.add_argument(
        "--include-varian",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the nmrglue Varian/Agilent fixture.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Raise instead of recording fixture processing failures.",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Return non-zero when any fixture requires review or fails.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Return non-zero only when the reporting-only guardrails are broken. "
            "Scientific review rows remain advisory in smoke mode."
        ),
    )
    parser.add_argument(
        "--promotion-gate",
        action="store_true",
        help=(
            "Return non-zero unless every fixture gate is ready for a future "
            "manual promotion. This still does not activate Prompt 1/2 at runtime."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-fixture progress output.",
    )
    args = parser.parse_args(argv)

    report = build_fixture_validation_report(
        include_varian=args.include_varian,
        limit=args.limit,
        strict=args.strict,
        progress=not args.quiet,
    )
    json_path, csv_path = write_validation_outputs(report, args.output_dir)
    summary = report["summary"]
    print(
        "Raw-FID Prompt sidecar fixture validation: "
        f"{summary['passed']} passed, "
        f"{summary['review_required']} review_required, "
        f"{summary['failed']} failed, "
        f"{summary['total']} total"
    )
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    provenance_path = args.output_dir / "raw_fid_prompt_sidecar_provenance_checksums.json"
    checksum_path = args.output_dir / "raw_fid_prompt_sidecar_provenance_checksums.csv"
    if provenance_path.exists() and checksum_path.exists():
        print(f"Provenance: {provenance_path}")
        print(f"Checksums:  {checksum_path}")
    shadow_path = args.output_dir / "raw_fid_prompt_shadow_comparison_summary.json"
    shadow_csv_path = args.output_dir / "raw_fid_prompt_shadow_comparison_summary.csv"
    if shadow_path.exists() and shadow_csv_path.exists():
        print(f"Shadow:     {shadow_path}")
        print(f"Shadow CSV: {shadow_csv_path}")
    readiness_path = args.output_dir / "raw_fid_prompt_release_readiness.md"
    if readiness_path.exists():
        print(f"Readiness:  {readiness_path}")
    if args.smoke:
        smoke = reporting_only_smoke_summary(report)
        if smoke["failures"]:
            print("Reporting-only smoke failures:")
            for failure in smoke["failures"]:
                print(f"- {failure}")
            return 1
    if args.promotion_gate:
        gate = promotion_gate_summary(report)
        if gate["failures"]:
            print("Prompt sidecar manual-promotion gate failures:")
            for failure in gate["failures"]:
                print(f"- {failure}")
            return 1
    if args.fail_on_review and (
        summary["failed"] > 0 or summary["review_required"] > 0
    ):
        return 1
    return 0


def shadow_comparison_summary(
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an admin-only aggregate of Prompt sidecar fixture comparisons.

    The summary is intentionally compact and non-activating. It gives release
    reviewers a single place to see whether the sidecar agrees with references
    before any future manual promotion decision.
    """

    checked_rows = [row for row in rows if isinstance(row, Mapping)]
    counts = dict(summary or _summarize_rows(checked_rows))
    activation_counts = _count_values(
        row.get("activation_readiness_status") for row in checked_rows
    )
    row_status_counts = _count_values(row.get("row_status") for row in checked_rows)
    review_fixture_ids = [
        str(row.get("fixture_id") or "unknown")
        for row in checked_rows
        if _row_needs_shadow_review(row)
    ][:8]
    fixture_count = len(checked_rows)
    prompt_sidecar_available = int(counts.get("prompt_sidecar_available") or 0)
    prompt_sidecar_unavailable = int(counts.get("prompt_sidecar_unavailable") or 0)
    peak_count_review_required = _count_bool(
        checked_rows,
        "prompt_peak_count_within_reference_tolerance",
        False,
    )
    ppm_review_required = _count_bool(
        checked_rows,
        "prompt_reference_ppm_within_tolerance",
        False,
    )
    failed_rows = int(counts.get("failed") or 0)
    if fixture_count <= 0:
        status = "no_fixtures"
    elif failed_rows or prompt_sidecar_unavailable:
        status = "blocked"
    elif review_fixture_ids or peak_count_review_required or ppm_review_required:
        status = "review_required"
    else:
        status = "passed"

    return {
        "version": SHADOW_COMPARISON_VERSION,
        "visibility": "admin_diagnostic_only",
        "reporting_policy": "read_only_shadow_comparison_no_runtime_activation",
        "status": status,
        "decision_guidance": (
            "all_shadow_gates_passed_manual_review_still_required"
            if status == "passed"
            else "review_required_before_any_manual_promotion"
        ),
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "runtime_activation_allowed": False,
        "fixture_count": fixture_count,
        "prompt_sidecar_available": prompt_sidecar_available,
        "prompt_sidecar_unavailable": prompt_sidecar_unavailable,
        "reference_rows": sum(
            1 for row in checked_rows if _safe_int(row.get("reference_peak_count")) is not None
        ),
        "ppm_reference_rows": sum(
            1
            for row in checked_rows
            if (_safe_int(row.get("prompt_reference_ppm_checked_count")) or 0) > 0
        ),
        "prompt_peak_count_within_reference_tolerance": _count_bool(
            checked_rows,
            "prompt_peak_count_within_reference_tolerance",
            True,
        ),
        "prompt_peak_count_review_required": peak_count_review_required,
        "prompt_reference_ppm_within_tolerance": _count_bool(
            checked_rows,
            "prompt_reference_ppm_within_tolerance",
            True,
        ),
        "prompt_reference_ppm_review_required": ppm_review_required,
        "prompt_runtime_within_target": _count_bool(
            checked_rows,
            "prompt_runtime_within_target",
            True,
        ),
        "prompt_runtime_review_required": _count_bool(
            checked_rows,
            "prompt_runtime_within_target",
            False,
        ),
        "row_status_counts": row_status_counts,
        "activation_status_counts": activation_counts,
        "max_peak_count_delta_legacy_prompt": _max_abs_int(
            row.get("peak_count_delta_legacy_prompt") for row in checked_rows
        ),
        "max_prompt_reference_peak_count_delta": _max_abs_int(
            row.get("prompt_reference_peak_count_delta") for row in checked_rows
        ),
        "max_prompt_reference_ppm_error": _max_float(
            row.get("prompt_reference_ppm_max_error") for row in checked_rows
        ),
        "max_phase_delta_degrees": _max_float(
            row.get("phase_delta_degrees") for row in checked_rows
        ),
        "max_baseline_rmse_fraction_full_scale": _max_float(
            row.get("baseline_prompt_rmse_fraction_full_scale")
            for row in checked_rows
        ),
        "max_prompt_runtime_ms": _max_float(
            row.get("prompt_runtime_ms") for row in checked_rows
        ),
        "review_fixture_ids": review_fixture_ids,
        "runtime_effect": {
            "spectracheck_visible_pipeline": "unchanged_legacy",
            "processed_spectrum_pipeline": "unchanged",
            "raw_fid_plotting": "unchanged",
            "prompt_sidecar_runtime": "diagnostic_only",
        },
    }


def _row_needs_shadow_review(row: Mapping[str, Any]) -> bool:
    if row.get("row_status") != "passed":
        return True
    if row.get("activation_readiness_status") != "passed":
        return True
    if row.get("prompt_peak_count_within_reference_tolerance") is False:
        return True
    if row.get("prompt_reference_ppm_within_tolerance") is False:
        return True
    if row.get("prompt_runtime_within_target") is False:
        return True
    return False


def _count_bool(
    rows: Sequence[Mapping[str, Any]],
    key: str,
    target: bool,
) -> int:
    return sum(1 for row in rows if row.get(key) is target)


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _max_abs_int(values: Iterable[Any]) -> int | None:
    numeric = [_safe_int(value) for value in values]
    finite = [abs(value) for value in numeric if value is not None]
    return max(finite) if finite else None


def _max_float(values: Iterable[Any]) -> float | None:
    finite = [_safe_float(value) for value in values]
    numbers = [value for value in finite if value is not None]
    return max(numbers) if numbers else None


def promotion_gate_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize whether Prompt 1/2 sidecar data is ready for manual promotion.

    This gate is a CI/admin decision aid only.  A passing gate means the
    observational fixture report is internally consistent and all scientific
    review gates passed.  It never flips the runtime pipeline and it still
    requires a separate code/config promotion step.
    """

    failures = promotion_gate_failures(report)
    eligible = not failures
    return {
        "version": PROMOTION_GATE_VERSION,
        "visibility": "ci_admin_gate_only",
        "status": "eligible_for_manual_promotion" if eligible else "blocked",
        "eligible_for_manual_promotion": eligible,
        "runtime_activation_allowed": False,
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "requires_manual_code_change": True,
        "requires_explicit_runtime_feature_flag": True,
        "failure_count": len(failures),
        "failures": failures,
        "ci_command": (
            "PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report "
            "--limit 20 --include-varian --quiet --promotion-gate"
        ),
    }


def promotion_gate_failures(report: Mapping[str, Any]) -> list[str]:
    """Return manual-promotion blockers for the raw-FID Prompt 1/2 sidecar."""

    failures: list[str] = []
    failures.extend(
        f"reporting_only_smoke:{failure}"
        for failure in reporting_only_smoke_failures(report)
    )

    readiness = report.get("activation_readiness")
    if not isinstance(readiness, Mapping):
        failures.append("activation_readiness_missing")
        readiness = {}

    if readiness.get("version") != "raw_fid_prompt_activation_readiness_v1":
        failures.append("activation_readiness_unexpected_version")
    if readiness.get("visibility") != "admin_diagnostic_only":
        failures.append("activation_readiness_not_admin_diagnostic_only")
    if readiness.get("active_visible_pipeline") != "legacy":
        failures.append("activation_readiness_visible_pipeline_not_legacy")
    if readiness.get("prompt_pipeline_active") is not False:
        failures.append("activation_readiness_prompt_pipeline_marked_active")
    if readiness.get("activation_allowed") is not False:
        failures.append("activation_readiness_allows_runtime_activation")
    if readiness.get("overall_status") != "candidate_ready_for_manual_promotion":
        failures.append(
            f"activation_readiness_status:{readiness.get('overall_status') or 'missing'}"
        )

    gates = readiness.get("gates")
    if not isinstance(gates, Sequence) or isinstance(gates, (str, bytes)):
        failures.append("activation_readiness_gates_missing")
        gates = []
    gate_count = _safe_int(readiness.get("gate_count"))
    passed_gate_count = _safe_int(readiness.get("passed_gate_count"))
    failed_gate_count = _safe_int(readiness.get("failed_gate_count"))
    review_gate_count = _safe_int(readiness.get("review_gate_count"))
    if gate_count is None or gate_count <= 0:
        failures.append("activation_readiness_no_gates")
    if failed_gate_count not in (0, None):
        failures.append(f"activation_readiness_failed_gate_count:{failed_gate_count}")
    if review_gate_count not in (0, None):
        failures.append(f"activation_readiness_review_gate_count:{review_gate_count}")
    if gate_count is not None and passed_gate_count != gate_count:
        failures.append(
            f"activation_readiness_not_all_gates_passed:{passed_gate_count}/{gate_count}"
        )
    for gate in gates:
        if not isinstance(gate, Mapping):
            failures.append("activation_readiness_gate_malformed")
            continue
        if gate.get("status") != "passed":
            failures.append(
                f"activation_readiness_gate_not_passed:{gate.get('name') or 'unknown'}"
            )

    rows = report.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        failures.append("fixture_rows_missing")
        rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            failures.append("fixture_row_malformed")
            continue
        fixture_id = str(row.get("fixture_id") or "unknown")
        if row.get("row_status") != "passed":
            failures.append(f"{fixture_id}:row_status_not_passed")
        if row.get("activation_readiness_status") != "passed":
            failures.append(f"{fixture_id}:activation_readiness_not_passed")
        if row.get("safe_to_activate") is not False:
            failures.append(f"{fixture_id}:safe_to_activate_not_false")
        if row.get("validation_visibility") != "hidden_metadata_only":
            failures.append(f"{fixture_id}:validation_not_hidden_metadata_only")
        if row.get("prompt_hash_present") is not True:
            failures.append(f"{fixture_id}:prompt_fingerprint_hash_missing")

    return _unique_preserving_order(failures)


def reporting_only_smoke_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return guardrail failures for CI/admin smoke checks.

    This smoke check is intentionally narrow: it verifies that the Prompt 1/2
    fixture report remains diagnostic and non-activating. It does not require
    fixture rows to pass scientific review thresholds because those rows are
    for manual comparison before a future activation decision.
    """

    failures = list(reporting_only_smoke_failures(report))
    return {
        "passed": not failures,
        "failure_count": len(failures),
        "failures": failures,
    }


def reporting_only_smoke_failures(report: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    rows = list(report.get("rows") or [])
    summary = report.get("summary") or {}
    if report.get("version") != REPORT_VERSION:
        failures.append("unexpected_report_version")
    if report.get("active_visible_pipeline") != "legacy":
        failures.append("active_visible_pipeline_not_legacy")
    if report.get("prompt_pipeline_active") is not False:
        failures.append("prompt_pipeline_marked_active")
    if report.get("activation_policy") != "reporting_only_no_runtime_wiring":
        failures.append("activation_policy_not_reporting_only")
    if int(report.get("fixture_count") or 0) <= 0:
        failures.append("no_fixtures_validated")
    if not rows:
        failures.append("no_fixture_rows")
    if int(summary.get("prompt_sidecar_available") or 0) <= 0:
        failures.append("prompt_sidecar_unavailable_for_smoke_fixture")
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "unknown")
        if row.get("safe_to_activate") is not False:
            failures.append(f"{fixture_id}:safe_to_activate_not_false")
        if row.get("validation_visibility") != "hidden_metadata_only":
            failures.append(f"{fixture_id}:validation_not_hidden_metadata_only")
        if (
            row.get("prompt_status") == "ok"
            and row.get("prompt_hash_present") is not True
        ):
            failures.append(f"{fixture_id}:missing_prompt_fingerprint_hash")
    return failures


def _load_nmrshiftdb2_fixtures(root: Path) -> Iterable[dict[str, Any]]:
    manifest_path = root / "expected" / "nmrshiftdb2_bruker_20.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for index, fixture in enumerate(manifest.get("fixtures") or [], start=1):
        archive = str(fixture["archive"])
        yield {
            "fixture_id": (
                f"nmrshiftdb2_{fixture.get('spectrum_id', index)}_"
                f"{_nucleus_slug(fixture.get('nucleus'))}"
            ),
            "source": fixture.get("source", "NMRShiftDB2"),
            "vendor": fixture.get("vendor", "Bruker"),
            "nucleus": fixture.get("nucleus"),
            "archive": archive,
            "archive_path": root / archive,
            "reference_peak_count": _safe_int(fixture.get("reference_peak_count")),
            "peak_count_tolerance": _safe_int(fixture.get("peak_count_tolerance")),
            "reference_peak_ppm": fixture.get("reference_peak_ppm") or [],
            "ppm_tolerance": _safe_float(fixture.get("ppm_tolerance")),
        }


def _load_varian_fixture(root: Path) -> dict[str, Any]:
    expected_path = root / "expected" / "example_separate_1d_varian.json"
    fixture = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = fixture.get("expected") or {}
    archive = "raw/example_separate_1d_varian.zip"
    return {
        "fixture_id": "nmrglue_example_separate_1d_varian",
        "source": "nmrglue",
        "vendor": expected.get("vendor", "Varian/Agilent"),
        "nucleus": expected.get("nucleus"),
        "solvent": expected.get("solvent"),
        "archive": archive,
        "archive_path": root / archive,
        "reference_peak_count": _safe_int(expected.get("peak_count")),
        "peak_count_tolerance": 2,
        "reference_peak_ppm": [],
        "ppm_tolerance": None,
        "reference_fingerprint_hash": expected.get("fingerprint_hash"),
    }


def _validate_fixture(fixture: Mapping[str, Any], *, strict: bool) -> dict[str, Any]:
    archive_path = Path(fixture["archive_path"])
    content = archive_path.read_bytes()
    nucleus = _clean_str(fixture.get("nucleus")) or "1H"
    solvent = _clean_str(fixture.get("solvent"))
    legacy_report: FIDPreviewReport | None = None
    legacy_error: str | None = None
    sidecar: dict[str, Any] = {}
    sidecar_error: str | None = None
    validation: dict[str, Any] | None = None

    try:
        legacy_report = process_bruker_1d_zip(
            filename=archive_path.name,
            content=content,
            nucleus=nucleus,
            solvent=solvent,
            settings=fid_settings_from_preset(selected_preset="balanced"),
        )
    except Exception as exc:
        if strict:
            raise
        legacy_error = _format_exception(exc)

    try:
        sidecar = build_prompt_pipeline_sidecar(
            filename=archive_path.name,
            content=content,
            nucleus=nucleus,
            solvent=solvent,
            strict=strict,
        )
    except Exception as exc:
        if strict:
            raise
        sidecar_error = _format_exception(exc)
        sidecar = {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": False,
            "warnings": [sidecar_error],
        }

    if legacy_report is not None:
        validation = build_prompt_pipeline_validation_report(legacy_report, sidecar)

    row = _base_row(fixture)
    row["archive_sha256"] = hashlib.sha256(content).hexdigest()
    row["archive_size_bytes"] = len(content)
    row.update(_legacy_fields(legacy_report, legacy_error))
    row.update(_prompt_fields(sidecar, sidecar_error))
    row.update(_validation_fields(validation))
    row.update(_reference_fields(row, fixture))
    row.update(_row_activation_readiness_fields(row))
    row["failure_reasons"] = _failure_reasons(legacy_error, sidecar_error, validation)
    row["row_status"] = _row_status(row)
    return row


def _base_row(fixture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": fixture.get("fixture_id"),
        "source": fixture.get("source"),
        "vendor": fixture.get("vendor"),
        "nucleus": fixture.get("nucleus"),
        "archive": fixture.get("archive"),
        "reference_peak_count": _safe_int(fixture.get("reference_peak_count")),
        "peak_count_tolerance": _safe_int(fixture.get("peak_count_tolerance")),
        "reference_peak_ppm_count": len(
            _finite_float_list(fixture.get("reference_peak_ppm"))
        ),
        "reference_ppm_tolerance": _safe_float(fixture.get("ppm_tolerance")),
    }


def _legacy_fields(
    report: FIDPreviewReport | None,
    error: str | None,
) -> dict[str, Any]:
    if report is None:
        return {
            "legacy_status": "failed",
            "legacy_peak_count": None,
            "legacy_point_count": None,
            "legacy_error": error,
        }
    return {
        "legacy_status": "ok",
        "legacy_peak_count": len(report.inferred_peaks),
        "legacy_point_count": int(report.point_count),
        "legacy_error": None,
    }


def _prompt_fields(
    sidecar: Mapping[str, Any],
    error: str | None,
) -> dict[str, Any]:
    prompt_peak_count = _safe_int(sidecar.get("peak_count"))
    if prompt_peak_count is None:
        prompt_peak_count = _safe_int(sidecar.get("estimated_peak_count"))
    if prompt_peak_count is None:
        prompt_peak_count = _safe_int(sidecar.get("processed_peaklist_peak_count"))
    preprocess_diagnostics = (
        sidecar.get("preprocess_diagnostics")
        if isinstance(sidecar.get("preprocess_diagnostics"), Mapping)
        else {}
    )
    baseline = (
        sidecar.get("baseline")
        if isinstance(sidecar.get("baseline"), Mapping)
        else {}
    )
    return {
        "prompt_status": "ok" if bool(sidecar.get("available")) else "failed",
        "prompt_peak_count": prompt_peak_count,
        "prompt_point_count": _safe_int(sidecar.get("point_count")),
        "prompt_ppm_min": _safe_float(sidecar.get("ppm_min")),
        "prompt_ppm_max": _safe_float(sidecar.get("ppm_max")),
        "prompt_hash_present": isinstance(sidecar.get("fingerprint_hash"), str)
        and len(str(sidecar.get("fingerprint_hash"))) == 64,
        "prompt_runtime_ms": _safe_float(sidecar.get("runtime_ms")),
        "baseline_prompt_rmse_fraction_full_scale": _safe_float(
            preprocess_diagnostics.get("baseline_rmse_fraction_full_scale")
            or baseline.get("baseline_rmse_fraction_full_scale")
        ),
        "prompt_error": error or "; ".join(str(w) for w in sidecar.get("warnings") or []),
    }


def _validation_fields(validation: Mapping[str, Any] | None) -> dict[str, Any]:
    if not validation:
        return {
            "validation_status": "unavailable",
            "validation_visibility": None,
            "safe_to_activate": False,
            "peak_count_delta_legacy_prompt": None,
            "point_count_delta": None,
            "ppm_min_abs_delta": None,
            "ppm_max_abs_delta": None,
            "phase_delta_degrees": None,
            "baseline_legacy_method": None,
            "baseline_prompt_method": None,
            "prompt_runtime_within_target": None,
        }
    comparisons = validation.get("comparisons") or {}
    peak_delta = comparisons.get("peak_count_delta") or {}
    ppm_delta = comparisons.get("ppm_range_delta") or {}
    phase_delta = comparisons.get("phase_delta_degrees") or {}
    baseline = comparisons.get("baseline") or {}
    runtime = comparisons.get("runtime") or {}
    return {
        "validation_status": validation.get("status"),
        "validation_visibility": validation.get("visibility"),
        "safe_to_activate": bool(validation.get("safe_to_activate")),
        "peak_count_delta_legacy_prompt": _safe_int(peak_delta.get("value")),
        "point_count_delta": _safe_int(comparisons.get("point_count_delta")),
        "ppm_min_abs_delta": _safe_float(ppm_delta.get("ppm_min_abs_delta")),
        "ppm_max_abs_delta": _safe_float(ppm_delta.get("ppm_max_abs_delta")),
        "phase_delta_degrees": _safe_float(phase_delta.get("value")),
        "baseline_legacy_method": baseline.get("legacy_method"),
        "baseline_prompt_method": baseline.get("prompt_method"),
        "prompt_runtime_within_target": runtime.get("within_target"),
    }


def _reference_fields(
    row: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    reference_count = _safe_int(fixture.get("reference_peak_count"))
    tolerance = _safe_int(fixture.get("peak_count_tolerance"))
    legacy_delta = _abs_int_delta(row.get("legacy_peak_count"), reference_count)
    prompt_delta = _abs_int_delta(row.get("prompt_peak_count"), reference_count)
    return {
        "legacy_reference_peak_count_delta": legacy_delta,
        "prompt_reference_peak_count_delta": prompt_delta,
        "legacy_peak_count_within_reference_tolerance": _within_tolerance(
            legacy_delta,
            tolerance,
        ),
        "prompt_peak_count_within_reference_tolerance": _within_tolerance(
            prompt_delta,
            tolerance,
        ),
        **_reference_ppm_axis_fields(row, fixture),
    }


def _reference_ppm_axis_fields(
    row: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare Prompt ppm grid spacing with processed Bruker reference peaks.

    The Prompt 1 reader acceptance test checks each processed sidecar peak
    against the generated ppm axis.  The fixture report mirrors that same
    contract without exposing or activating the plotted Prompt trace.
    """

    references = _finite_float_list(fixture.get("reference_peak_ppm"))
    tolerance = _safe_float(fixture.get("ppm_tolerance"))
    point_count = _safe_int(row.get("prompt_point_count"))
    ppm_min = _safe_float(row.get("prompt_ppm_min"))
    ppm_max = _safe_float(row.get("prompt_ppm_max"))
    if not references or tolerance is None:
        return {
            "prompt_reference_ppm_checked_count": 0,
            "prompt_reference_ppm_max_error": None,
            "prompt_reference_ppm_mean_error": None,
            "prompt_reference_ppm_within_tolerance": None,
        }
    if point_count is None or point_count < 2 or ppm_min is None or ppm_max is None:
        return {
            "prompt_reference_ppm_checked_count": 0,
            "prompt_reference_ppm_max_error": None,
            "prompt_reference_ppm_mean_error": None,
            "prompt_reference_ppm_within_tolerance": False,
        }

    errors = [
        _nearest_uniform_axis_error(
            reference_ppm,
            ppm_min=ppm_min,
            ppm_max=ppm_max,
            point_count=point_count,
        )
        for reference_ppm in references
    ]
    max_error = max(errors) if errors else None
    mean_error = sum(errors) / len(errors) if errors else None
    return {
        "prompt_reference_ppm_checked_count": len(errors),
        "prompt_reference_ppm_max_error": max_error,
        "prompt_reference_ppm_mean_error": mean_error,
        "prompt_reference_ppm_within_tolerance": (
            None if max_error is None else max_error <= tolerance
        ),
    }


def _failure_reasons(
    legacy_error: str | None,
    sidecar_error: str | None,
    validation: Mapping[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if legacy_error:
        reasons.append(f"legacy: {legacy_error}")
    if sidecar_error:
        reasons.append(f"prompt_sidecar: {sidecar_error}")
    if validation:
        reasons.extend(str(reason) for reason in validation.get("failure_reasons") or [])
    return reasons


def _row_status(row: Mapping[str, Any]) -> str:
    if row.get("legacy_status") != "ok" or row.get("prompt_status") != "ok":
        return "failed"
    if row.get("prompt_peak_count_within_reference_tolerance") is False:
        return "review_required"
    if row.get("prompt_reference_ppm_within_tolerance") is False:
        return "review_required"
    if row.get("validation_status") == "review_required":
        return "review_required"
    return "passed"


def _row_activation_readiness_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    reviews: list[str] = []

    if row.get("legacy_status") != "ok":
        failures.append("legacy_processor_failed")
    if row.get("prompt_status") != "ok":
        failures.append("prompt_sidecar_failed")
    if row.get("prompt_hash_present") is not True:
        failures.append("prompt_fingerprint_hash_missing")

    runtime_within_target = row.get("prompt_runtime_within_target")
    if runtime_within_target is False:
        failures.append("prompt_runtime_over_3000ms")
    elif runtime_within_target is None:
        reviews.append("prompt_runtime_target_unavailable")

    peak_count_within_reference = row.get(
        "prompt_peak_count_within_reference_tolerance"
    )
    if peak_count_within_reference is False:
        reviews.append("prompt_peak_count_outside_reference_tolerance")
    elif peak_count_within_reference is None:
        reviews.append("prompt_peak_count_reference_tolerance_unavailable")

    reference_ppm_count = _safe_int(row.get("reference_peak_ppm_count")) or 0
    reference_ppm_within_tolerance = row.get(
        "prompt_reference_ppm_within_tolerance"
    )
    if reference_ppm_count > 0 and reference_ppm_within_tolerance is False:
        reviews.append("prompt_reference_peak_ppm_axis_outside_tolerance")
    elif reference_ppm_count > 0 and reference_ppm_within_tolerance is None:
        reviews.append("prompt_reference_peak_ppm_axis_tolerance_unavailable")

    for key in ("ppm_min_abs_delta", "ppm_max_abs_delta"):
        value = _safe_float(row.get(key))
        if value is None:
            reviews.append(f"{key}_unavailable")
        elif value > 0.01:
            reviews.append(f"{key}_over_0.01ppm")

    phase_delta = _safe_float(row.get("phase_delta_degrees"))
    if phase_delta is None:
        reviews.append("phase_delta_degrees_unavailable")
    elif phase_delta > 5.0:
        reviews.append("phase_delta_degrees_over_5")

    expected_baseline = _expected_baseline_method(row.get("nucleus"))
    prompt_baseline = _clean_str(row.get("baseline_prompt_method"))
    if prompt_baseline is None:
        reviews.append("prompt_baseline_method_unavailable")
    elif expected_baseline and prompt_baseline.lower() != expected_baseline:
        reviews.append("prompt_baseline_method_unexpected")

    status = "failed" if failures else "review_required" if reviews else "passed"
    return {
        "activation_readiness_status": status,
        "activation_readiness_gate_failures": failures,
        "activation_readiness_gate_reviews": reviews,
    }


def _summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(rows),
        "passed": 0,
        "review_required": 0,
        "failed": 0,
        "prompt_reference_passed": 0,
        "prompt_reference_failed": 0,
        "prompt_ppm_reference_passed": 0,
        "prompt_ppm_reference_failed": 0,
        "legacy_reference_passed": 0,
        "legacy_reference_failed": 0,
        "prompt_sidecar_available": 0,
        "prompt_sidecar_unavailable": 0,
    }
    for row in rows:
        status = str(row.get("row_status") or "failed")
        if status not in counts:
            status = "failed"
        counts[status] += 1
        if row.get("prompt_status") == "ok":
            counts["prompt_sidecar_available"] += 1
        else:
            counts["prompt_sidecar_unavailable"] += 1
        if row.get("prompt_peak_count_within_reference_tolerance") is True:
            counts["prompt_reference_passed"] += 1
        elif row.get("prompt_peak_count_within_reference_tolerance") is False:
            counts["prompt_reference_failed"] += 1
        if row.get("prompt_reference_ppm_within_tolerance") is True:
            counts["prompt_ppm_reference_passed"] += 1
        elif row.get("prompt_reference_ppm_within_tolerance") is False:
            counts["prompt_ppm_reference_failed"] += 1
        if row.get("legacy_peak_count_within_reference_tolerance") is True:
            counts["legacy_reference_passed"] += 1
        elif row.get("legacy_peak_count_within_reference_tolerance") is False:
            counts["legacy_reference_failed"] += 1
    return counts


def _activation_readiness_summary(
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, int],
) -> dict[str, Any]:
    gates = [
        _gate_all_rows(
            rows,
            name="prompt_sidecar_available",
            target="All fixture rows must produce Prompt 1/2 sidecar metadata.",
            pass_predicate=lambda row: row.get("prompt_status") == "ok",
            fail_predicate=lambda row: row.get("prompt_status") != "ok",
        ),
        _gate_all_rows(
            rows,
            name="peak_count_reference_tolerance",
            target="Prompt peak count must be within the fixture reference tolerance.",
            pass_predicate=lambda row: row.get(
                "prompt_peak_count_within_reference_tolerance"
            )
            is True,
            review_predicate=lambda row: row.get(
                "prompt_peak_count_within_reference_tolerance"
            )
            is not True,
        ),
        _gate_all_rows(
            rows,
            name="ppm_axis_alignment",
            target="Prompt and legacy ppm range endpoints must agree within 0.01 ppm.",
            pass_predicate=_row_ppm_axis_gate_passes,
            review_predicate=lambda row: not _row_ppm_axis_gate_passes(row),
        ),
        _gate_all_rows(
            rows,
            name="processed_peak_ppm_axis_alignment",
            target=(
                "When processed Bruker sidecar peak ppm references are available, "
                "the Prompt ppm axis must contain each reference within fixture tolerance."
            ),
            pass_predicate=_row_processed_peak_ppm_axis_gate_passes,
            review_predicate=lambda row: not _row_processed_peak_ppm_axis_gate_passes(row),
        ),
        _gate_all_rows(
            rows,
            name="phase_delta",
            target="Prompt phase angle delta must be within 5 degrees.",
            pass_predicate=lambda row: _safe_float(row.get("phase_delta_degrees"))
            is not None
            and _safe_float(row.get("phase_delta_degrees")) <= 5.0,
            review_predicate=lambda row: not (
                _safe_float(row.get("phase_delta_degrees")) is not None
                and _safe_float(row.get("phase_delta_degrees")) <= 5.0
            ),
        ),
        _gate_all_rows(
            rows,
            name="baseline_method",
            target=(
                "Prompt baseline method must match nucleus defaults: "
                "1H=bernstein, 13C=whittaker."
            ),
            pass_predicate=_row_baseline_gate_passes,
            review_predicate=lambda row: not _row_baseline_gate_passes(row),
        ),
        _gate_all_rows(
            rows,
            name="fingerprint_hash",
            target=(
                "Every Prompt sidecar must expose a 64-character fingerprint hash; "
                "determinism is covered by tests/test_fid_reader.py."
            ),
            pass_predicate=lambda row: row.get("prompt_hash_present") is True,
            fail_predicate=lambda row: row.get("prompt_hash_present") is not True,
        ),
        _gate_all_rows(
            rows,
            name="runtime_target",
            target="Prompt sidecar generation must complete within 3000 ms per fixture.",
            pass_predicate=lambda row: row.get("prompt_runtime_within_target") is True,
            fail_predicate=lambda row: row.get("prompt_runtime_within_target") is False,
            review_predicate=lambda row: row.get("prompt_runtime_within_target")
            is None,
        ),
        _gate_all_rows(
            rows,
            name="no_runtime_activation",
            target="Fixture diagnostics must not mark any row safe for runtime activation.",
            pass_predicate=lambda row: row.get("safe_to_activate") is False,
            fail_predicate=lambda row: row.get("safe_to_activate") is not False,
        ),
    ]
    failed = sum(1 for gate in gates if gate["status"] == "failed")
    review = sum(1 for gate in gates if gate["status"] == "review_required")
    if int(summary.get("total") or 0) <= 0:
        overall = "blocked_no_fixtures"
    elif failed:
        overall = "blocked"
    elif review:
        overall = "review_required"
    else:
        overall = "candidate_ready_for_manual_promotion"
    return {
        "version": "raw_fid_prompt_activation_readiness_v1",
        "visibility": "admin_diagnostic_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "activation_allowed": False,
        "activation_policy": (
            "blocked_until_all_gates_pass_and_a_separate_manual_promotion_is_implemented"
        ),
        "overall_status": overall,
        "gate_count": len(gates),
        "passed_gate_count": sum(1 for gate in gates if gate["status"] == "passed"),
        "review_gate_count": review,
        "failed_gate_count": failed,
        "fixture_count": int(summary.get("total") or 0),
        "gates": gates,
    }


def _gate_all_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    name: str,
    target: str,
    pass_predicate: Any,
    fail_predicate: Any | None = None,
    review_predicate: Any | None = None,
) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = []
    review: list[str] = []
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "unknown")
        if fail_predicate is not None and fail_predicate(row):
            failed.append(fixture_id)
        elif review_predicate is not None and review_predicate(row):
            review.append(fixture_id)
        elif pass_predicate(row):
            passed.append(fixture_id)
        else:
            review.append(fixture_id)
    status = "failed" if failed else "review_required" if review else "passed"
    return {
        "name": name,
        "status": status,
        "target": target,
        "total": len(rows),
        "passed": len(passed),
        "review_required": len(review),
        "failed": len(failed),
        "failed_fixtures": failed[:10],
        "review_fixtures": review[:10],
    }


def _row_ppm_axis_gate_passes(row: Mapping[str, Any]) -> bool:
    ppm_min = _safe_float(row.get("ppm_min_abs_delta"))
    ppm_max = _safe_float(row.get("ppm_max_abs_delta"))
    return ppm_min is not None and ppm_max is not None and ppm_min <= 0.01 and ppm_max <= 0.01


def _row_processed_peak_ppm_axis_gate_passes(row: Mapping[str, Any]) -> bool:
    reference_count = _safe_int(row.get("reference_peak_ppm_count")) or 0
    if reference_count <= 0:
        return True
    return row.get("prompt_reference_ppm_within_tolerance") is True


def _row_baseline_gate_passes(row: Mapping[str, Any]) -> bool:
    expected = _expected_baseline_method(row.get("nucleus"))
    method = _clean_str(row.get("baseline_prompt_method"))
    return bool(expected and method and method.lower() == expected)


def _expected_baseline_method(nucleus: Any) -> str | None:
    normalized = str(nucleus or "").upper().replace(" ", "")
    if normalized == "13C":
        return "whittaker"
    if normalized == "1H":
        return "bernstein"
    return None


def _nucleus_slug(value: Any) -> str:
    return str(value or "unknown").lower().replace(" ", "").replace("/", "_")


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_exception(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        if value is None:
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if _is_finite_number(numeric) else None


def _abs_int_delta(left: Any, right: Any) -> int | None:
    left_int = _safe_int(left)
    right_int = _safe_int(right)
    if left_int is None or right_int is None:
        return None
    return abs(left_int - right_int)


def _within_tolerance(delta: int | None, tolerance: int | None) -> bool | None:
    if delta is None or tolerance is None:
        return None
    return delta <= tolerance


def _finite_float_list(value: Any) -> list[float]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return []
    floats: list[float] = []
    for item in value:
        numeric = _safe_float(item)
        if numeric is not None:
            floats.append(numeric)
    return floats


def _nearest_uniform_axis_error(
    ppm: float,
    *,
    ppm_min: float,
    ppm_max: float,
    point_count: int,
) -> float:
    low, high = sorted((float(ppm_min), float(ppm_max)))
    if point_count < 2 or high <= low:
        return float("inf")
    step = (high - low) / float(point_count - 1)
    if ppm <= low:
        return abs(ppm - low)
    if ppm >= high:
        return abs(ppm - high)
    index = round((ppm - low) / step)
    nearest = low + index * step
    return abs(ppm - nearest)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _stable_row_for_hash(row: Mapping[str, Any]) -> dict[str, Any]:
    volatile_fields = {
        "prompt_runtime_ms",
        "prompt_runtime_within_target",
    }
    return {
        str(key): _jsonable(value)
        for key, value in row.items()
        if str(key) not in volatile_fields
    }


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _file_manifest(artifact_type: str, path: Path) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "fixture_id": "",
        "source": "",
        "vendor": "",
        "nucleus": "",
        "path": path.name,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return str(value)


def _markdown_inline(value: Any) -> str:
    text = _csv_cell(value).strip()
    if not text:
        return "-"
    return text.replace("`", "\\`").replace("|", "\\|").replace("\n", " ")


def _markdown_cell(value: Any) -> str:
    return _markdown_inline(value)


def _is_finite_number(value: Any) -> bool:
    try:
        return bool(math.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
