"""Output-invariance goldens for the raw-FID pipeline (Prompt 2 science gate).

The Instant-FID latency work rewrites the *how* of ``process_bruker_1d_zip``
(single baseline estimate, decimated auto-phase scoring, decimated sensitivity
sweep, ndarray containers) while promising the *what* is untouched. These tests
are that promise, written before the optimizations: they run the real pipeline
over the public nmrshiftdb2 Bruker fixtures and pin every scientifically
meaningful output — chosen peak-detection sensitivity, the peak list (shifts,
integrals, multiplicities), phase mode and (p0, p1) to display precision,
baseline mode, and a downsampled-preview aggregate — to committed golden files.

A legitimate science change (Prompt 5 territory, not Prompt 2) re-baselines
visibly by regenerating the goldens and explaining the diff in the same commit:

    MOLTRACE_REGEN_FID_GOLDEN=1 uv run pytest tests/test_fid_pipeline_invariants.py -m ''

The fast tier (one small 1H fixture, both guidance modes) runs in the default
suite. The full corpus tier is marked ``slow`` like the other multi-FID guards.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "nmrshiftdb2"
NMREDATA = FIXTURES / "source" / "nmrshiftdb2rawdata.nmredata.sd"
GOLDEN_DIR = Path(__file__).parent / "golden" / "fid_invariants"
REGEN = os.environ.get("MOLTRACE_REGEN_FID_GOLDEN") == "1"

# Display precision for phase angles is 3 decimal places (fid.py rounds p0/p1
# with round(..., 3)); a half-unit-in-the-last-place bound on that rounding.
PHASE_TOL_DEG = 5e-3
SHIFT_TOL_PPM = 1e-4
INTEGRAL_TOL_H = 1e-3

# One small 1H fixture keeps the default-suite cost to a few seconds while the
# full corpus rides behind the slow marker with the other >30 s guards.
FAST_SPECTRA = {"60000023"}


def _structure_index() -> tuple[dict[str, str], dict[str, str]]:
    """spectrum_id -> (SMILES, solvent) from the bundled NMReDATA index."""
    if not NMREDATA.exists():
        return {}, {}
    text = NMREDATA.read_text(errors="ignore")
    smiles: dict[str, str] = {}
    solvent: dict[str, str] = {}
    for record in text.split("$$$$"):
        match = re.search(r"<NMREDATA_SMILES>\s*\n(.+?)\n", record)
        if not match:
            continue
        value = match.group(1).strip().rstrip("\\")
        sol = re.search(r"<NMREDATA_SOLVENT>\s*\n(.+?)\n", record)
        sol_value = (sol.group(1).strip().rstrip("\\") if sol else "").split(",")[0]
        for spectrum_id in re.findall(r"spectrumid=(\d+)", record):
            smiles[spectrum_id] = value
            solvent[spectrum_id] = sol_value.strip()
    return smiles, solvent


def _cases() -> list[dict[str, Any]]:
    if not FIXTURES.exists():
        return []
    smiles, solvent = _structure_index()
    cases: list[dict[str, Any]] = []
    for archive in sorted((FIXTURES / "raw").glob("nmrshiftdb2_*_1h.zip")):
        spectrum_id = archive.stem.split("_")[1]
        base = {
            "spectrum_id": spectrum_id,
            "archive": archive,
            "nucleus": "1H",
            "solvent": solvent.get(spectrum_id) or None,
        }
        # Unguided: the 5-candidate sensitivity sweep, relative integrals.
        cases.append({**base, "config": "unguided", "smiles": None})
        # Structure-guided: the 7-candidate sweep plus deconvolution pass.
        if spectrum_id in smiles:
            cases.append({**base, "config": "guided", "smiles": smiles[spectrum_id]})
    for archive in sorted((FIXTURES / "raw").glob("nmrshiftdb2_*_13c.zip"))[:2]:
        spectrum_id = archive.stem.split("_")[1]
        cases.append(
            {
                "spectrum_id": spectrum_id,
                "archive": archive,
                "nucleus": "13C",
                "solvent": solvent.get(spectrum_id) or None,
                "config": "unguided",
                "smiles": None,
            }
        )
    return cases


CASES = _cases()


def _case_id(case: dict[str, Any]) -> str:
    return f"{case['spectrum_id']}_{case['nucleus'].lower()}_{case['config']}"


def _run_pipeline(case: dict[str, Any]) -> dict[str, Any]:
    from nmrcheck.fid import process_bruker_1d_zip

    expected_total_h = expected_non_labile_h = None
    if case["smiles"] is not None:
        from nmrcheck.chemistry import structure_summary_from_smiles

        structure = structure_summary_from_smiles(case["smiles"])
        expected_total_h = structure.total_hydrogens
        expected_non_labile_h = structure.non_labile_hydrogens

    archive: Path = case["archive"]
    report = process_bruker_1d_zip(
        filename=archive.name,
        content=archive.read_bytes(),
        solvent=case["solvent"],
        nucleus=case["nucleus"],
        expected_total_h=expected_total_h,
        expected_non_labile_h=expected_non_labile_h,
    )
    metadata = report.metadata or {}
    phase = metadata.get("phase") or {}
    baseline = metadata.get("baseline") or {}
    preview = report.preview_points
    y_values = [float(p.intensity) for p in preview]
    y_max = max(y_values) if y_values else 0.0
    x_at_y_max = float(preview[y_values.index(y_max)].shift_ppm) if y_values else 0.0
    return {
        "point_count": int(report.point_count),
        "phase": {
            "mode": phase.get("mode"),
            "p0": float(phase.get("p0") or 0.0),
            "p1": float(phase.get("p1") or 0.0),
            "correction_applied": bool(phase.get("correction_applied")),
        },
        "baseline": {
            "mode": baseline.get("mode"),
            "order": baseline.get("order"),
            "correction_applied": bool(baseline.get("correction_applied")),
        },
        "peak_detection_sensitivity": metadata.get("peak_detection_sensitivity"),
        "peaks": [
            {
                "shift_ppm": round(float(p.shift_ppm), 6),
                "integration_h": round(float(p.integration_h), 6),
                "multiplicity": p.multiplicity,
            }
            for p in report.inferred_peaks
        ],
        "preview": {
            "n": len(preview),
            "y_sum": float(sum(y_values)),
            "y_max": y_max,
            "x_at_y_max": x_at_y_max,
        },
    }


def _golden_path(case: dict[str, Any]) -> Path:
    return GOLDEN_DIR / f"{_case_id(case)}.json"


def _assert_matches_golden(observed: dict[str, Any], golden: dict[str, Any]) -> None:
    assert observed["point_count"] == golden["point_count"]

    assert observed["phase"]["mode"] == golden["phase"]["mode"]
    assert observed["phase"]["correction_applied"] == golden["phase"]["correction_applied"]
    assert observed["phase"]["p0"] == pytest.approx(golden["phase"]["p0"], abs=PHASE_TOL_DEG)
    assert observed["phase"]["p1"] == pytest.approx(golden["phase"]["p1"], abs=PHASE_TOL_DEG)

    assert observed["baseline"] == golden["baseline"]

    assert observed["peak_detection_sensitivity"] == pytest.approx(
        golden["peak_detection_sensitivity"], abs=1e-9
    )

    assert len(observed["peaks"]) == len(golden["peaks"]), (
        f"peak count changed: {len(golden['peaks'])} -> {len(observed['peaks'])}"
    )
    for i, (obs, gold) in enumerate(zip(observed["peaks"], golden["peaks"], strict=True)):
        assert obs["multiplicity"] == gold["multiplicity"], f"peak {i} multiplicity"
        assert obs["shift_ppm"] == pytest.approx(gold["shift_ppm"], abs=SHIFT_TOL_PPM), (
            f"peak {i} shift"
        )
        assert obs["integration_h"] == pytest.approx(
            gold["integration_h"], abs=INTEGRAL_TOL_H
        ), f"peak {i} integration"

    assert observed["preview"]["n"] == golden["preview"]["n"]
    assert observed["preview"]["y_max"] == pytest.approx(
        golden["preview"]["y_max"], rel=1e-6
    )
    assert observed["preview"]["x_at_y_max"] == pytest.approx(
        golden["preview"]["x_at_y_max"], abs=SHIFT_TOL_PPM
    )
    assert observed["preview"]["y_sum"] == pytest.approx(
        golden["preview"]["y_sum"], rel=1e-5, abs=1e-9
    )
    assert math.isfinite(observed["preview"]["y_sum"])


def _check_case(case: dict[str, Any]) -> None:
    path = _golden_path(case)
    observed = _run_pipeline(case)
    if REGEN:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
        return
    assert path.exists(), (
        f"Missing golden {path.name}; generate with MOLTRACE_REGEN_FID_GOLDEN=1"
    )
    golden = json.loads(path.read_text())
    _assert_matches_golden(observed, golden)


FAST_CASES = [c for c in CASES if c["spectrum_id"] in FAST_SPECTRA and c["nucleus"] == "1H"]
SLOW_CASES = [c for c in CASES if c not in FAST_CASES]


@pytest.mark.skipif(not FAST_CASES, reason="nmrshiftdb2 fixtures unavailable")
@pytest.mark.parametrize("case", FAST_CASES, ids=_case_id)
def test_fid_pipeline_outputs_pinned_fast(case: dict[str, Any]) -> None:
    _check_case(case)


@pytest.mark.slow
@pytest.mark.skipif(not SLOW_CASES, reason="nmrshiftdb2 fixtures unavailable")
@pytest.mark.parametrize("case", SLOW_CASES, ids=_case_id)
def test_fid_pipeline_outputs_pinned_full_corpus(case: dict[str, Any]) -> None:
    _check_case(case)
