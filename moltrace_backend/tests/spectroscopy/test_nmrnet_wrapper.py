"""Prompt 6 (revised) — tests for the NMRNet wrapper + HOSE fallback.

In CI neither torch nor the NMRNet weights are present, so the NMRNet inference
path is exercised with a **fake torch + a monkeypatched ``_run_nmrnet``** (which
validates device resolution, conformer-ensemble aggregation, and the NaN
single-conformer uncertainty without the real model), while the HOSE fallback is
exercised for real. The QM9-NMR accuracy gate is written but skipped unless real
weights + the QM9-NMR set are configured — no fabricated number is asserted.
"""

from __future__ import annotations

import math
import os
import sys
import types

import pytest

from moltrace.spectroscopy.predict import nmrnet_wrapper as w
from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    AtomShift,
    ShiftPrediction,
    predict_shifts,
)


# --------------------------------------------------------------------------- #
# Fake torch (so the NMRNet path is testable without a real install)
# --------------------------------------------------------------------------- #
class _FakeDevice:
    def __init__(self, kind: str) -> None:
        self.type = kind

    def __str__(self) -> str:
        return self.type


def _install_fake_torch(monkeypatch, *, cuda=False, mps=False) -> None:
    torch = types.ModuleType("torch")
    torch.device = lambda kind="cpu": _FakeDevice(kind)  # type: ignore[attr-defined]
    torch.cuda = types.SimpleNamespace(is_available=lambda: cuda)  # type: ignore[attr-defined]
    torch.backends = types.SimpleNamespace(  # type: ignore[attr-defined]
        mps=types.SimpleNamespace(is_available=lambda: mps)
    )
    torch.load = lambda *a, **k: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)


# --------------------------------------------------------------------------- #
# Input handling: parse failures, salts/charged species, stereochemistry, AddHs
# --------------------------------------------------------------------------- #
def test_parse_failure_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        predict_shifts("not a molecule )(")


def test_charged_species_and_salts_do_not_crash() -> None:
    # sodium acetate — a salt with a charged fragment.
    result = predict_shifts("CC(=O)[O-].[Na+]", nuclei=["13C"])
    assert result.method == "hose_fallback"
    # The two acetate carbons are predicted; Na+ contributes no C/H shift.
    assert [s.element for s in result.shifts] == ["C", "C"]


def test_stereochemistry_is_handled() -> None:
    result = predict_shifts("C[C@H](O)CC")  # a defined stereocentre
    assert isinstance(result, ShiftPrediction)
    assert result.shifts  # parsed + predicted without error


def test_addhs_produces_proton_shifts() -> None:
    # Methane: AddHs must add the four H so ¹H shifts exist.
    result = predict_shifts("C")
    elements = {s.element for s in result.shifts}
    assert "H" in elements and "C" in elements
    assert sum(s.element == "H" for s in result.shifts) == 4


# --------------------------------------------------------------------------- #
# Fallback behaviour + atom-index alignment + determinism
# --------------------------------------------------------------------------- #
def test_fallback_recovers_benzene_from_seed_kb() -> None:
    result = predict_shifts("c1ccccc1")
    assert result.method == "hose_fallback" and result.device == "cpu"
    carbons = [s.predicted_ppm for s in result.shifts if s.element == "C"]
    protons = [s.predicted_ppm for s in result.shifts if s.element == "H"]
    assert carbons and all(abs(v - 128.4) < 0.5 for v in carbons)
    assert protons and all(abs(v - 7.26) < 0.5 for v in protons)


def test_atom_index_alignment_matches_elements() -> None:
    # Every AtomShift's atom_index must point at an atom of its declared element
    # in the H-added molecule (no identity-ordering assumption).
    from rdkit import Chem

    smiles = "CCO"
    mol_h = Chem.AddHs(Chem.MolFromSmiles(smiles))
    result = predict_shifts(smiles)
    for shift in result.shifts:
        assert mol_h.GetAtomWithIdx(shift.atom_index).GetSymbol() == shift.element


def test_predictions_are_deterministic() -> None:
    a = predict_shifts("CCO")
    b = predict_shifts("CCO")
    assert [(s.atom_index, s.predicted_ppm) for s in a.shifts] == [
        (s.atom_index, s.predicted_ppm) for s in b.shifts
    ]


def test_conformer_failure_routes_to_fallback(monkeypatch) -> None:
    monkeypatch.setattr(w, "_embed_conformers", lambda *a, **k: [])
    result = predict_shifts("CCO")
    assert result.method == "hose_fallback"
    assert any("embedding" in msg.lower() for msg in result.warnings)


def test_unsupported_nucleus_is_ignored_with_warning() -> None:
    result = predict_shifts("CCO", nuclei=["19F"])  # not in the 1H/13C map
    assert any("unsupported" in msg.lower() for msg in result.warnings)
    assert result.shifts == []


def test_allow_fallback_false_raises_without_nmrnet() -> None:
    from moltrace.spectroscopy.predict.nmrnet_wrapper import NMRNetUnavailable

    with pytest.raises(NMRNetUnavailable):
        predict_shifts("CC", allow_fallback=False)


# --------------------------------------------------------------------------- #
# Device resolution + NMRNet ensemble aggregation (via fake torch)
# --------------------------------------------------------------------------- #
def test_device_resolution_order(monkeypatch) -> None:
    _install_fake_torch(monkeypatch, cuda=False, mps=True)
    from moltrace.spectroscopy.predict.nmrnet_wrapper import _select_device

    assert _select_device("cpu").type == "cpu"  # explicit preference wins
    assert _select_device().type == "mps"  # cuda off, mps on
    _install_fake_torch(monkeypatch, cuda=False, mps=False)
    assert _select_device().type == "cpu"  # both off → cpu baseline


def test_nmrnet_path_aggregates_conformers(monkeypatch) -> None:
    _install_fake_torch(monkeypatch)
    monkeypatch.setattr(
        w, "_run_nmrnet", lambda mol_h, conf_ids, nuclei, device, warnings: {
            (0, "13C"): [40.0, 42.0, 44.0]  # three conformers
        }
    )
    result = predict_shifts("CC", nuclei=["13C"], n_conformers=3)
    assert result.method == "nmrnet" and result.device == "cpu"
    shift = result.shifts[0]
    assert abs(shift.predicted_ppm - 42.0) < 1e-9
    assert shift.uncertainty_ppm > 0.0  # ensemble spread


def test_single_conformer_uncertainty_is_nan(monkeypatch) -> None:
    _install_fake_torch(monkeypatch)
    monkeypatch.setattr(
        w, "_run_nmrnet", lambda *a, **k: {(0, "13C"): [42.0]}  # one conformer
    )
    result = predict_shifts("CC", nuclei=["13C"], n_conformers=1)
    assert result.method == "nmrnet"
    assert math.isnan(result.shifts[0].uncertainty_ppm)
    assert any("nan" in msg.lower() for msg in result.warnings)


def test_mps_failure_retries_on_cpu(monkeypatch) -> None:
    _install_fake_torch(monkeypatch, mps=True)
    calls = {"n": 0}

    def flaky(mol_h, conf_ids, nuclei, device, warnings):
        calls["n"] += 1
        if device.type == "mps":
            raise RuntimeError("no MPS kernel for this op")
        return {(0, "13C"): [30.0, 31.0]}

    monkeypatch.setattr(w, "_run_nmrnet", flaky)
    result = predict_shifts("CC", nuclei=["13C"], n_conformers=2)
    assert result.method == "nmrnet" and result.device == "cpu"
    assert calls["n"] == 2  # tried MPS, then CPU
    assert any("mps" in msg.lower() for msg in result.warnings)


# --------------------------------------------------------------------------- #
# QM9-NMR accuracy gate (paper's QM9NMR panel, NOT the nmrshiftdb2 headline)
# --------------------------------------------------------------------------- #
# Xu et al., Nat. Comput. Sci. 5, 292 (2025), QM9NMR comparison vs DetaNet
# (arXiv:2408.15681): NMRNet MAE 0.020 ppm (1H), 0.262 ppm (13C) — distinct from
# the nmrshiftdb2 experimental headline of 0.181 / 1.098 ppm.
_PAPER_QM9NMR_MAE = {"1H": 0.020, "13C": 0.262}


@pytest.mark.slow
@pytest.mark.skipif(
    not (os.environ.get("MOLTRACE_NMRNET_WEIGHTS") and os.environ.get("MOLTRACE_QM9NMR_PATH")),
    reason=(
        "Real NMRNet weights (MOLTRACE_NMRNET_WEIGHTS) and the QM9-NMR test set "
        "(MOLTRACE_QM9NMR_PATH) are required; neither ships here. No fabricated "
        "number is asserted when they are absent."
    ),
)
def test_nmrnet_qm9nmr_mae_within_30pct_of_paper() -> None:  # pragma: no cover - env-gated
    import json
    from pathlib import Path

    qm9 = json.loads(Path(os.environ["MOLTRACE_QM9NMR_PATH"]).read_text())
    abs_err: dict[str, list[float]] = {"1H": [], "13C": []}
    for record in qm9:
        prediction = predict_shifts(record["smiles"])
        assert prediction.method == "nmrnet", "expected the NMRNet backend for this gate"
        by_index = {s.atom_index: s for s in prediction.shifts}
        for ref in record["shifts"]:
            got = by_index.get(int(ref["atom_index"]))
            if got is not None and ref["nucleus"] in abs_err:
                abs_err[ref["nucleus"]].append(abs(got.predicted_ppm - float(ref["shift_ppm"])))

    for nucleus, errors in abs_err.items():
        if not errors:
            continue
        mae = sum(errors) / len(errors)
        assert mae <= _PAPER_QM9NMR_MAE[nucleus] * 1.30, (
            f"{nucleus} QM9NMR MAE {mae:.3f} exceeds 130% of paper "
            f"({_PAPER_QM9NMR_MAE[nucleus]:.3f} ppm)"
        )


def test_shift_objects_have_expected_fields() -> None:
    result = predict_shifts("CCO")
    assert all(isinstance(s, AtomShift) for s in result.shifts)
    sample = result.shifts[0]
    for field_name in ("atom_index", "element", "nucleus", "predicted_ppm", "uncertainty_ppm"):
        assert hasattr(sample, field_name)
