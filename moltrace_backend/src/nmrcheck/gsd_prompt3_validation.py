"""Fixture validation runner for the Prompt 3 GSD sidecar.

This module is the next promotion gate for the Prompt 3 sidecar
(``moltrace.spectroscopy.peaks.gsd``). It is deliberately observational:
runs ``gsd_peak_pick`` + ``auto_classify`` against the curated NMRShiftDB2
fixture corpus, compares peak counts and solvent labels against the expert
reference manifest, and emits CSV+JSON reports. It does not mutate or
activate the sidecar in any production SpectraCheck path.

Promotion criteria (from the Prompt 3 spec):

* Solvent peak auto-detected on >= 95% of fixtures with a known
  residual-solvent reference shift.
* Peak count within +/- 5% of the expert manual count (with a min-1 floor
  so single-peak spectra don't trivially fail). The per-fixture manifest
  tolerance (default 2) is reported alongside for context.

The module mirrors the structure of ``raw_fid_prompt_validation`` so the
two sidecars share an idiomatic harness shape.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum, read_fid
from moltrace.spectroscopy.peaks.gsd import (
    Environment,
    Peak,
    auto_classify,
    cluster_into_environments,
    gsd_peak_pick,
)

# Default spectrometer frequency for clustering when the FID metadata does
# not provide one; mirrors moltrace.spectroscopy.peaks.gsd._DEFAULT_FIELD_MHZ.
_DEFAULT_FIELD_MHZ = 500.0

REPORT_VERSION = "gsd_prompt3_validation_report_v1"
DEFAULT_OUTPUT_DIRNAME = "gsd_prompt3_validation"
DEFAULT_LEVEL = 2
DEFAULT_BUNDLE_FILENAME = "nmrshiftdb2_bruker_20.json"
SOLVENT_PPM_WINDOW = 0.20

# Fulmer/Gottlieb residual-solvent reference shifts.  The keys are the
# normalised solvent token (uppercased, "-" and "_" stripped) so we can match
# both ``DMSO-d6`` and ``DMSOD6`` from different acqus exports without bespoke
# parsing.  These are not exhaustive -- the gate only needs to cover the
# fixture corpus, plus the small set of common solvents pharma R&D uses.
_SOLVENT_REFERENCE_PPM_1H: dict[str, float] = {
    "CDCL3": 7.26,
    "DMSO": 2.50,
    "DMSOD6": 2.50,
    "ACETONE": 2.05,
    "ACETONED6": 2.05,
    "CD3OD": 3.31,
    "METHANOLD4": 3.31,
    "MEOD": 3.31,
    "D2O": 4.79,
    "C6D6": 7.16,
    "BENZENED6": 7.16,
    "CD3CN": 1.94,
    "ACETONITRILED3": 1.94,
    "THF": 3.58,
    "THFD8": 3.58,
}
_SOLVENT_REFERENCE_PPM_13C: dict[str, float] = {
    "CDCL3": 77.16,
    "DMSO": 39.52,
    "DMSOD6": 39.52,
    "ACETONE": 29.84,
    "ACETONED6": 29.84,
    "CD3OD": 49.00,
    "METHANOLD4": 49.00,
    "MEOD": 49.00,
    "C6D6": 128.06,
    "BENZENED6": 128.06,
    "CD3CN": 118.26,
    "ACETONITRILED3": 118.26,
    "THF": 67.21,
    "THFD8": 67.21,
}

CSV_COLUMNS = [
    "fixture_id",
    "spectrum_id",
    "nucleus",
    "solvent",
    "row_status",
    "reference_peak_count",
    "prompt_peak_count",
    "prompt_compound_peak_count",
    "prompt_environment_count",
    "prompt_compound_environment_count",
    "compound_peak_count_delta",
    "compound_peak_count_within_5pct",
    "compound_peak_count_within_manifest_tol",
    "compound_environment_count_delta",
    "compound_environment_count_within_manifest_tol",
    "peak_count_delta",
    "peak_count_within_5pct",
    "peak_count_within_manifest_tol",
    "manifest_peak_count_tolerance",
    "reference_ppm_count_matched",
    "reference_ppm_max_error",
    "reference_ppm_mean_error",
    "reference_ppm_within_tolerance",
    "reference_ppm_unmatched_count",
    "reference_ppm_plausibility_threshold",
    "solvent_reference_ppm",
    "solvent_peak_detected",
    "solvent_peak_ppm",
    "category_counts",
    "error",
]


@dataclass(slots=True, frozen=True)
class FixtureSpec:
    """One curated NMRShiftDB2 fixture expected reference."""

    fixture_id: str
    spectrum_id: str
    nucleus: str
    archive: str
    extracted_path: str  # relative to ``tests/fixtures/nmrshiftdb2``
    reference_peak_ppm: list[float]
    reference_peak_count: int
    ppm_tolerance: float
    peak_count_tolerance: int


def load_fixture_specs(
    fixtures_root: Path,
    *,
    bundle_filename: str = DEFAULT_BUNDLE_FILENAME,
) -> list[FixtureSpec]:
    """Load the curated NMRShiftDB2 manifest bundle into typed fixture specs.

    Only the bundle is loaded because the single-fixture detailed JSONs in
    ``expected/`` use a ``db_id``-based ``extracted_path`` that does not match
    the on-disk ``spectrum_id``-based directory names.  The bundle is the
    single source of truth for paths + reference peak lists; solvent ground
    truth is read from each FID's acqus on the fly via ``read_fid``.
    """

    bundle_path = fixtures_root / "nmrshiftdb2" / "expected" / bundle_filename
    if not bundle_path.exists():
        return []
    with bundle_path.open() as fh:
        bundle = json.load(fh)
    specs: list[FixtureSpec] = []
    for entry in bundle.get("fixtures", []):
        spectrum_id = str(entry.get("spectrum_id", "unknown"))
        nucleus = str(entry.get("nucleus", "unknown"))
        ppm_list = entry.get("reference_peak_ppm") or entry.get("expected_peak_ppm") or []
        specs.append(
            FixtureSpec(
                fixture_id=f"nmrshiftdb2_{spectrum_id}_{nucleus.lower()}",
                spectrum_id=spectrum_id,
                nucleus=nucleus,
                archive=str(entry.get("archive", "")),
                extracted_path=str(entry.get("extracted_path", "")),
                reference_peak_ppm=[float(v) for v in ppm_list],
                reference_peak_count=int(entry.get("reference_peak_count", len(ppm_list))),
                ppm_tolerance=float(entry.get("ppm_tolerance", 0.01)),
                peak_count_tolerance=int(entry.get("peak_count_tolerance", 2)),
            )
        )
    return specs


def run_fixture(
    spec: FixtureSpec,
    fixtures_root: Path,
    *,
    level: int = DEFAULT_LEVEL,
) -> dict[str, Any]:
    """Process one fixture, returning a serialisable result row."""

    dataset_path = fixtures_root / "nmrshiftdb2" / spec.extracted_path
    if not dataset_path.exists():
        return _row_error(spec, f"dataset not extracted at {dataset_path}")
    try:
        spectrum = read_fid(dataset_path)
        peaks = gsd_peak_pick(spectrum, level=level)
        solvent_value = spectrum.solvent or ""
        classified = auto_classify(peaks, spectrum, solvent_value)
        environments = cluster_into_environments(
            classified,
            field_mhz=float(spectrum.field_mhz or _DEFAULT_FIELD_MHZ),
            nucleus=spec.nucleus,
        )
    except Exception as exc:  # pragma: no cover - defensive against vendor edge cases
        return _row_error(spec, f"{type(exc).__name__}: {exc}")
    return _row_success(spec, spectrum, classified, environments)


def run_all(
    fixtures_root: Path,
    *,
    level: int = DEFAULT_LEVEL,
    bundle_filename: str = DEFAULT_BUNDLE_FILENAME,
) -> dict[str, Any]:
    """Run the harness across every fixture in the bundle and build a report."""

    specs = load_fixture_specs(fixtures_root, bundle_filename=bundle_filename)
    rows = [run_fixture(spec, fixtures_root, level=level) for spec in specs]
    return build_report(rows, level=level)


def build_report(rows: list[dict[str, Any]], *, level: int) -> dict[str, Any]:
    ok_rows = [row for row in rows if row["row_status"] == "ok"]
    solvent_eligible = [row for row in ok_rows if row["solvent_reference_ppm"] is not None]
    solvent_hits = sum(1 for row in solvent_eligible if row["solvent_peak_detected"])
    within_5pct_total = sum(1 for row in ok_rows if row["peak_count_within_5pct"])
    within_5pct_compound = sum(1 for row in ok_rows if row["compound_peak_count_within_5pct"])
    within_manifest_total = sum(1 for row in ok_rows if row["peak_count_within_manifest_tol"])
    within_manifest_compound = sum(
        1 for row in ok_rows if row["compound_peak_count_within_manifest_tol"]
    )
    within_manifest_compound_env = sum(
        1
        for row in ok_rows
        if row.get("compound_environment_count_within_manifest_tol")
    )

    def _median_abs(field: str) -> float | None:
        values = sorted(
            abs(row[field]) for row in ok_rows if row.get(field) is not None
        )
        return float(values[len(values) // 2]) if values else None

    summary = {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "level": level,
        "fixture_count": len(rows),
        "ok_count": len(ok_rows),
        "error_count": len(rows) - len(ok_rows),
        "fixtures_with_solvent_reference": len(solvent_eligible),
        "solvent_detected_count": solvent_hits,
        "solvent_detect_rate": (
            solvent_hits / len(solvent_eligible) if solvent_eligible else None
        ),
        # Compound-only metrics are the primary gate: NMRShiftDB2's reference
        # peak list is curated to molecular peaks, not raw detection.  The
        # total-prompt metrics stay in the report as diagnostic context.
        "compound_peak_count_within_5pct_count": within_5pct_compound,
        "compound_peak_count_within_5pct_rate": (
            within_5pct_compound / len(ok_rows) if ok_rows else None
        ),
        "compound_peak_count_within_manifest_tol_count": within_manifest_compound,
        "compound_peak_count_within_manifest_tol_rate": (
            within_manifest_compound / len(ok_rows) if ok_rows else None
        ),
        "median_abs_compound_peak_count_delta": _median_abs("compound_peak_count_delta"),
        # Environment-count metrics: the semantically correct primary gate
        # per FE A/B finding (NMRShiftDB2 counts environments, not lines).
        "compound_environment_count_within_manifest_tol_count": within_manifest_compound_env,
        "compound_environment_count_within_manifest_tol_rate": (
            within_manifest_compound_env / len(ok_rows) if ok_rows else None
        ),
        "median_abs_compound_environment_count_delta": _median_abs(
            "compound_environment_count_delta"
        ),
        "peak_count_within_5pct_count": within_5pct_total,
        "peak_count_within_5pct_rate": within_5pct_total / len(ok_rows) if ok_rows else None,
        "peak_count_within_manifest_tol_count": within_manifest_total,
        "peak_count_within_manifest_tol_rate": (
            within_manifest_total / len(ok_rows) if ok_rows else None
        ),
        "median_abs_peak_count_delta": _median_abs("peak_count_delta"),
    }
    return {"summary": summary, "rows": rows}


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
    """Persist the JSON + CSV artifacts; returns the JSON path."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{REPORT_VERSION}_{timestamp}.json"
    csv_path = output_dir / f"{REPORT_VERSION}_{timestamp}.csv"
    with json_path.open("w") as fh:
        json.dump(report, fh, indent=2, default=str)
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in report["rows"]:
            csv_row = {key: row.get(key) for key in CSV_COLUMNS}
            csv_row["category_counts"] = json.dumps(row.get("category_counts", {}))
            writer.writerow(csv_row)
    return json_path


def _row_error(spec: FixtureSpec, error: str) -> dict[str, Any]:
    return {
        "fixture_id": spec.fixture_id,
        "spectrum_id": spec.spectrum_id,
        "nucleus": spec.nucleus,
        "solvent": "",
        "row_status": "error",
        "reference_peak_count": spec.reference_peak_count,
        "prompt_peak_count": 0,
        "prompt_compound_peak_count": 0,
        "prompt_environment_count": 0,
        "prompt_compound_environment_count": 0,
        "compound_peak_count_delta": None,
        "compound_peak_count_within_5pct": False,
        "compound_peak_count_within_manifest_tol": False,
        "compound_environment_count_delta": None,
        "compound_environment_count_within_manifest_tol": False,
        "peak_count_delta": None,
        "peak_count_within_5pct": False,
        "peak_count_within_manifest_tol": False,
        "manifest_peak_count_tolerance": spec.peak_count_tolerance,
        "reference_ppm_count_matched": 0,
        "reference_ppm_max_error": None,
        "reference_ppm_mean_error": None,
        "reference_ppm_within_tolerance": False,
        "reference_ppm_unmatched_count": None,
        "reference_ppm_plausibility_threshold": None,
        "solvent_reference_ppm": None,
        "solvent_peak_detected": False,
        "solvent_peak_ppm": None,
        "category_counts": {},
        "error": error,
    }


def _row_success(
    spec: FixtureSpec,
    spectrum: NMRSpectrum,
    peaks: list[Peak],
    environments: list[Environment],
) -> dict[str, Any]:
    prompt_count = len(peaks)
    compound_count = sum(1 for peak in peaks if peak.category == "compound")
    env_total_count = len(environments)
    env_compound_count = sum(
        1 for env in environments if env.category == "compound"
    )

    pct_tolerance = max(1, int(math.ceil(spec.reference_peak_count * 0.05)))

    total_delta = prompt_count - spec.reference_peak_count
    within_5pct_total = abs(total_delta) <= pct_tolerance
    within_manifest_tol_total = abs(total_delta) <= spec.peak_count_tolerance

    compound_delta = compound_count - spec.reference_peak_count
    within_5pct_compound = abs(compound_delta) <= pct_tolerance
    within_manifest_tol_compound = abs(compound_delta) <= spec.peak_count_tolerance

    # Environment-count delta is the semantically correct primary gate:
    # NMRShiftDB2's reference shift list counts chemical environments (one
    # entry per H/C atom), not multiplet lines.  An accurate detector
    # legitimately resolves a doublet as 2 peaks but the reference treats
    # it as 1 entry.  Clustering peaks back into environments restores the
    # apples-to-apples comparison.
    compound_env_delta = env_compound_count - spec.reference_peak_count
    within_manifest_tol_compound_env = (
        abs(compound_env_delta) <= spec.peak_count_tolerance
    )

    # Per-reference-ppm match against the compound-category peaks (the
    # curated reference shifts describe molecular peaks).
    #
    # Plausibility-bounded matching: when no detected peak sits within a
    # plausible chemical-window of the reference shift, the reference is
    # considered un-detected -- recording the distance to the nearest
    # (potentially whole-spectrum-width) peak inflates max_error into
    # meaningless territory (e.g., 89 ppm on a 13C trace says "the peak is
    # missing entirely", not "our position prediction is 89 ppm off").
    # Plausibility windows: 0.5 ppm for 1H (wider than the typical 0.05 ppm
    # tolerance but narrow enough to exclude chemical-environment confusion),
    # 5.0 ppm for 13C (where line widths and referencing drift are larger).
    plausibility_ppm = 0.5 if (spec.nucleus or "").upper() == "1H" else 5.0
    compound_ppm = sorted(peak.position_ppm for peak in peaks if peak.category == "compound")
    matched = 0
    ppm_errors: list[float] = []
    unmatched_refs: list[float] = []
    for ref in spec.reference_peak_ppm:
        if not compound_ppm:
            unmatched_refs.append(float(ref))
            continue
        nearest = min(compound_ppm, key=lambda value: abs(value - ref))
        ppm_delta = abs(nearest - ref)
        if ppm_delta > plausibility_ppm:
            unmatched_refs.append(float(ref))
            continue
        ppm_errors.append(ppm_delta)
        if ppm_delta <= spec.ppm_tolerance:
            matched += 1
    max_err = max(ppm_errors) if ppm_errors else None
    mean_err = sum(ppm_errors) / len(ppm_errors) if ppm_errors else None
    ppm_within = matched == len(spec.reference_peak_ppm) if spec.reference_peak_ppm else None
    unmatched_count = len(unmatched_refs)

    solvent_ref_ppm, solvent_detected, solvent_peak_ppm = _resolve_solvent_detection(
        spectrum=spectrum, nucleus=spec.nucleus, peaks=peaks
    )

    category_counts: dict[str, int] = {}
    for peak in peaks:
        category_counts[peak.category] = category_counts.get(peak.category, 0) + 1

    return {
        "fixture_id": spec.fixture_id,
        "spectrum_id": spec.spectrum_id,
        "nucleus": spec.nucleus,
        "solvent": spectrum.solvent,
        "row_status": "ok",
        "reference_peak_count": spec.reference_peak_count,
        "prompt_peak_count": prompt_count,
        "prompt_compound_peak_count": compound_count,
        "prompt_environment_count": env_total_count,
        "prompt_compound_environment_count": env_compound_count,
        "compound_peak_count_delta": compound_delta,
        "compound_peak_count_within_5pct": within_5pct_compound,
        "compound_peak_count_within_manifest_tol": within_manifest_tol_compound,
        "compound_environment_count_delta": compound_env_delta,
        "compound_environment_count_within_manifest_tol": within_manifest_tol_compound_env,
        "peak_count_delta": total_delta,
        "peak_count_within_5pct": within_5pct_total,
        "peak_count_within_manifest_tol": within_manifest_tol_total,
        "manifest_peak_count_tolerance": spec.peak_count_tolerance,
        "reference_ppm_count_matched": matched,
        "reference_ppm_max_error": max_err,
        "reference_ppm_mean_error": mean_err,
        "reference_ppm_within_tolerance": ppm_within,
        "reference_ppm_unmatched_count": unmatched_count,
        "reference_ppm_plausibility_threshold": plausibility_ppm,
        "solvent_reference_ppm": solvent_ref_ppm,
        "solvent_peak_detected": solvent_detected,
        "solvent_peak_ppm": solvent_peak_ppm,
        "category_counts": category_counts,
        "error": None,
    }


def _resolve_solvent_detection(
    *,
    spectrum: NMRSpectrum,
    nucleus: str,
    peaks: list[Peak],
) -> tuple[float | None, bool, float | None]:
    """Return (solvent_reference_ppm, detected, solvent_peak_ppm).

    Detection tolerance is taken from ``peak_categorization.categorize_peak``'s
    own solvent window (e.g. CDCl3 13C is 76.3-77.7 to cover the J(CD)
    satellites, much wider than a hardcoded fixed window).  This keeps the
    harness consistent with auto_classify: any peak the classifier *can*
    legitimately label as solvent counts as detected.
    """

    normalised = (spectrum.solvent or "").upper().replace("-", "").replace("_", "")
    if not normalised:
        return None, False, None
    table = (
        _SOLVENT_REFERENCE_PPM_1H if nucleus.upper() == "1H" else _SOLVENT_REFERENCE_PPM_13C
    )
    reference_ppm: float | None = None
    for key, ppm in table.items():
        if key in normalised:
            reference_ppm = ppm
            break
    if reference_ppm is None:
        return None, False, None

    low = reference_ppm - SOLVENT_PPM_WINDOW
    high = reference_ppm + SOLVENT_PPM_WINDOW
    try:
        from nmrcheck.peak_categorization import categorize_peak

        detail = categorize_peak(
            nucleus=nucleus.upper(),  # type: ignore[arg-type]
            shift_ppm=reference_ppm,
            solvent=spectrum.solvent,
        )
        solvent_hit = detail.get("solvent_hit") if isinstance(detail, dict) else None
        if isinstance(solvent_hit, dict):
            low_value = solvent_hit.get("low_ppm")
            high_value = solvent_hit.get("high_ppm")
            if low_value is not None and high_value is not None:
                low = float(low_value)
                high = float(high_value)
    except Exception:  # pragma: no cover - defensive against categorisation import shifts
        pass

    for peak in peaks:
        if peak.category == "solvent" and low <= peak.position_ppm <= high:
            return reference_ppm, True, peak.position_ppm
    return reference_ppm, False, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prompt 3 GSD fixture validation runner.")
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "tests" / "fixtures",
        help="Path to tests/fixtures.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write the report (default: <fixtures-root>/gsd_prompt3_validation).",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=DEFAULT_LEVEL,
        help="GSD level 1-5 (default 2).",
    )
    parser.add_argument(
        "--bundle",
        type=str,
        default=DEFAULT_BUNDLE_FILENAME,
        help=f"Manifest bundle filename (default {DEFAULT_BUNDLE_FILENAME}).",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir or (args.fixtures_root / DEFAULT_OUTPUT_DIRNAME)
    report = run_all(args.fixtures_root, level=args.level, bundle_filename=args.bundle)
    path = write_report(report, output_dir)
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
