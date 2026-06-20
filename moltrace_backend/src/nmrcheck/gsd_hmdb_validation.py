"""Validate the Prompt 3 GSD sidecar against the curated HMDB raw-FID corpus.

Companion harness to ``gsd_prompt3_validation`` (NMRShiftDB2 corpus) and
``gsd_hmdb_style_validation`` (synthetic Pretsch/Fulmer mini-corpus).
This one closes the literal gap in the Prompt 3 spec: real HMDB raw-FID
spectra paired with HMDB-published peak-list metadata.

Pipeline per fixture (manifest at
``tests/fixtures/hmdb/expected/hmdb_validation_v1.json``):

  1. Extract the per-spectrum FID zip into a temp directory.  HMDB FID
     zips come in five different vendor / layout patterns; the extractor
     sanitises path-traversal entries and finds the dataset root
     regardless of which pattern was uploaded.
  2. ``read_fid(dataset_root)`` → ``NMRSpectrum`` via the existing
     moltrace.spectroscopy.io.fid_reader.  Wrapped with FIDReaderError /
     nmrglue parser-error handling so malformed PROCPAR / acqus files
     fail the fixture cleanly without tanking the run.
  3. Run the full GSD pipeline (``gsd_peak_pick + auto_classify +
     cluster_into_environments``).
  4. Compare against the HMDB XML reference: peak count, environment
     count, solvent auto-detect.

The HMDB solvent strings ("Water", "100%_DMSO", "5%_DMSO") are
normalised to the canonical Fulmer-table solvent keys before comparison
so the harness uses the same solvent windows the classifier does.

CLI:
    moltrace-gsd-hmdb-validation-report
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as ET  # XXE-safe parser for HMDB reference XML fixtures

from moltrace.spectroscopy.io.fid_reader import (
    FIDReaderError,
    NMRSpectrum,
    read_fid,
)
from moltrace.spectroscopy.peaks.gsd import (
    Environment,
    Peak,
    auto_classify,
    cluster_into_environments,
    gsd_peak_pick,
)

REPORT_VERSION = "gsd_hmdb_validation_report_v1"
DEFAULT_LEVEL = 2
DEFAULT_BUNDLE_FILENAME = "hmdb_validation_v1.json"
DEFAULT_OUTPUT_DIR_NAME = "hmdb"


# HMDB's solvent strings need normalising before classifier comparison;
# the Fulmer / Gottlieb table this codebase uses keys on canonical names.
_SOLVENT_NORMALISATION: dict[str, str] = {
    "Water": "D2O",  # HMDB convention: D2O experimental spectra labelled "Water"
    "water": "D2O",
    "H2O": "D2O",
    "100%_DMSO": "DMSO-d6",
    "5%_DMSO": "DMSO-d6",
    "100% DMSO": "DMSO-d6",
}

# Canonical residual-peak ppm for the simple "did we detect solvent?" check.
# Keyed on the normalised solvent name.  Pulled from Fulmer 2010 + standard
# tables; the harness counts solvent detected if any peak categorised as
# 'solvent' is within ±0.4 ppm of the canonical residual for the spectrum's
# nucleus, mirroring the gsd_prompt3_validation.py approach for NMRShiftDB2.
_SOLVENT_RESIDUAL_1H: dict[str, float] = {
    "D2O": 4.79,
    "CDCl3": 7.26,
    "DMSO-d6": 2.50,
    "CD3OD": 3.31,
    "C6D6": 7.16,
    "CD3CN": 1.94,
}
_SOLVENT_RESIDUAL_13C: dict[str, float] = {
    "CDCl3": 77.16,
    "DMSO-d6": 39.52,
    "CD3OD": 49.00,
    "C6D6": 128.06,
    "CD3CN": 1.32,
}
_SOLVENT_DETECT_TOLERANCE_PPM = 0.4


CSV_COLUMNS = [
    "fixture_id",
    "hmdb_id",
    "spectrum_id",
    "nucleus",
    "vendor",
    "solvent_raw",
    "solvent_normalised",
    "frequency",
    "row_status",
    "expected_peak_count",
    "prompt_peak_count",
    "prompt_compound_peak_count",
    "prompt_environment_count",
    "prompt_compound_environment_count",
    "compound_peak_count_delta",
    "compound_environment_count_delta",
    "solvent_reference_ppm",
    "solvent_peak_detected",
    "solvent_peak_ppm",
    "category_counts",
    "error",
]


@dataclass(slots=True, frozen=True)
class FixtureSpec:
    fixture_id: str
    hmdb_id: str
    spectrum_id: str
    nucleus: str
    solvent_raw: str
    solvent_normalised: str
    frequency: str
    vendor: str
    chemical_shift_reference: str
    expected_peak_count: int
    xml_path: Path  # absolute
    fid_zip_path: Path  # absolute


def _normalise_solvent(raw: str) -> str:
    if not raw:
        return ""
    return _SOLVENT_NORMALISATION.get(raw, raw)


def load_fixture_specs(
    fixtures_root: Path, *, bundle_filename: str = DEFAULT_BUNDLE_FILENAME
) -> list[FixtureSpec]:
    bundle_path = fixtures_root / DEFAULT_OUTPUT_DIR_NAME / "expected" / bundle_filename
    if not bundle_path.exists():
        return []
    payload = json.loads(bundle_path.read_text())
    hmdb_root = fixtures_root / DEFAULT_OUTPUT_DIR_NAME
    specs: list[FixtureSpec] = []
    for entry in payload.get("fixtures", []):
        raw_solvent = str(entry.get("solvent") or "")
        specs.append(
            FixtureSpec(
                fixture_id=str(entry["fixture_id"]),
                hmdb_id=str(entry["hmdb_id"]),
                spectrum_id=str(entry["spectrum_id"]),
                nucleus=str(entry["nucleus"]),
                solvent_raw=raw_solvent,
                solvent_normalised=_normalise_solvent(raw_solvent),
                frequency=str(entry.get("frequency") or ""),
                vendor=str(entry.get("vendor") or ""),
                chemical_shift_reference=str(entry.get("chemical_shift_reference") or ""),
                expected_peak_count=int(entry.get("expected_peak_count") or 0),
                xml_path=hmdb_root / entry["xml_path"],
                fid_zip_path=hmdb_root / entry["fid_zip_path"],
            )
        )
    return specs


def _safe_extract(zip_path: Path, dest: Path) -> None:
    """Extract a zip into ``dest`` skipping any path-traversal entries.

    HMDB FID zips occasionally contain entries like ``../94/acqus`` (the
    original uploader bundled a parent-relative dataset).  zipfile's
    default extract honours ``../`` and would write outside ``dest``.
    Strip the prefix and write inside ``dest`` so the entry is recoverable
    yet contained.
    """

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.lstrip("/")
            # Collapse any "../" / "./" prefixes.
            parts: list[str] = []
            for piece in name.split("/"):
                if piece in ("", ".", ".."):
                    continue
                parts.append(piece)
            if not parts:
                continue
            safe = "/".join(parts)
            target = dest / safe
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _find_dataset_root(extracted: Path) -> Path | None:
    """Locate the read_fid-compatible dataset root inside an extracted FID zip.

    Five HMDB layout patterns:
      1. ``acqus``/``fid`` at extract root             -> root itself (Bruker)
      2. ``<NAME>/acqus`` (1-level subdir, Bruker)
      3. ``<NAME>.FID/FID`` / ``.fid/fid`` (Varian)
      4. parent-relative entries like ``../94/acqus`` -> sanitised to ``94/``
      5. extra wrapper directories                    -> recurse
    """

    def _looks_like_bruker(p: Path) -> bool:
        names = {x.name.lower() for x in p.iterdir() if x.is_file()}
        return "acqus" in names and "fid" in names

    def _looks_like_varian(p: Path) -> bool:
        # Varian dataset: FID file (binary) + PROCPAR text file in same dir,
        # case-insensitive (HMDB uses both "FID"/"PROCPAR" and "fid"/"procpar").
        names = {x.name.lower() for x in p.iterdir() if x.is_file()}
        return ("fid" in names) and ("procpar" in names)

    # Pattern 1: root itself
    if _looks_like_bruker(extracted) or _looks_like_varian(extracted):
        return extracted
    # Patterns 2-5: walk depth-limited tree (max 8 levels) for a directory
    # that matches Bruker or Varian shape. Depth=8 covers HMDB zips whose
    # original instrument paths were e.g.
    # ``opt/topspin/data/nmrsu/nmr/Met_Tool_2D_DB/1826/`` (7 levels deep)
    # and ``Documents and Settings/<user>/Desktop/.../<sample>/`` (5+ levels).
    for depth_root, dirs, files in _walk_limited(extracted, max_depth=8):
        if _looks_like_bruker(depth_root) or _looks_like_varian(depth_root):
            return depth_root
    return None


def _walk_limited(root: Path, *, max_depth: int):
    """Yield (path, subdirs, files) up to max_depth, depth-first."""
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        path, depth = stack.pop()
        if not path.is_dir():
            continue
        try:
            children = list(path.iterdir())
        except OSError:
            continue
        subdirs = [c for c in children if c.is_dir()]
        files = [c for c in children if c.is_file()]
        yield path, subdirs, files
        if depth < max_depth:
            stack.extend((d, depth + 1) for d in subdirs)


def _parse_xml_reference(xml_path: Path) -> dict[str, Any]:
    """Extract peak-list + metadata from the HMDB XML reference."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    def gt(tag: str) -> str | None:
        el = root.find(tag)
        return (el.text or "").strip() if el is not None and el.text else None

    peaks: list[dict[str, Any]] = []
    for peak_el in root.findall("nmr-one-d-peaks/nmr-one-d-peak"):
        shift_el = peak_el.find("chemical-shift")
        intensity_el = peak_el.find("intensity")
        try:
            shift = float(shift_el.text) if shift_el is not None and shift_el.text else None
            intensity = float(intensity_el.text) if intensity_el is not None and intensity_el.text else None
        except (TypeError, ValueError):
            shift = intensity = None
        if shift is None:
            continue
        peaks.append({"shift_ppm": shift, "intensity": intensity})

    return {
        "solvent": gt("solvent"),
        "nucleus": gt("nucleus"),
        "frequency": gt("frequency"),
        "vendor": gt("instrument-type"),
        "reference_standard": gt("chemical-shift-reference"),
        "peaks": peaks,
    }


def _resolve_solvent_detection(
    *,
    spec: FixtureSpec,
    classified_peaks: list[Peak],
) -> tuple[float | None, bool, float | None]:
    """Returns (reference_ppm, detected, observed_solvent_peak_ppm)."""

    table = (
        _SOLVENT_RESIDUAL_1H
        if (spec.nucleus or "").upper() == "1H"
        else _SOLVENT_RESIDUAL_13C
    )
    ref_ppm = table.get(spec.solvent_normalised)
    if ref_ppm is None:
        return None, False, None
    for peak in classified_peaks:
        if peak.category != "solvent":
            continue
        if abs(peak.position_ppm - ref_ppm) <= _SOLVENT_DETECT_TOLERANCE_PPM:
            return ref_ppm, True, peak.position_ppm
    return ref_ppm, False, None


def run_fixture(spec: FixtureSpec, *, level: int = DEFAULT_LEVEL) -> dict[str, Any]:
    if not spec.fid_zip_path.exists() or not spec.xml_path.exists():
        return _row_error(spec, f"fixture files missing: fid={spec.fid_zip_path.exists()} xml={spec.xml_path.exists()}")
    try:
        xml_ref = _parse_xml_reference(spec.xml_path)
    except Exception as exc:
        return _row_error(spec, f"xml parse failed: {type(exc).__name__}: {exc}")

    try:
        with tempfile.TemporaryDirectory(prefix="hmdb_fid_") as td:
            td_path = Path(td)
            _safe_extract(spec.fid_zip_path, td_path)
            dataset_root = _find_dataset_root(td_path)
            if dataset_root is None:
                return _row_error(spec, "no Bruker/Varian dataset root found in extracted zip")
            try:
                spectrum = read_fid(dataset_root)
            except (FIDReaderError, Exception) as exc:
                return _row_error(spec, f"read_fid failed: {type(exc).__name__}: {exc}")
    except Exception as exc:
        return _row_error(spec, f"extract failed: {type(exc).__name__}: {exc}")

    # Patch the spectrum with the normalised solvent (HMDB's "Water" ->
    # "D2O") so auto_classify sees a canonical key the Fulmer table covers.
    if spec.solvent_normalised:
        from dataclasses import replace
        spectrum = replace(spectrum, solvent=spec.solvent_normalised)

    try:
        peaks = gsd_peak_pick(spectrum, level=level)
        classified = auto_classify(peaks, spectrum, spec.solvent_normalised or "")
        environments = cluster_into_environments(
            classified,
            field_mhz=float(spectrum.field_mhz or 500.0),
            nucleus=spec.nucleus,
        )
    except Exception as exc:
        return _row_error(spec, f"gsd pipeline failed: {type(exc).__name__}: {exc}")

    return _row_success(spec, spectrum, classified, environments, xml_ref)


def _row_success(
    spec: FixtureSpec,
    spectrum: NMRSpectrum,
    peaks: list[Peak],
    environments: list[Environment],
    xml_ref: dict[str, Any],
) -> dict[str, Any]:
    prompt_count = len(peaks)
    compound_count = sum(1 for p in peaks if p.category == "compound")
    env_count = len(environments)
    env_compound_count = sum(1 for e in environments if e.category == "compound")

    compound_delta = compound_count - spec.expected_peak_count
    env_delta = env_compound_count - spec.expected_peak_count

    solvent_ref_ppm, solvent_detected, solvent_peak_ppm = _resolve_solvent_detection(
        spec=spec, classified_peaks=peaks
    )

    category_counts: dict[str, int] = {}
    for peak in peaks:
        category_counts[peak.category] = category_counts.get(peak.category, 0) + 1

    return {
        "fixture_id": spec.fixture_id,
        "hmdb_id": spec.hmdb_id,
        "spectrum_id": spec.spectrum_id,
        "nucleus": spec.nucleus,
        "vendor": spec.vendor,
        "solvent_raw": spec.solvent_raw,
        "solvent_normalised": spec.solvent_normalised,
        "frequency": spec.frequency,
        "row_status": "ok",
        "expected_peak_count": spec.expected_peak_count,
        "prompt_peak_count": prompt_count,
        "prompt_compound_peak_count": compound_count,
        "prompt_environment_count": env_count,
        "prompt_compound_environment_count": env_compound_count,
        "compound_peak_count_delta": compound_delta,
        "compound_environment_count_delta": env_delta,
        "solvent_reference_ppm": solvent_ref_ppm,
        "solvent_peak_detected": solvent_detected,
        "solvent_peak_ppm": solvent_peak_ppm,
        "category_counts": category_counts,
        "error": None,
    }


def _row_error(spec: FixtureSpec, error: str) -> dict[str, Any]:
    return {
        "fixture_id": spec.fixture_id,
        "hmdb_id": spec.hmdb_id,
        "spectrum_id": spec.spectrum_id,
        "nucleus": spec.nucleus,
        "vendor": spec.vendor,
        "solvent_raw": spec.solvent_raw,
        "solvent_normalised": spec.solvent_normalised,
        "frequency": spec.frequency,
        "row_status": "error",
        "expected_peak_count": spec.expected_peak_count,
        "prompt_peak_count": 0,
        "prompt_compound_peak_count": 0,
        "prompt_environment_count": 0,
        "prompt_compound_environment_count": 0,
        "compound_peak_count_delta": None,
        "compound_environment_count_delta": None,
        "solvent_reference_ppm": None,
        "solvent_peak_detected": False,
        "solvent_peak_ppm": None,
        "category_counts": {},
        "error": error,
    }


def run_all(
    fixtures_root: Path,
    *,
    level: int = DEFAULT_LEVEL,
    bundle_filename: str = DEFAULT_BUNDLE_FILENAME,
    limit: int | None = None,
) -> dict[str, Any]:
    specs = load_fixture_specs(fixtures_root, bundle_filename=bundle_filename)
    if limit is not None:
        specs = specs[:limit]
    rows = [run_fixture(spec, level=level) for spec in specs]
    return build_report(rows, level=level)


def build_report(rows: list[dict[str, Any]], *, level: int) -> dict[str, Any]:
    ok_rows = [r for r in rows if r["row_status"] == "ok"]
    err_rows = [r for r in rows if r["row_status"] == "error"]
    solvent_eligible = [r for r in ok_rows if r["solvent_reference_ppm"] is not None]
    solvent_hits = sum(1 for r in solvent_eligible if r["solvent_peak_detected"])

    def _median_abs(field: str) -> float | None:
        values = sorted(
            abs(r[field]) for r in ok_rows if r.get(field) is not None
        )
        return float(values[len(values) // 2]) if values else None

    # Top error categories (truncated message → frequency)
    err_counter: dict[str, int] = {}
    for r in err_rows:
        msg = (r.get("error") or "").split(":")[0]
        err_counter[msg] = err_counter.get(msg, 0) + 1

    summary = {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "level": level,
        "fixture_count": len(rows),
        "ok_count": len(ok_rows),
        "error_count": len(err_rows),
        "parseable_rate": (len(ok_rows) / len(rows)) if rows else None,
        "error_kind_counts": err_counter,
        "fixtures_with_solvent_reference": len(solvent_eligible),
        "solvent_detected_count": solvent_hits,
        "solvent_detect_rate": (
            solvent_hits / len(solvent_eligible) if solvent_eligible else None
        ),
        "median_abs_compound_peak_count_delta": _median_abs("compound_peak_count_delta"),
        "median_abs_compound_environment_count_delta": _median_abs(
            "compound_environment_count_delta"
        ),
    }
    return {"summary": summary, "rows": rows}


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the Prompt 3 GSD sidecar against the curated HMDB raw-FID "
            "corpus.  Closes the literal Prompt 3 spec gap by running on real "
            "HMDB experimental spectra (not just NMRShiftDB2 + synthetic)."
        )
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures",
        help="Root directory containing hmdb/expected/hmdb_validation_v1.json + hmdb/{fid,xml}/.",
    )
    parser.add_argument("--bundle", type=str, default=DEFAULT_BUNDLE_FILENAME)
    parser.add_argument("--level", type=int, default=DEFAULT_LEVEL)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N fixtures (useful for quick smoke runs).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write JSON + CSV report (defaults to <fixtures_root>/hmdb).",
    )
    args = parser.parse_args()

    fixtures_root = args.fixtures_root
    report = run_all(
        fixtures_root,
        level=args.level,
        bundle_filename=args.bundle,
        limit=args.limit,
    )
    output_dir = args.output_dir or (fixtures_root / DEFAULT_OUTPUT_DIR_NAME)
    json_path = write_report(report, output_dir)
    print(json.dumps(report["summary"], indent=2, default=str))
    print(f"Report written: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
