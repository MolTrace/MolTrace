"""Tests for the QM9-NMR loader + shielding→shift converter."""

from __future__ import annotations

import json

import pytest

from moltrace.spectroscopy.predict.qm9nmr import (
    LinearReference,
    shielding_to_shift,
    load_qm9nmr_json,
)


def test_shielding_to_shift_is_reference_minus_sigma() -> None:
    # δ = intercept − slope·σ.  TMS-style: intercept = σ_ref, slope = 1.
    ref = LinearReference(intercept=187.0, slope=1.0)
    assert shielding_to_shift(60.0, ref) == pytest.approx(127.0)
    # A scaled linear fit.
    scaled = LinearReference(intercept=190.0, slope=1.05)
    assert shielding_to_shift(100.0, scaled) == pytest.approx(190.0 - 1.05 * 100.0)


def test_loader_passes_through_existing_shifts(tmp_path) -> None:
    data = [
        {"smiles": "C", "shifts": [{"atom_index": 0, "nucleus": "13C", "shift_ppm": -2.3}]}
    ]
    path = tmp_path / "qm9.json"
    path.write_text(json.dumps(data))
    records = load_qm9nmr_json(path)
    assert len(records) == 1
    assert records[0].smiles == "C"
    assert records[0].shifts[0]["shift_ppm"] == pytest.approx(-2.3)


def test_loader_converts_shielding_with_reference(tmp_path) -> None:
    data = [
        {"smiles": "C", "shielding": [{"atom_index": 0, "nucleus": "13C", "sigma": 197.0}]}
    ]
    path = tmp_path / "qm9_sigma.json"
    path.write_text(json.dumps(data))
    ref = {"13C": LinearReference(intercept=187.0, slope=1.0)}
    records = load_qm9nmr_json(path, reference=ref)
    # δ = 187 − 197 = −10.0
    assert records[0].shifts[0]["shift_ppm"] == pytest.approx(-10.0)


def test_loader_raises_on_shielding_without_reference(tmp_path) -> None:
    data = [
        {"smiles": "C", "shielding": [{"atom_index": 0, "nucleus": "13C", "sigma": 197.0}]}
    ]
    path = tmp_path / "qm9_noref.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_qm9nmr_json(path)  # no reference supplied
