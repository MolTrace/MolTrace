"""Karplus vicinal-3J validation harness for the Week-40 multiplet layer.

Companion to the GSD/HMDB validation harnesses, but targeting the **opt-in
Karplus refinement** of ``jcoupling_prediction`` rather than the GSD peak
picker.  Where the GSD harnesses forward-model synthetic spectra, this
harness drives the topological J predictor directly with ``use_karplus=True``
and grades its conformer-averaged vicinal couplings against literature.

Approach: for each fixture, call
``predict_proton_couplings_from_smiles(smiles, use_karplus=True,
karplus_method=method)``, collect every coupling whose ``detail.category``
matches the method (``aliphatic_vicinal_karplus`` for the generic three-term
relation, ``aliphatic_vicinal_haasnoot_altona`` for the Haasnoot-de Leeuw-
Altona generalized relation), take the **maximum** as the diagnostic vicinal
coupling for that molecule, and compare it to the fixture's
``expected_max_vicinal_j_hz`` (the largest vicinal 3J a chemist would report
for that system, drawn from literature).  The harness is method-aware
(``method=`` keyword on ``run_fixture``/``run_all``/``build_report`` and the
``--method`` CLI flag) so the same corpus can be graded under either relation
and the two reports compared head-to-head.

Why the *maximum* and not a per-bond match: the predictor keys each coupling
by carbon-atom-index pair, which is fragile to map back onto named protons
across arbitrary SMILES atom orderings.  The maximum vicinal coupling is the
robust, order-independent diagnostic that captures the scientifically
meaningful claim the refinement makes -- "a conformationally **locked**
diaxial coupling is recognised as a large (~9-11 Hz) coupling, while a
**mobile/averaged** system collapses to ~6.5-7.5 Hz."  The corpus is split
into ``locked_diaxial`` and (``mobile_averaged`` / ``acyclic_averaged``)
kinds so the report can measure that discrimination directly.

This is a **semi-quantitative discrimination gate**, not a sub-Hz
prediction claim: the generic three-term Karplus relation caps near
10.26 Hz at 180 degrees and omits the electronegativity corrections that
Haasnoot-Altona adds for sugars, so per-entry tolerances are 1.5-2.5 Hz.

CLI:
    moltrace-karplus-jcoupling-report
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nmrcheck.jcoupling_prediction import (
    CONFORMER_WEIGHTING_DEFAULT,
    CONFORMER_WEIGHTINGS,
    KARPLUS_CATEGORY_GENERIC,
    KARPLUS_CATEGORY_HAASNOOT_ALTONA,
    KARPLUS_DEFAULT_MAX_CONFORMERS,
    KARPLUS_DEFAULT_METHOD,
    KARPLUS_METHOD_GENERIC,
    KARPLUS_METHOD_HAASNOOT_ALTONA,
    KARPLUS_METHODS,
    KARPLUS_RANDOM_SEED,
    predict_proton_couplings_from_smiles,
)

REPORT_VERSION = "karplus_jcoupling_validation_report_v1"
DEFAULT_BUNDLE_FILENAME = "karplus_jcoupling_corpus_v1.json"
DEFAULT_OUTPUT_DIR_NAME = "karplus_jcoupling_corpus"

# The detail category emitted by the opt-in Karplus refinement depends on the
# method: the generic three-term relation emits ``aliphatic_vicinal_karplus``
# while the Haasnoot-de Leeuw-Altona generalized relation emits
# ``aliphatic_vicinal_haasnoot_altona``.  The harness is method-aware so the
# same corpus can be graded under either relation and the two reports compared.
_CATEGORY_BY_METHOD = {
    KARPLUS_METHOD_GENERIC: KARPLUS_CATEGORY_GENERIC,
    KARPLUS_METHOD_HAASNOOT_ALTONA: KARPLUS_CATEGORY_HAASNOOT_ALTONA,
}
# Back-compat alias (generic category) for callers that imported the old name.
KARPLUS_CATEGORY = KARPLUS_CATEGORY_GENERIC
# Fixtures whose ``kind`` is this value are expected to RECOVER a large
# diaxial coupling; every other kind is treated as mobile/averaged.
LOCKED_KIND = "locked_diaxial"


def category_for_method(method: str) -> str:
    """Return the ``detail.category`` string emitted by ``method``'s refinement.

    Raises ``ValueError`` for an unknown method so a typo in a harness call or
    CLI flag fails loudly rather than silently grading zero couplings.
    """

    if method not in KARPLUS_METHODS:
        raise ValueError(
            f"Unknown karplus method {method!r}; expected one of {KARPLUS_METHODS}."
        )
    return _CATEGORY_BY_METHOD[method]

CSV_COLUMNS = [
    "fixture_id",
    "compound_name",
    "smiles",
    "kind",
    "method",
    "weighting",
    "row_status",
    "expected_max_vicinal_j_hz",
    "tolerance_hz",
    "predicted_max_vicinal_j_hz",
    "predicted_min_vicinal_j_hz",
    "karplus_coupling_count",
    "abs_error_hz",
    "within_tol",
    "max_predicted_hz",
    "invalid_structure",
    "warnings",
    "error",
]


@dataclass(slots=True, frozen=True)
class KarplusFixtureSpec:
    """One molecule with a literature-known diagnostic vicinal 3J."""

    fixture_id: str
    compound_name: str
    smiles: str
    kind: str
    expected_max_vicinal_j_hz: float
    tolerance_hz: float
    literature_note: str = ""
    notes: str = ""


def load_fixture_specs(
    fixtures_root: Path, *, bundle_filename: str = DEFAULT_BUNDLE_FILENAME
) -> list[KarplusFixtureSpec]:
    bundle_path = fixtures_root / DEFAULT_OUTPUT_DIR_NAME / bundle_filename
    if not bundle_path.exists():
        return []
    payload = json.loads(bundle_path.read_text())
    specs: list[KarplusFixtureSpec] = []
    for entry in payload.get("fixtures", []):
        specs.append(
            KarplusFixtureSpec(
                fixture_id=str(entry["fixture_id"]),
                compound_name=str(entry.get("compound_name") or entry["fixture_id"]),
                smiles=str(entry["smiles"]),
                kind=str(entry.get("kind") or LOCKED_KIND),
                expected_max_vicinal_j_hz=float(entry["expected_max_vicinal_j_hz"]),
                tolerance_hz=float(entry.get("tolerance_hz") or 2.0),
                literature_note=str(entry.get("literature_note") or ""),
                notes=str(entry.get("notes") or ""),
            )
        )
    return specs


def run_fixture(
    spec: KarplusFixtureSpec,
    *,
    method: str = KARPLUS_DEFAULT_METHOD,
    weighting: str = CONFORMER_WEIGHTING_DEFAULT,
    max_conformers: int = KARPLUS_DEFAULT_MAX_CONFORMERS,
    seed: int = KARPLUS_RANDOM_SEED,
) -> dict[str, Any]:
    category = category_for_method(method)
    try:
        result = predict_proton_couplings_from_smiles(
            spec.smiles,
            use_karplus=True,
            karplus_method=method,
            karplus_conformer_weighting=weighting,
            karplus_max_conformers=max_conformers,
            karplus_seed=seed,
        )
    except Exception as exc:  # pragma: no cover - defensive against vendor edge cases
        return _row_error(
            spec, f"{type(exc).__name__}: {exc}", method=method, weighting=weighting
        )

    if result.invalid_structure:
        return _row_error(
            spec, "invalid_structure", warnings=list(result.warnings),
            method=method, weighting=weighting,
        )

    karplus_js = [d.j_hz for d in result.details if d.category == category]
    if not karplus_js:
        return _row_error(
            spec,
            f"no {category} couplings emitted",
            warnings=list(result.warnings),
            method=method,
            weighting=weighting,
        )

    return _row_success(spec, result, karplus_js, method=method, weighting=weighting)


def _row_success(
    spec: KarplusFixtureSpec,
    result: Any,
    karplus_js: list[float],
    *,
    method: str = KARPLUS_DEFAULT_METHOD,
    weighting: str = CONFORMER_WEIGHTING_DEFAULT,
) -> dict[str, Any]:
    predicted_max = max(karplus_js)
    predicted_min = min(karplus_js)
    abs_error = abs(predicted_max - spec.expected_max_vicinal_j_hz)
    within_tol = abs_error <= spec.tolerance_hz
    return {
        "fixture_id": spec.fixture_id,
        "compound_name": spec.compound_name,
        "smiles": spec.smiles,
        "kind": spec.kind,
        "method": method,
        "weighting": weighting,
        "row_status": "ok",
        "expected_max_vicinal_j_hz": spec.expected_max_vicinal_j_hz,
        "tolerance_hz": spec.tolerance_hz,
        "predicted_max_vicinal_j_hz": round(predicted_max, 2),
        "predicted_min_vicinal_j_hz": round(predicted_min, 2),
        "karplus_coupling_count": len(karplus_js),
        "abs_error_hz": round(abs_error, 2),
        "within_tol": within_tol,
        "max_predicted_hz": result.max_predicted_hz,
        "invalid_structure": False,
        "warnings": list(result.warnings),
        "error": None,
    }


def _row_error(
    spec: KarplusFixtureSpec,
    error: str,
    *,
    warnings: list[str] | None = None,
    method: str = KARPLUS_DEFAULT_METHOD,
    weighting: str = CONFORMER_WEIGHTING_DEFAULT,
) -> dict[str, Any]:
    return {
        "fixture_id": spec.fixture_id,
        "compound_name": spec.compound_name,
        "smiles": spec.smiles,
        "kind": spec.kind,
        "method": method,
        "weighting": weighting,
        "row_status": "error",
        "expected_max_vicinal_j_hz": spec.expected_max_vicinal_j_hz,
        "tolerance_hz": spec.tolerance_hz,
        "predicted_max_vicinal_j_hz": None,
        "predicted_min_vicinal_j_hz": None,
        "karplus_coupling_count": 0,
        "abs_error_hz": None,
        "within_tol": False,
        "max_predicted_hz": None,
        "invalid_structure": error == "invalid_structure",
        "warnings": warnings or [],
        "error": error,
    }


def run_all(
    fixtures_root: Path,
    *,
    method: str = KARPLUS_DEFAULT_METHOD,
    weighting: str = CONFORMER_WEIGHTING_DEFAULT,
    max_conformers: int = KARPLUS_DEFAULT_MAX_CONFORMERS,
    seed: int = KARPLUS_RANDOM_SEED,
    bundle_filename: str = DEFAULT_BUNDLE_FILENAME,
) -> dict[str, Any]:
    specs = load_fixture_specs(fixtures_root, bundle_filename=bundle_filename)
    rows = [
        run_fixture(
            spec, method=method, weighting=weighting,
            max_conformers=max_conformers, seed=seed,
        )
        for spec in specs
    ]
    return build_report(
        rows, method=method, weighting=weighting,
        max_conformers=max_conformers, seed=seed,
    )


def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def build_report(
    rows: list[dict[str, Any]],
    *,
    method: str = KARPLUS_DEFAULT_METHOD,
    weighting: str = CONFORMER_WEIGHTING_DEFAULT,
    max_conformers: int = KARPLUS_DEFAULT_MAX_CONFORMERS,
    seed: int = KARPLUS_RANDOM_SEED,
) -> dict[str, Any]:
    ok_rows = [row for row in rows if row["row_status"] == "ok"]
    abs_errors = [row["abs_error_hz"] for row in ok_rows]
    within_tol_count = sum(1 for row in ok_rows if row["within_tol"])

    locked_predicted = [
        row["predicted_max_vicinal_j_hz"]
        for row in ok_rows
        if row["kind"] == LOCKED_KIND
    ]
    mobile_predicted = [
        row["predicted_max_vicinal_j_hz"]
        for row in ok_rows
        if row["kind"] != LOCKED_KIND
    ]

    mean_locked = _mean(locked_predicted)
    mean_mobile = _mean(mobile_predicted)
    min_locked = min(locked_predicted) if locked_predicted else None
    max_mobile = max(mobile_predicted) if mobile_predicted else None

    if min_locked is not None and max_mobile is not None:
        separation_hz: float | None = round(min_locked - max_mobile, 2)
        clean_separation = min_locked > max_mobile
    else:
        separation_hz = None
        clean_separation = False

    summary = {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "method": method,
        "weighting": weighting,
        "category": category_for_method(method),
        "max_conformers": max_conformers,
        "seed": seed,
        "fixture_count": len(rows),
        "ok_count": len(ok_rows),
        "error_count": len(rows) - len(ok_rows),
        "within_tol_count": within_tol_count,
        "within_tol_rate": (within_tol_count / len(ok_rows) if ok_rows else None),
        "mean_abs_error_hz": (round(_mean(abs_errors), 4) if abs_errors else None),
        "median_abs_error_hz": (round(_median(abs_errors), 4) if abs_errors else None),
        "max_abs_error_hz": (round(max(abs_errors), 4) if abs_errors else None),
        "locked_count": len(locked_predicted),
        "mobile_count": len(mobile_predicted),
        "mean_locked_predicted_max_hz": (round(mean_locked, 4) if mean_locked is not None else None),
        "mean_mobile_predicted_max_hz": (round(mean_mobile, 4) if mean_mobile is not None else None),
        "min_locked_predicted_max_hz": min_locked,
        "max_mobile_predicted_max_hz": max_mobile,
        "locked_vs_mobile_separation_hz": separation_hz,
        "clean_locked_vs_mobile_separation": clean_separation,
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
            csv_row["warnings"] = json.dumps(row.get("warnings", []))
            writer.writerow(csv_row)
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the opt-in Karplus refinement of the Week-40 multiplet "
            "J-coupling layer against a hand-curated literature vicinal-3J "
            "corpus.  Drives predict_proton_couplings_from_smiles(use_karplus="
            "True) per fixture and reports the diagnostic maximum vicinal "
            "coupling against the literature value, plus the locked-vs-mobile "
            "discrimination separation."
        )
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures",
        help="Root directory containing karplus_jcoupling_corpus/*.json",
    )
    parser.add_argument(
        "--bundle",
        type=str,
        default=DEFAULT_BUNDLE_FILENAME,
        help="Bundle JSON filename under karplus_jcoupling_corpus/.",
    )
    parser.add_argument(
        "--method",
        type=str,
        default=KARPLUS_DEFAULT_METHOD,
        choices=list(KARPLUS_METHODS),
        help=(
            "Karplus relation to grade the corpus under: 'generic' (three-term) "
            "or 'haasnoot_altona' (electronegativity/orientation-corrected)."
        ),
    )
    parser.add_argument(
        "--weighting",
        type=str,
        default=CONFORMER_WEIGHTING_DEFAULT,
        choices=list(CONFORMER_WEIGHTINGS),
        help=(
            "Conformer-population weighting: 'uniform' (plain ensemble mean) or "
            "'boltzmann' (MMFF-energy Boltzmann weights, ground state dominates)."
        ),
    )
    parser.add_argument(
        "--max-conformers",
        type=int,
        default=KARPLUS_DEFAULT_MAX_CONFORMERS,
        help="ETKDG conformer ensemble size for the Karplus refinement.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=KARPLUS_RANDOM_SEED,
        help="RDKit embedding random seed (fixed for determinism).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write the JSON + CSV report. Defaults to the bundle directory.",
    )
    args = parser.parse_args()

    fixtures_root = args.fixtures_root
    report = run_all(
        fixtures_root,
        method=args.method,
        weighting=args.weighting,
        max_conformers=args.max_conformers,
        seed=args.seed,
        bundle_filename=args.bundle,
    )
    output_dir = args.output_dir or (fixtures_root / DEFAULT_OUTPUT_DIR_NAME)
    json_path = write_report(report, output_dir)
    print(json.dumps(report["summary"], indent=2, default=str))
    print(f"Report written: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
