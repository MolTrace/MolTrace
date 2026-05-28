"""HMDB-style validation harness for the Prompt 3 GSD sidecar.

Companion to ``gsd_prompt3_validation`` (which evaluates against the
NMRShiftDB2 environment-granularity corpus).  This harness evaluates the
sidecar against a **multiplet-line-granularity** corpus modeled the way
HMDB and Pretsch publish peak references: each environment is annotated
with shift, multiplicity (s/d/t/q/...), J-couplings, and integration.

Forward-modeling approach: for each fixture, synthesize a noisy Lorentzian
spectrum from the multiplet annotations (each environment contributes
``multiplet_line_count`` Lorentzian lines spaced by ``J/field_mhz`` ppm),
run the full GSD pipeline (``gsd_peak_pick`` -> ``auto_classify`` ->
``cluster_into_environments``), and compare:

* **Raw peak count** vs ``expected_multiplet_line_count`` (the GSD raw
  output should resolve each multiplet line as a separate peak).
* **Environment count** vs ``expected_environment_count`` (the GSD
  clustered output should match the chemical-environment count).

This is the scaffold for a future production-grade corpus: drop a real
HMDB download into ``tests/fixtures/hmdb_style_minicorpus/`` with the
same schema and the harness picks it up unchanged.

CLI:
    moltrace-gsd-hmdb-sidecar-report
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter1d

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import (
    Environment,
    Peak,
    auto_classify,
    cluster_into_environments,
    gsd_peak_pick,
)

REPORT_VERSION = "gsd_hmdb_style_validation_report_v1"
DEFAULT_LEVEL = 2
DEFAULT_BUNDLE_FILENAME = "hmdb_style_minicorpus_v1.json"
DEFAULT_OUTPUT_DIR_NAME = "hmdb_style_minicorpus"

CSV_COLUMNS = [
    "fixture_id",
    "compound_name",
    "nucleus",
    "solvent",
    "row_status",
    "expected_environment_count",
    "expected_multiplet_line_count",
    "prompt_peak_count",
    "prompt_compound_peak_count",
    "prompt_environment_count",
    "prompt_compound_environment_count",
    "environment_count_delta",
    "environment_count_within_tol",
    "multiplet_line_count_delta",
    "multiplet_line_count_within_tol",
    "category_counts",
    "error",
]


# Pascal-triangle intensities for common first-order multiplets (1H).
# Higher orders (>7) collapse to equal intensities -- the GSD picker
# will still resolve them as distinct lines when spaced well enough.
_PASCAL_BY_N: dict[int, list[float]] = {
    1: [1.0],
    2: [1.0, 1.0],
    3: [1.0, 2.0, 1.0],
    4: [1.0, 3.0, 3.0, 1.0],
    5: [1.0, 4.0, 6.0, 4.0, 1.0],
    6: [1.0, 5.0, 10.0, 10.0, 5.0, 1.0],
    7: [1.0, 6.0, 15.0, 20.0, 15.0, 6.0, 1.0],
}


_MULTIPLICITY_TO_LINES: dict[str, int] = {
    "s": 1,
    "d": 2,
    "t": 3,
    "q": 4,
    "quint": 5,
    "p": 5,
    "sext": 6,
    "sept": 7,
    "m": 1,  # treat unresolved multiplet as one envelope
    "dd": 4,
    "ddd": 8,
    "dt": 6,
    "td": 6,
    "tt": 9,
}


@dataclass(slots=True, frozen=True)
class EnvironmentSpec:
    """One reference environment as published by HMDB / Pretsch / Fulmer."""

    shift_ppm: float
    multiplicity: str
    j_hz: tuple[float, ...]
    integration_h: float
    label: str = ""


@dataclass(slots=True, frozen=True)
class FixtureSpec:
    fixture_id: str
    compound_name: str
    smiles: str
    nucleus: str
    solvent: str
    field_mhz: float
    ppm_range_low: float
    ppm_range_high: float
    linewidth_hz: float
    snr_target: float
    reference_environments: tuple[EnvironmentSpec, ...]
    expected_environment_count: int
    expected_multiplet_line_count: int
    environment_count_tolerance: int
    multiplet_line_count_tolerance: int
    notes: str = ""


def load_fixture_specs(
    fixtures_root: Path, *, bundle_filename: str = DEFAULT_BUNDLE_FILENAME
) -> list[FixtureSpec]:
    bundle_path = fixtures_root / DEFAULT_OUTPUT_DIR_NAME / bundle_filename
    if not bundle_path.exists():
        return []
    payload = json.loads(bundle_path.read_text())
    specs: list[FixtureSpec] = []
    for entry in payload.get("fixtures", []):
        envs = tuple(
            EnvironmentSpec(
                shift_ppm=float(env["shift_ppm"]),
                multiplicity=str(env.get("multiplicity") or "s"),
                j_hz=tuple(float(j) for j in (env.get("j_hz") or [])),
                integration_h=float(env.get("integration_h") or 1.0),
                label=str(env.get("label") or ""),
            )
            for env in entry.get("reference_environments", [])
        )
        specs.append(
            FixtureSpec(
                fixture_id=str(entry["fixture_id"]),
                compound_name=str(entry.get("compound_name") or entry["fixture_id"]),
                smiles=str(entry.get("smiles") or ""),
                nucleus=str(entry.get("nucleus") or "1H"),
                solvent=str(entry.get("solvent") or ""),
                field_mhz=float(entry.get("field_mhz") or 400.0),
                ppm_range_low=float(entry.get("ppm_range_low") or 0.0),
                ppm_range_high=float(entry.get("ppm_range_high") or 12.0),
                linewidth_hz=float(entry.get("linewidth_hz") or 1.5),
                snr_target=float(entry.get("snr_target") or 50.0),
                reference_environments=envs,
                expected_environment_count=int(entry.get("expected_environment_count") or len(envs)),
                expected_multiplet_line_count=int(entry.get("expected_multiplet_line_count") or len(envs)),
                environment_count_tolerance=int(entry.get("environment_count_tolerance") or 0),
                multiplet_line_count_tolerance=int(entry.get("multiplet_line_count_tolerance") or 1),
                notes=str(entry.get("notes") or ""),
            )
        )
    return specs


def synthesize_spectrum(spec: FixtureSpec) -> NMRSpectrum:
    """Forward-model an NMRSpectrum from the fixture's multiplet annotations.

    For each environment, emit ``multiplet_line_count`` Lorentzian lines
    centered on ``shift_ppm``, spaced symmetrically by ``J/field_mhz`` ppm,
    with Pascal-triangle intensities scaled by ``integration_h``.  Add
    Gaussian noise calibrated to ``snr_target`` so the GSD picker has a
    realistic detection problem rather than a noise-free synthetic.
    """

    # Spectral grid: ~16k points across the ppm range gives good
    # multiplet resolution at typical 1H J values and linewidths.  For
    # 13C the natural range is wider (~240 ppm vs ~10 ppm) so the per-ppm
    # density is much lower; below we enforce a minimum HWHM relative to
    # the sample step so peaks always span enough points for GSD to
    # detect (otherwise narrow peaks collapse to single-sample spikes
    # that the picker treats as noise-vs-signal ambiguity).
    n_points = 16384
    high = max(spec.ppm_range_high, spec.ppm_range_low + 1.0)
    low = min(spec.ppm_range_low, high - 1.0)
    ppm_axis = np.linspace(high, low, n_points)  # descending (NMR convention)
    intensity = np.zeros_like(ppm_axis)

    sample_step_ppm = abs(high - low) / float(n_points - 1)
    linewidth_ppm = spec.linewidth_hz / spec.field_mhz
    # Enforce >= 6 samples per FWHM by clamping HWHM up if the manifest's
    # linewidth would otherwise be sub-sample (common pitfall on 13C
    # spectra whose natural linewidth in ppm is much smaller than the
    # spectrum's per-sample resolution).
    hwhm_ppm = max(linewidth_ppm / 2.0, 3.0 * sample_step_ppm)

    for env in spec.reference_environments:
        n_lines = _MULTIPLICITY_TO_LINES.get(env.multiplicity, 1)
        # Spacing: for simple n+1 multiplets, lines at center + (k - (n-1)/2)*J
        # where J is the first reported J (compound multiplets use only the
        # first J for the synth -- the gate still works because the harness
        # measures peak counts, not exact ppm positions).
        j_value_hz = env.j_hz[0] if env.j_hz else 0.0
        spacing_ppm = j_value_hz / spec.field_mhz
        pascal = _PASCAL_BY_N.get(n_lines)
        if pascal is None:
            pascal = [1.0] * n_lines
        pascal_norm = max(pascal)
        for line_index in range(n_lines):
            offset = (line_index - (n_lines - 1) / 2.0) * spacing_ppm
            center = env.shift_ppm + offset
            amplitude = (pascal[line_index] / pascal_norm) * env.integration_h
            dx2 = (ppm_axis - center) ** 2
            intensity += amplitude * hwhm_ppm * hwhm_ppm / (dx2 + hwhm_ppm * hwhm_ppm)

    # Gaussian noise: std = peak_intensity / snr_target.
    # Stable per-fixture seed via hashlib so noise is deterministic across
    # Python processes (Python's built-in hash() is randomized per-process
    # when PYTHONHASHSEED is unset, which makes the harness non-reproducible
    # between standalone CLI runs and pytest invocations).
    peak_intensity = float(np.max(intensity))
    noise_std = peak_intensity / max(spec.snr_target, 1.0)
    seed_int = int.from_bytes(
        hashlib.md5(spec.fixture_id.encode("utf-8")).digest()[:4], "big"
    )
    rng = np.random.default_rng(seed=seed_int)
    intensity = intensity + rng.normal(loc=0.0, scale=noise_std, size=intensity.size)

    return NMRSpectrum(
        data=intensity,
        ppm_axis=ppm_axis,
        metadata={"source": "gsd_hmdb_style_validation", "fixture_id": spec.fixture_id},
        nucleus=spec.nucleus,
        solvent=spec.solvent,
        field_mhz=spec.field_mhz,
    )


def run_fixture(spec: FixtureSpec, *, level: int = DEFAULT_LEVEL) -> dict[str, Any]:
    try:
        spectrum = synthesize_spectrum(spec)
        peaks = gsd_peak_pick(spectrum, level=level)
        classified = auto_classify(peaks, spectrum, spec.solvent)
        environments = cluster_into_environments(
            classified, field_mhz=spec.field_mhz, nucleus=spec.nucleus
        )
    except Exception as exc:  # pragma: no cover - defensive against vendor edge cases
        return _row_error(spec, f"{type(exc).__name__}: {exc}")
    return _row_success(spec, classified, environments)


def _row_success(
    spec: FixtureSpec, peaks: list[Peak], environments: list[Environment]
) -> dict[str, Any]:
    prompt_peak_count = len(peaks)
    compound_peak_count = sum(1 for p in peaks if p.category == "compound")
    env_total_count = len(environments)
    env_compound_count = sum(1 for e in environments if e.category == "compound")

    env_delta = env_compound_count - spec.expected_environment_count
    env_within_tol = abs(env_delta) <= spec.environment_count_tolerance

    line_delta = compound_peak_count - spec.expected_multiplet_line_count
    line_within_tol = abs(line_delta) <= spec.multiplet_line_count_tolerance

    category_counts: dict[str, int] = {}
    for peak in peaks:
        category_counts[peak.category] = category_counts.get(peak.category, 0) + 1

    return {
        "fixture_id": spec.fixture_id,
        "compound_name": spec.compound_name,
        "nucleus": spec.nucleus,
        "solvent": spec.solvent,
        "row_status": "ok",
        "expected_environment_count": spec.expected_environment_count,
        "expected_multiplet_line_count": spec.expected_multiplet_line_count,
        "prompt_peak_count": prompt_peak_count,
        "prompt_compound_peak_count": compound_peak_count,
        "prompt_environment_count": env_total_count,
        "prompt_compound_environment_count": env_compound_count,
        "environment_count_delta": env_delta,
        "environment_count_within_tol": env_within_tol,
        "multiplet_line_count_delta": line_delta,
        "multiplet_line_count_within_tol": line_within_tol,
        "category_counts": category_counts,
        "error": None,
    }


def _row_error(spec: FixtureSpec, error: str) -> dict[str, Any]:
    return {
        "fixture_id": spec.fixture_id,
        "compound_name": spec.compound_name,
        "nucleus": spec.nucleus,
        "solvent": spec.solvent,
        "row_status": "error",
        "expected_environment_count": spec.expected_environment_count,
        "expected_multiplet_line_count": spec.expected_multiplet_line_count,
        "prompt_peak_count": 0,
        "prompt_compound_peak_count": 0,
        "prompt_environment_count": 0,
        "prompt_compound_environment_count": 0,
        "environment_count_delta": None,
        "environment_count_within_tol": False,
        "multiplet_line_count_delta": None,
        "multiplet_line_count_within_tol": False,
        "category_counts": {},
        "error": error,
    }


def run_all(
    fixtures_root: Path,
    *,
    level: int = DEFAULT_LEVEL,
    bundle_filename: str = DEFAULT_BUNDLE_FILENAME,
) -> dict[str, Any]:
    specs = load_fixture_specs(fixtures_root, bundle_filename=bundle_filename)
    rows = [run_fixture(spec, level=level) for spec in specs]
    return build_report(rows, level=level)


def build_report(rows: list[dict[str, Any]], *, level: int) -> dict[str, Any]:
    ok_rows = [row for row in rows if row["row_status"] == "ok"]
    env_within = sum(1 for row in ok_rows if row["environment_count_within_tol"])
    line_within = sum(1 for row in ok_rows if row["multiplet_line_count_within_tol"])

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
        "environment_count_within_tol_count": env_within,
        "environment_count_within_tol_rate": (
            env_within / len(ok_rows) if ok_rows else None
        ),
        "median_abs_environment_count_delta": _median_abs("environment_count_delta"),
        "multiplet_line_count_within_tol_count": line_within,
        "multiplet_line_count_within_tol_rate": (
            line_within / len(ok_rows) if ok_rows else None
        ),
        "median_abs_multiplet_line_count_delta": _median_abs("multiplet_line_count_delta"),
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
            "Validate the Prompt 3 GSD sidecar against the HMDB-style "
            "multiplet-line-granularity mini-corpus.  Forward-models each "
            "fixture's published peak list into a noisy synthetic spectrum, "
            "runs gsd_peak_pick + auto_classify + cluster_into_environments, "
            "and reports per-fixture deltas against both the environment "
            "count and the multiplet-line count."
        )
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures",
        help="Root directory containing hmdb_style_minicorpus/*.json",
    )
    parser.add_argument(
        "--bundle",
        type=str,
        default=DEFAULT_BUNDLE_FILENAME,
        help="Bundle JSON filename under hmdb_style_minicorpus/.",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=DEFAULT_LEVEL,
        help="GSD level (1-5); higher = more sensitive.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write the JSON + CSV report. Defaults to the bundle directory.",
    )
    args = parser.parse_args()

    fixtures_root = args.fixtures_root
    report = run_all(fixtures_root, level=args.level, bundle_filename=args.bundle)
    output_dir = args.output_dir or (fixtures_root / DEFAULT_OUTPUT_DIR_NAME)
    json_path = write_report(report, output_dir)
    print(json.dumps(report["summary"], indent=2, default=str))
    print(f"Report written: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
