"""Prompt 6 — tests for the NMRNet shift-prediction wrapper + HOSE fallback.

In this environment NMRNet's dependencies (torch + the NMRNet package + weights)
are absent, so every test here exercises the **HOSE-code fallback** and the
**gating** that routes to it. The NMRNet path is covered by injecting a
*conformant stub* (a fake torch + fake NMRNet package) so the adapter plumbing is
verified without claiming the real model runs. The QM9-NMR accuracy gate against
the paper's reported MAE is written but **skips** unless a real checkpoint and the
QM9-NMR set are configured — it never asserts a fabricated number.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    AtomShiftPrediction,
    NMRNetUnavailable,
    ShiftPrediction,
    _NMRNetBackend,
    build_seed_knowledge_base,
    hose_code,
    load_knowledge_base,
    predict_shifts,
)
from rdkit import Chem


# --------------------------------------------------------------------------- #
# Gating: NMRNet is unavailable here, fallback is used
# --------------------------------------------------------------------------- #
def test_nmrnet_backend_is_cleanly_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("MOLTRACE_NMRNET_WEIGHTS", raising=False)
    with pytest.raises(NMRNetUnavailable):
        _NMRNetBackend.load()


def test_predict_shifts_falls_back_to_hose(monkeypatch) -> None:
    monkeypatch.delenv("MOLTRACE_NMRNET_WEIGHTS", raising=False)
    result = predict_shifts("c1ccccc1")
    assert isinstance(result, ShiftPrediction)
    assert result.backend == "hose_nmrshiftdb2"
    assert result.notes and "fallback" in result.notes[0].lower()


def test_shiftprediction_structure() -> None:
    result = predict_shifts("CCO")  # ethanol
    assert set(result.nuclei) == {"1H", "13C"}
    # shifts is keyed by atom index, each value carries the core read-outs.
    for atom_index, shift in result.shifts.items():
        assert isinstance(atom_index, int)
        assert isinstance(shift, AtomShiftPrediction)
        assert shift.atom_index == atom_index
        assert isinstance(shift.predicted_ppm, float)
        assert isinstance(shift.uncertainty_ppm, float) and shift.uncertainty_ppm >= 0.0
        assert shift.nucleus in {"1H", "13C"}
        assert shift.element in {"H", "C"}
        assert shift.method == "hose_nmrshiftdb2"


# --------------------------------------------------------------------------- #
# Fallback accuracy on the curated seed KB (honest: in-KB recovery)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "smiles, element, expected_ppm, nucleus",
    [
        ("c1ccccc1", "C", 128.4, "13C"),
        ("c1ccccc1", "H", 7.26, "1H"),
        ("C1CCCCC1", "C", 26.9, "13C"),
        ("C1CCCCC1", "H", 1.43, "1H"),
        ("CC#N", "C", 118.3, "13C"),  # nitrile carbon
        ("CC(C)=O", "C", 206.0, "13C"),  # carbonyl carbon
    ],
)
def test_seed_kb_recovers_curated_shifts(smiles, element, expected_ppm, nucleus) -> None:
    result = predict_shifts(smiles)
    matching = [
        s.predicted_ppm
        for s in result.shifts.values()
        if s.element == element and s.nucleus == nucleus
        and abs(s.predicted_ppm - expected_ppm) < 0.5
    ]
    assert matching, (
        f"{smiles}: no {nucleus} atom recovered near {expected_ppm} ppm; "
        f"got {[round(s.predicted_ppm, 1) for s in result.shifts.values() if s.nucleus == nucleus]}"
    )


# --------------------------------------------------------------------------- #
# Sphere-decreasing generalisation (the core spec behaviour)
# --------------------------------------------------------------------------- #
def test_sphere_decreases_until_match() -> None:
    # Toluene's aromatic ring carbons are NOT exact KB members (only its methyl
    # is), so they must match benzene's aromatic-CH environment at a sphere < 6.
    result = predict_shifts("Cc1ccccc1")
    aromatic_like = [
        s
        for s in result.shifts.values()
        if s.nucleus == "13C"
        and abs(s.predicted_ppm - 128.4) < 1.0
        and 0 < s.provenance["hose_sphere"] < 6
    ]
    assert aromatic_like, "expected ring carbons to match benzene env at a reduced sphere"


def test_unknown_environment_falls_back_to_element_prior() -> None:
    # C-Br is absent from the seed KB; the carbon should drop to the element
    # prior (sphere 0) with a large uncertainty rather than a confident guess.
    result = predict_shifts("CBr")
    carbon = next(s for s in result.shifts.values() if s.element == "C")
    assert carbon.provenance["hose_sphere"] == 0
    assert carbon.provenance.get("element_prior") is True
    assert carbon.uncertainty_ppm >= 10.0  # honestly low-confidence


# --------------------------------------------------------------------------- #
# HOSE code properties
# --------------------------------------------------------------------------- #
def test_hose_code_is_deterministic_and_sized() -> None:
    mol = Chem.AddHs(Chem.MolFromSmiles("Cc1ccccc1"))
    code_a = hose_code(mol, 3, max_sphere=6)
    code_b = hose_code(mol, 3, max_sphere=6)
    assert code_a == code_b
    assert len(code_a) == 7  # center + 6 shells
    # Truncation is a strict prefix: a smaller sphere is the start of a larger one.
    code_3 = hose_code(mol, 3, max_sphere=3)
    assert code_3 == code_a[:4]


def test_distinct_environments_get_distinct_codes() -> None:
    mol = Chem.AddHs(Chem.MolFromSmiles("CC=O"))  # acetaldehyde

    def _h_neighbors(atom: Chem.Atom) -> int:
        return sum(1 for nbr in atom.GetNeighbors() if nbr.GetSymbol() == "H")

    # After AddHs the hydrogens are explicit atoms, so identify the methyl by its
    # H *neighbours* (GetTotalNumHs would be 0 here) and the carbonyl by its C=O.
    methyl_c = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C" and _h_neighbors(a) == 3)
    carbonyl_c = next(
        a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetSymbol() == "C"
        and any(b.GetBondType() == Chem.BondType.DOUBLE for b in a.GetBonds())
    )
    assert hose_code(mol, methyl_c) != hose_code(mol, carbonyl_c)


# --------------------------------------------------------------------------- #
# Input handling + nucleus selection
# --------------------------------------------------------------------------- #
def test_invalid_smiles_raises() -> None:
    with pytest.raises(ValueError):
        predict_shifts("not a molecule )(")


def test_only_requested_nuclei_are_predicted() -> None:
    result = predict_shifts("CCO", nuclei=["13C"])
    assert result.shifts  # non-empty
    assert all(s.nucleus == "13C" and s.element == "C" for s in result.shifts.values())


def test_custom_knowledge_base_overrides_seed(tmp_path) -> None:
    # A tiny custom KB: methane carbon at a deliberately unusual shift.
    export = [
        {
            "smiles": "C",
            "assignments": [{"atom_index": 0, "nucleus": "13C", "shift_ppm": -99.0}],
        }
    ]
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(export))
    kb = load_knowledge_base(path)
    assert kb.reference_count == 1
    result = predict_shifts("C", nuclei=["13C"], knowledge_base=kb)
    carbon = next(s for s in result.shifts.values() if s.element == "C")
    assert abs(carbon.predicted_ppm - (-99.0)) < 0.5


# --------------------------------------------------------------------------- #
# NMRNet adapter plumbing, via a conformant stub (no real model claimed)
# --------------------------------------------------------------------------- #
def test_nmrnet_adapter_plumbing_with_conformant_stub(tmp_path, monkeypatch) -> None:
    """Inject a fake torch + a conformant fake NMRNet package and confirm the
    adapter does the RDKit featurisation, calls the model, and maps outputs back
    to atom indices. This validates OUR contract — it does not run real NMRNet."""

    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))

    fake = types.ModuleType("fake_nmrnet")

    def load_pretrained(weights_path: str):
        def model(symbols, coords, nuclei):
            assert len(symbols) == len(coords)  # adapter passes real 3D coords
            out = {}
            for i, sym in enumerate(symbols):
                if sym == "C":
                    out[i] = (42.0, 0.5)
                elif sym == "H":
                    out[i] = (3.0, 0.1)
            return out

        return model

    fake.load_pretrained = load_pretrained
    monkeypatch.setitem(sys.modules, "fake_nmrnet", fake)
    monkeypatch.setenv("MOLTRACE_NMRNET_MODULE", "fake_nmrnet")
    weights = tmp_path / "weights.pt"
    weights.write_text("checkpoint")
    monkeypatch.setenv("MOLTRACE_NMRNET_WEIGHTS", str(weights))

    result = predict_shifts("CC", nuclei=["1H", "13C"])  # ethane
    assert result.backend == "nmrnet"
    assert result.notes == ()
    carbons = [s.predicted_ppm for s in result.shifts.values() if s.element == "C"]
    hydrogens = [s.predicted_ppm for s in result.shifts.values() if s.element == "H"]
    assert carbons and all(abs(v - 42.0) < 1e-9 for v in carbons)
    assert hydrogens and all(abs(v - 3.0) < 1e-9 for v in hydrogens)
    assert all(s.method == "nmrnet" for s in result.shifts.values())


# --------------------------------------------------------------------------- #
# Paper-accuracy gate — written, but skipped unless real assets are present
# --------------------------------------------------------------------------- #
import os  # noqa: E402

_PAPER_MAE = {"1H": 0.181, "13C": 1.098}  # Xu et al., Nat. Comput. Sci. 5, 292 (2025)


@pytest.mark.skipif(
    not (os.environ.get("MOLTRACE_NMRNET_WEIGHTS") and os.environ.get("MOLTRACE_QM9NMR_PATH")),
    reason=(
        "NMRNet checkpoint (MOLTRACE_NMRNET_WEIGHTS) and the QM9-NMR test set "
        "(MOLTRACE_QM9NMR_PATH) are required; neither ships in this repo. "
        "No fabricated number is asserted when they are absent."
    ),
)
def test_nmrnet_qm9_mae_within_30pct_of_paper() -> None:  # pragma: no cover - env-gated
    """When a real NMRNet checkpoint + QM9-NMR are configured, measured MAE must
    be within 30 % of the paper's reported values (0.181 ppm ¹H, 1.098 ppm ¹³C).

    QM9-NMR JSON: ``[{"smiles": ..., "shifts": [{"atom_index", "nucleus",
    "shift_ppm"}, ...]}, ...]``.
    """

    qm9 = json.loads(__import__("pathlib").Path(os.environ["MOLTRACE_QM9NMR_PATH"]).read_text())
    abs_err: dict[str, list[float]] = {"1H": [], "13C": []}
    for record in qm9:
        pred = predict_shifts(record["smiles"])
        assert pred.backend == "nmrnet", "expected the NMRNet backend for this gate"
        by_index = pred.shifts
        for ref in record["shifts"]:
            nucleus = ref["nucleus"]
            if nucleus not in abs_err:
                continue
            got = by_index.get(int(ref["atom_index"]))
            if got is not None:
                abs_err[nucleus].append(abs(got.predicted_ppm - float(ref["shift_ppm"])))

    for nucleus, errors in abs_err.items():
        if not errors:
            continue
        mae = sum(errors) / len(errors)
        assert mae <= _PAPER_MAE[nucleus] * 1.30, (
            f"{nucleus} MAE {mae:.3f} ppm exceeds 130 % of paper "
            f"({_PAPER_MAE[nucleus]:.3f} ppm)"
        )
